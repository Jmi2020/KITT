"""
Disk Space Management for Research Pipeline

Provides disk quota monitoring, old data compression, and cold storage
upload to MinIO for research data management.

Features:
- Quota monitoring with configurable thresholds
- Automatic compression of old data
- MinIO upload for cold storage
- Cleanup policies for temporary files
"""

import asyncio
import gzip
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import json

logger = logging.getLogger(__name__)


@dataclass
class DiskUsage:
    """Current disk usage statistics."""
    total_gb: float
    used_gb: float
    available_gb: float
    usage_percent: float
    research_data_gb: float
    expert_models_gb: float
    temp_files_gb: float
    checked_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class QuotaStatus:
    """Quota check result."""
    within_quota: bool
    usage_percent: float
    alert_level: str  # "ok", "warning", "critical", "paused"
    message: str


@dataclass
class CompressionResult:
    """Result of compression operation."""
    files_compressed: int
    bytes_before: int
    bytes_after: int
    compression_ratio: float
    duration_seconds: float


@dataclass
class UploadResult:
    """Result of MinIO upload operation."""
    files_uploaded: int
    total_bytes: int
    object_urls: List[str]
    duration_seconds: float


class DiskQuotaManager:
    """
    Manages disk space for research pipeline.

    Features:
    - Quota monitoring with alerts
    - Automatic compression of old data
    - MinIO cold storage uploads
    - Cleanup of temporary files
    """

    # Default thresholds
    DEFAULT_QUOTA_GB = 500.0
    ALERT_THRESHOLD_PERCENT = 80.0
    PAUSE_THRESHOLD_PERCENT = 95.0

    def __init__(
        self,
        research_data_dir: str = "/Users/Shared/Coding/KITT/.research_data",
        expert_models_dir: str = "/Users/Shared/Coding/KITT/.expert_models",
        quota_gb: float = DEFAULT_QUOTA_GB,
        minio_endpoint: str = "localhost:9000",
        minio_bucket: str = "kitty-research",
        minio_access_key: Optional[str] = None,
        minio_secret_key: Optional[str] = None,
    ):
        self.research_data_dir = Path(research_data_dir)
        self.expert_models_dir = Path(expert_models_dir)
        self.quota_gb = quota_gb
        self.minio_endpoint = minio_endpoint
        self.minio_bucket = minio_bucket
        self.minio_access_key = minio_access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.minio_secret_key = minio_secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")

        # Ensure directories exist
        self.research_data_dir.mkdir(parents=True, exist_ok=True)
        self.expert_models_dir.mkdir(parents=True, exist_ok=True)

    async def get_usage(self) -> DiskUsage:
        """
        Get current disk usage statistics.

        Returns:
            DiskUsage with current statistics
        """
        try:
            # Get overall disk usage using df
            result = subprocess.run(
                ["df", "-g", str(self.research_data_dir)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                raise RuntimeError(f"df failed: {result.stderr}")

            # Parse df output
            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                raise ValueError("Unexpected df output")

            # Parse second line (first is header)
            parts = lines[1].split()
            total_gb = float(parts[1])  # 1024-blocks
            used_gb = float(parts[2])
            available_gb = float(parts[3])
            usage_percent = (used_gb / total_gb * 100) if total_gb > 0 else 0

            # Calculate directory-specific usage
            research_data_gb = await self._get_dir_size_gb(self.research_data_dir)
            expert_models_gb = await self._get_dir_size_gb(self.expert_models_dir)

            # Temp files in research data
            temp_dir = self.research_data_dir / "temp"
            temp_files_gb = await self._get_dir_size_gb(temp_dir) if temp_dir.exists() else 0.0

            return DiskUsage(
                total_gb=total_gb,
                used_gb=used_gb,
                available_gb=available_gb,
                usage_percent=round(usage_percent, 1),
                research_data_gb=round(research_data_gb, 2),
                expert_models_gb=round(expert_models_gb, 2),
                temp_files_gb=round(temp_files_gb, 2),
            )

        except Exception as e:
            logger.error(f"Failed to get disk usage: {e}")
            # Return fallback values
            return DiskUsage(
                total_gb=1000.0,
                used_gb=500.0,
                available_gb=500.0,
                usage_percent=50.0,
                research_data_gb=0.0,
                expert_models_gb=0.0,
                temp_files_gb=0.0,
            )

    async def _get_dir_size_gb(self, path: Path) -> float:
        """Get directory size in GB using du."""
        if not path.exists():
            return 0.0

        try:
            result = subprocess.run(
                ["du", "-sg", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                size_gb = float(result.stdout.split()[0])
                return size_gb

        except Exception as e:
            logger.debug(f"Failed to get size for {path}: {e}")

        return 0.0

    async def check_quota(self) -> QuotaStatus:
        """
        Check if usage is within quota.

        Returns:
            QuotaStatus with check result
        """
        usage = await self.get_usage()

        # Calculate research-specific usage against quota
        research_usage_gb = usage.research_data_gb + usage.expert_models_gb
        usage_percent = (research_usage_gb / self.quota_gb * 100) if self.quota_gb > 0 else 0

        if usage_percent >= self.PAUSE_THRESHOLD_PERCENT:
            return QuotaStatus(
                within_quota=False,
                usage_percent=round(usage_percent, 1),
                alert_level="paused",
                message=f"CRITICAL: Research storage at {usage_percent:.1f}% ({research_usage_gb:.1f}GB / {self.quota_gb}GB). Pipeline paused.",
            )
        elif usage_percent >= self.ALERT_THRESHOLD_PERCENT:
            return QuotaStatus(
                within_quota=True,
                usage_percent=round(usage_percent, 1),
                alert_level="warning",
                message=f"WARNING: Research storage at {usage_percent:.1f}%. Consider archiving old data.",
            )
        else:
            return QuotaStatus(
                within_quota=True,
                usage_percent=round(usage_percent, 1),
                alert_level="ok",
                message=f"Storage OK: {usage_percent:.1f}% used ({research_usage_gb:.1f}GB / {self.quota_gb}GB)",
            )

    async def compress_old_data(
        self,
        age_days: int = 30,
        dry_run: bool = False,
    ) -> CompressionResult:
        """
        Compress old research data files.

        Compresses PDF files and JSON data older than age_days.

        Args:
            age_days: Files older than this will be compressed
            dry_run: If True, only report what would be done

        Returns:
            CompressionResult with statistics
        """
        start_time = datetime.utcnow()
        cutoff_date = datetime.utcnow() - timedelta(days=age_days)

        files_compressed = 0
        bytes_before = 0
        bytes_after = 0

        # Find old files to compress
        patterns = ["**/*.pdf", "**/*.json"]
        exclude_patterns = ["*.gz", "registry.json", "checkpoint*"]

        for pattern in patterns:
            for file_path in self.research_data_dir.glob(pattern):
                # Skip already compressed
                if file_path.suffix == ".gz":
                    continue

                # Skip excluded patterns
                if any(file_path.match(exc) for exc in exclude_patterns):
                    continue

                # Check modification time
                try:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime > cutoff_date:
                        continue

                    file_size = file_path.stat().st_size
                    bytes_before += file_size

                    if dry_run:
                        files_compressed += 1
                        bytes_after += int(file_size * 0.3)  # Estimate
                        continue

                    # Compress file
                    compressed_path = Path(str(file_path) + ".gz")
                    with open(file_path, "rb") as f_in:
                        with gzip.open(compressed_path, "wb", compresslevel=6) as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    # Verify and remove original
                    if compressed_path.exists():
                        bytes_after += compressed_path.stat().st_size
                        file_path.unlink()
                        files_compressed += 1
                        logger.debug(f"Compressed: {file_path}")

                except Exception as e:
                    logger.warning(f"Failed to compress {file_path}: {e}")

        duration = (datetime.utcnow() - start_time).total_seconds()
        compression_ratio = (bytes_after / bytes_before) if bytes_before > 0 else 1.0

        logger.info(
            f"Compression complete: {files_compressed} files, "
            f"{bytes_before / 1e6:.1f}MB -> {bytes_after / 1e6:.1f}MB "
            f"({compression_ratio:.1%})"
        )

        return CompressionResult(
            files_compressed=files_compressed,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            compression_ratio=compression_ratio,
            duration_seconds=round(duration, 2),
        )

    async def upload_to_minio(
        self,
        local_path: str,
        object_name: Optional[str] = None,
    ) -> str:
        """
        Upload a file or directory to MinIO cold storage.

        Args:
            local_path: Path to file or directory
            object_name: Object name in bucket (defaults to basename)

        Returns:
            Object URL in MinIO
        """
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"Path not found: {local_path}")

        if object_name is None:
            object_name = local_path.name

        # Use mc (MinIO client) if available
        mc_path = shutil.which("mc")

        if mc_path:
            return await self._upload_with_mc(local_path, object_name)
        else:
            return await self._upload_with_minio_client(local_path, object_name)

    async def _upload_with_mc(
        self,
        local_path: Path,
        object_name: str,
    ) -> str:
        """Upload using MinIO client (mc)."""
        # Configure mc alias if needed
        alias = "kitty"
        minio_url = f"http://{self.minio_endpoint}"

        # Set alias
        subprocess.run(
            ["mc", "alias", "set", alias, minio_url, self.minio_access_key, self.minio_secret_key],
            capture_output=True,
            timeout=10,
        )

        # Ensure bucket exists
        subprocess.run(
            ["mc", "mb", "-p", f"{alias}/{self.minio_bucket}"],
            capture_output=True,
            timeout=10,
        )

        # Upload
        dest = f"{alias}/{self.minio_bucket}/{object_name}"

        if local_path.is_dir():
            cmd = ["mc", "cp", "--recursive", str(local_path), dest]
        else:
            cmd = ["mc", "cp", str(local_path), dest]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min for large files
        )

        if result.returncode != 0:
            raise RuntimeError(f"Upload failed: {result.stderr}")

        return f"s3://{self.minio_bucket}/{object_name}"

    async def _upload_with_minio_client(
        self,
        local_path: Path,
        object_name: str,
    ) -> str:
        """Upload using minio Python client."""
        try:
            from minio import Minio

            client = Minio(
                self.minio_endpoint,
                access_key=self.minio_access_key,
                secret_key=self.minio_secret_key,
                secure=False,
            )

            # Ensure bucket exists
            if not client.bucket_exists(self.minio_bucket):
                client.make_bucket(self.minio_bucket)

            if local_path.is_file():
                client.fput_object(
                    self.minio_bucket,
                    object_name,
                    str(local_path),
                )
            else:
                # Upload directory recursively
                for file_path in local_path.rglob("*"):
                    if file_path.is_file():
                        relative = file_path.relative_to(local_path)
                        obj_name = f"{object_name}/{relative}"
                        client.fput_object(
                            self.minio_bucket,
                            obj_name,
                            str(file_path),
                        )

            return f"s3://{self.minio_bucket}/{object_name}"

        except ImportError:
            raise RuntimeError("minio package not installed. Install with: pip install minio")

    async def cleanup_temp_files(
        self,
        max_age_hours: int = 24,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Clean up temporary files.

        Args:
            max_age_hours: Remove files older than this
            dry_run: Only report what would be deleted

        Returns:
            Cleanup statistics
        """
        temp_dir = self.research_data_dir / "temp"
        if not temp_dir.exists():
            return {"files_deleted": 0, "bytes_freed": 0}

        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        files_deleted = 0
        bytes_freed = 0

        for file_path in temp_dir.rglob("*"):
            if not file_path.is_file():
                continue

            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime > cutoff:
                    continue

                file_size = file_path.stat().st_size

                if not dry_run:
                    file_path.unlink()

                files_deleted += 1
                bytes_freed += file_size

            except Exception as e:
                logger.warning(f"Failed to clean {file_path}: {e}")

        logger.info(f"Cleanup: removed {files_deleted} temp files ({bytes_freed / 1e6:.1f}MB)")

        return {
            "files_deleted": files_deleted,
            "bytes_freed": bytes_freed,
            "dry_run": dry_run,
        }

    async def archive_topic_data(
        self,
        topic_id: str,
        upload_to_cold: bool = True,
    ) -> Dict[str, Any]:
        """
        Archive all data for a research topic.

        Compresses and optionally uploads to MinIO.

        Args:
            topic_id: Topic ID to archive
            upload_to_cold: Whether to upload to MinIO

        Returns:
            Archive statistics
        """
        topic_dir = self.research_data_dir / "topics" / topic_id

        if not topic_dir.exists():
            return {"error": f"Topic directory not found: {topic_id}"}

        # Create archive
        archive_name = f"topic-{topic_id}-{datetime.utcnow().strftime('%Y%m%d')}"
        archive_path = self.research_data_dir / "archives" / f"{archive_name}.tar.gz"
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Create tarball
        result = subprocess.run(
            ["tar", "-czf", str(archive_path), "-C", str(topic_dir.parent), topic_id],
            capture_output=True,
            timeout=600,
        )

        if result.returncode != 0:
            return {"error": f"Archive failed: {result.stderr.decode()}"}

        archive_size = archive_path.stat().st_size

        response = {
            "topic_id": topic_id,
            "archive_path": str(archive_path),
            "archive_size_bytes": archive_size,
        }

        # Upload to MinIO
        if upload_to_cold:
            try:
                url = await self.upload_to_minio(
                    str(archive_path),
                    f"archives/{archive_name}.tar.gz"
                )
                response["minio_url"] = url

                # Remove local archive after successful upload
                archive_path.unlink()
                response["local_deleted"] = True

            except Exception as e:
                response["upload_error"] = str(e)

        return response


# Global instance
_manager: Optional[DiskQuotaManager] = None


def get_disk_quota_manager() -> DiskQuotaManager:
    """Get or create the global disk quota manager."""
    global _manager
    if _manager is None:
        _manager = DiskQuotaManager()
    return _manager
