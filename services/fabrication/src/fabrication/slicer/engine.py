"""CuraEngine CLI wrapper with async job management."""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from common.logging import get_logger

from .profiles import ProfileManager
from .schemas import (
    SlicingConfig,
    SlicingJobStatus,
    SlicingStatus,
    SupportType,
)

LOGGER = get_logger(__name__)


@dataclass
class SlicingJob:
    """Internal representation of a slicing job."""

    job_id: str
    input_path: Path
    output_path: Path
    config: SlicingConfig
    status: SlicingStatus = SlicingStatus.PENDING
    progress: float = 0.0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # Estimates parsed from slicer output
    estimated_print_time_seconds: Optional[int] = None
    estimated_filament_grams: Optional[float] = None
    layer_count: Optional[int] = None


class SlicerEngine:
    """CuraEngine CLI wrapper with async job management.

    Manages slicing jobs in background tasks, providing status polling
    and progress tracking.
    """

    def __init__(
        self,
        bin_path: str | Path,
        profiles_dir: str | Path,
        output_base_dir: str | Path,
    ):
        """Initialize slicer engine.

        Args:
            bin_path: Path to CuraEngine binary
            profiles_dir: Directory containing slicer profiles
            output_base_dir: Base directory for G-code output
        """
        self.bin_path = Path(bin_path)
        self.output_base_dir = Path(output_base_dir)
        self.profiles = ProfileManager(profiles_dir)

        # In-memory job storage (matches segmentation pattern)
        self._jobs: dict[str, SlicingJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}

        # Check if slicer binary is available
        self._slicer_available = self._check_slicer_available()

        # Ensure output directory exists
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "SlicerEngine initialized",
            bin_path=str(self.bin_path),
            profiles_dir=str(profiles_dir),
            output_dir=str(self.output_base_dir),
            slicer_available=self._slicer_available,
        )

    def _check_slicer_available(self) -> bool:
        """Check if CuraEngine binary is available and executable."""
        if not self.bin_path.exists():
            LOGGER.warning(
                "CuraEngine not found - slicing disabled",
                expected_path=str(self.bin_path),
            )
            return False
        return True

    @property
    def is_available(self) -> bool:
        """Check if slicing is available on this system."""
        return self._slicer_available

    async def slice_async(self, input_path: str, config: SlicingConfig) -> str:
        """Start async slicing job.

        Args:
            input_path: Path to input 3MF or STL file
            config: Slicing configuration

        Returns:
            Job ID for status polling

        Raises:
            RuntimeError: If slicer is not available on this system
        """
        if not self._slicer_available:
            raise RuntimeError(
                "CuraEngine is not available on this system. "
                "Ensure CuraEngine binary is installed at the configured path."
            )

        job_id = str(uuid.uuid4())
        input_file = Path(input_path)

        # Create output directory for this job
        job_output_dir = self.output_base_dir / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)

        # Generate output filename
        output_filename = input_file.stem + ".gcode"
        output_path = job_output_dir / output_filename

        # Create job record
        job = SlicingJob(
            job_id=job_id,
            input_path=input_file,
            output_path=output_path,
            config=config,
        )
        self._jobs[job_id] = job

        # Start background task
        task = asyncio.create_task(self._execute_slicing(job))
        self._tasks[job_id] = task

        LOGGER.info(
            "Started slicing job",
            job_id=job_id,
            input=str(input_path),
            printer=config.printer_id,
            material=config.material_id,
            quality=config.quality.value,
        )

        return job_id

    def get_job_status(self, job_id: str) -> Optional[SlicingJobStatus]:
        """Get current status of a slicing job."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        return SlicingJobStatus(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            input_path=str(job.input_path),
            config=job.config,
            gcode_path=str(job.output_path) if job.status == SlicingStatus.COMPLETED else None,
            error=job.error,
            started_at=job.started_at,
            completed_at=job.completed_at,
            estimated_print_time_seconds=job.estimated_print_time_seconds,
            estimated_filament_grams=job.estimated_filament_grams,
            layer_count=job.layer_count,
        )

    def get_gcode_path(self, job_id: str) -> Optional[Path]:
        """Get path to generated G-code file if completed."""
        job = self._jobs.get(job_id)
        if job and job.status == SlicingStatus.COMPLETED and job.output_path.exists():
            return job.output_path
        return None

    async def _execute_slicing(self, job: SlicingJob) -> None:
        """Execute slicing in background.

        Updates job status and progress as slicing proceeds.
        """
        job.status = SlicingStatus.RUNNING
        job.started_at = datetime.now()
        job.progress = 0.1  # Starting

        try:
            # Build CLI command
            cmd = await self._build_command(job)
            LOGGER.debug("Executing slicer command", cmd=" ".join(cmd))

            # Run slicer subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Read output and track progress
            stdout_lines = []
            stderr_lines = []

            async def read_stream(stream, lines_list, is_stderr=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").strip()
                    lines_list.append(decoded)
                    if not is_stderr:
                        self._parse_progress(job, decoded)

            await asyncio.gather(
                read_stream(process.stdout, stdout_lines),
                read_stream(process.stderr, stderr_lines, is_stderr=True),
            )

            return_code = await process.wait()

            if return_code != 0:
                error_msg = "\n".join(stderr_lines[-10:]) if stderr_lines else "Unknown error"
                raise RuntimeError(f"Slicer exited with code {return_code}: {error_msg}")

            # Verify output exists
            if not job.output_path.exists():
                raise RuntimeError(f"Slicer did not produce output file: {job.output_path}")

            # Parse final estimates from G-code
            self._parse_gcode_metadata(job)

            job.status = SlicingStatus.COMPLETED
            job.progress = 1.0
            job.completed_at = datetime.now()

            LOGGER.info(
                "Slicing completed",
                job_id=job.job_id,
                output=str(job.output_path),
                duration_s=(job.completed_at - job.started_at).total_seconds(),
                layers=job.layer_count,
            )

        except Exception as e:
            job.status = SlicingStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now()
            LOGGER.error(
                "Slicing failed",
                job_id=job.job_id,
                error=str(e),
            )

    async def _build_command(self, job: SlicingJob) -> list[str]:
        """Build CuraEngine CLI command with settings.

        CuraEngine syntax: CuraEngine slice -v -p -s key=value ... -l model.stl -o output.gcode
        """
        cmd = [str(self.bin_path), "slice", "-v", "-p"]

        # Add printer settings from profile
        printer = self.profiles.get_printer_profile(job.config.printer_id)
        if printer and printer.curaengine_settings:
            for key, value in printer.curaengine_settings.items():
                cmd.extend(["-s", f"{key}={value}"])
        else:
            # Fallback: use build volume from basic profile
            if printer:
                cmd.extend(["-s", f"machine_width={int(printer.build_volume[0])}"])
                cmd.extend(["-s", f"machine_depth={int(printer.build_volume[1])}"])
                cmd.extend(["-s", f"machine_height={int(printer.build_volume[2])}"])
                cmd.extend(["-s", f"machine_nozzle_size={printer.nozzle_diameter}"])
                cmd.extend(["-s", f"machine_heated_bed={'true' if printer.heated_bed else 'false'}"])
            LOGGER.warning(
                "Printer profile missing curaengine_settings, using fallback",
                printer_id=job.config.printer_id,
            )

        # Add material settings from profile
        material = self.profiles.get_material_profile(
            job.config.material_id, job.config.printer_id
        )
        if material and material.curaengine_settings:
            for key, value in material.curaengine_settings.items():
                cmd.extend(["-s", f"{key}={value}"])
        else:
            # Fallback: use basic profile values
            if material:
                cmd.extend(["-s", f"material_print_temperature={material.default_nozzle_temp}"])
                cmd.extend(["-s", f"material_bed_temperature={material.default_bed_temp}"])
                cmd.extend(["-s", f"cool_fan_speed={material.cooling_fan_speed}"])
            LOGGER.warning(
                "Material profile missing curaengine_settings, using fallback",
                material_id=job.config.material_id,
            )

        # Add quality settings from profile
        quality = self.profiles.get_quality_profile(job.config.quality.value)
        if quality and quality.curaengine_settings:
            for key, value in quality.curaengine_settings.items():
                cmd.extend(["-s", f"{key}={value}"])
        else:
            # Fallback: convert mm to microns (CuraEngine uses microns)
            if quality:
                layer_height_microns = int(quality.layer_height * 1000)
                first_layer_microns = int(quality.first_layer_height * 1000)
                cmd.extend(["-s", f"layer_height={layer_height_microns}"])
                cmd.extend(["-s", f"layer_height_0={first_layer_microns}"])
                cmd.extend(["-s", f"wall_line_count={quality.perimeters}"])
                cmd.extend(["-s", f"top_layers={quality.top_solid_layers}"])
                cmd.extend(["-s", f"bottom_layers={quality.bottom_solid_layers}"])
                cmd.extend(["-s", f"infill_sparse_density={quality.fill_density}"])
                cmd.extend(["-s", f"infill_pattern={quality.fill_pattern}"])
                cmd.extend(["-s", f"speed_print={quality.print_speed}"])
            LOGGER.warning(
                "Quality profile missing curaengine_settings, using fallback",
                quality_id=job.config.quality.value,
            )

        # Add support settings based on config
        if job.config.support_type == SupportType.TREE:
            cmd.extend(["-s", "support_enable=true"])
            cmd.extend(["-s", "support_structure=tree"])
            cmd.extend(["-s", "support_type=everywhere"])
        elif job.config.support_type == SupportType.NORMAL:
            cmd.extend(["-s", "support_enable=true"])
            cmd.extend(["-s", "support_structure=normal"])
        else:
            cmd.extend(["-s", "support_enable=false"])

        # Add infill override
        cmd.extend(["-s", f"infill_sparse_density={job.config.infill_percent}"])

        # Add config overrides
        if job.config.layer_height_mm:
            layer_height_microns = int(job.config.layer_height_mm * 1000)
            cmd.extend(["-s", f"layer_height={layer_height_microns}"])
        if job.config.nozzle_temp_c:
            cmd.extend(["-s", f"material_print_temperature={job.config.nozzle_temp_c}"])
        if job.config.bed_temp_c:
            cmd.extend(["-s", f"material_bed_temperature={job.config.bed_temp_c}"])

        # Input file (-l for load model)
        cmd.extend(["-l", str(job.input_path)])

        # Output file
        cmd.extend(["-o", str(job.output_path)])

        return cmd

    def _parse_progress(self, job: SlicingJob, line: str) -> None:
        """Parse slicer output for progress updates."""
        # OrcaSlicer/PrusaSlicer progress patterns
        # "=> Slicing object" -> 0.2
        # "=> Generating support" -> 0.4
        # "=> Generating G-code" -> 0.6
        # "=> Done." -> 0.9

        line_lower = line.lower()
        if "slicing" in line_lower:
            job.progress = 0.2
        elif "support" in line_lower:
            job.progress = 0.4
        elif "infill" in line_lower:
            job.progress = 0.5
        elif "perimeter" in line_lower:
            job.progress = 0.6
        elif "g-code" in line_lower or "gcode" in line_lower:
            job.progress = 0.7
        elif "done" in line_lower:
            job.progress = 0.9

    def _parse_gcode_metadata(self, job: SlicingJob) -> None:
        """Parse generated G-code for print time and filament estimates."""
        try:
            gcode_content = job.output_path.read_text(errors="replace")

            # Look for common comment formats
            # ; estimated printing time = 1h 30m 45s
            # ; filament used [mm] = 12345.67
            # ; filament used [g] = 45.6
            # ; total layers = 150

            # Parse print time
            time_match = re.search(
                r";\s*estimated printing time.*?=\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?",
                gcode_content,
                re.IGNORECASE,
            )
            if time_match:
                hours = int(time_match.group(1) or 0)
                minutes = int(time_match.group(2) or 0)
                seconds = int(time_match.group(3) or 0)
                job.estimated_print_time_seconds = hours * 3600 + minutes * 60 + seconds

            # Parse filament weight
            weight_match = re.search(
                r";\s*filament used.*?\[g\]\s*=\s*([\d.]+)",
                gcode_content,
                re.IGNORECASE,
            )
            if weight_match:
                job.estimated_filament_grams = float(weight_match.group(1))

            # Parse layer count
            layer_match = re.search(
                r";\s*total layers\s*=\s*(\d+)",
                gcode_content,
                re.IGNORECASE,
            )
            if layer_match:
                job.layer_count = int(layer_match.group(1))

            LOGGER.debug(
                "Parsed G-code metadata",
                job_id=job.job_id,
                print_time_s=job.estimated_print_time_seconds,
                filament_g=job.estimated_filament_grams,
                layers=job.layer_count,
            )

        except Exception as e:
            LOGGER.warning(
                "Failed to parse G-code metadata",
                job_id=job.job_id,
                error=str(e),
            )

    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """Remove old completed/failed jobs from memory.

        Returns number of jobs cleaned up.
        """
        now = datetime.now()
        to_remove = []

        for job_id, job in self._jobs.items():
            if job.completed_at:
                age_hours = (now - job.completed_at).total_seconds() / 3600
                if age_hours > max_age_hours:
                    to_remove.append(job_id)

        for job_id in to_remove:
            del self._jobs[job_id]
            if job_id in self._tasks:
                del self._tasks[job_id]

        if to_remove:
            LOGGER.info("Cleaned up old slicing jobs", count=len(to_remove))

        return len(to_remove)
