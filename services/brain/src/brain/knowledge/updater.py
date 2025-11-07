"""Knowledge base updater for autonomous content generation."""
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import frontmatter
import structlog

logger = structlog.get_logger()


class KnowledgeUpdater:
    """Manages creating and updating knowledge base content."""

    def __init__(self, knowledge_base_path: Optional[Path] = None):
        """Initialize knowledge updater.

        Args:
            knowledge_base_path: Path to knowledge base directory (default: repo_root/knowledge)
        """
        if knowledge_base_path is None:
            # Assume we're running from services/brain/src, go up to repo root
            current_file = Path(__file__)
            repo_root = current_file.parent.parent.parent.parent.parent.parent
            knowledge_base_path = repo_root / "knowledge"

        self.kb_path = Path(knowledge_base_path)
        self.materials_path = self.kb_path / "materials"
        self.techniques_path = self.kb_path / "techniques"
        self.equipment_path = self.kb_path / "equipment"
        self.research_path = self.kb_path / "research"

        # Ensure directories exist
        for path in [
            self.materials_path,
            self.techniques_path,
            self.equipment_path,
            self.research_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)

        logger.info("Knowledge updater initialized", kb_path=str(self.kb_path))

    def create_material(
        self,
        slug: str,
        name: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        auto_commit: bool = False,
    ) -> Path:
        """Create material documentation with YAML frontmatter.

        Args:
            slug: Filename slug (e.g., 'pla', 'petg-recycled')
            name: Full material name
            content: Markdown content body
            metadata: YAML frontmatter fields (cost_per_kg, density, etc.)
            auto_commit: Whether to auto-commit to git

        Returns:
            Path to created file
        """
        file_path = self.materials_path / f"{slug}.md"

        # Build frontmatter
        fm_data = metadata or {}
        if "cost_per_kg" not in fm_data:
            fm_data["cost_per_kg"] = None
        if "density" not in fm_data:
            fm_data["density"] = None
        if "print_temp" not in fm_data:
            fm_data["print_temp"] = None
        if "bed_temp" not in fm_data:
            fm_data["bed_temp"] = None
        if "sustainability_score" not in fm_data:
            fm_data["sustainability_score"] = None
        if "suppliers" not in fm_data:
            fm_data["suppliers"] = []

        # Create frontmatter document
        post = frontmatter.Post(content)
        post.metadata = fm_data

        # Write to file
        with open(file_path, "w") as f:
            f.write(frontmatter.dumps(post))

        logger.info("Created material document", slug=slug, path=str(file_path))

        if auto_commit:
            self._git_commit(
                file_path, f"KB: Add {name} material documentation (autonomous)"
            )

        return file_path

    def create_technique(
        self,
        slug: str,
        name: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        auto_commit: bool = False,
    ) -> Path:
        """Create technique guide.

        Args:
            slug: Filename slug (e.g., 'first-layer-adhesion')
            name: Full technique name
            content: Markdown content body
            metadata: Optional YAML frontmatter
            auto_commit: Whether to auto-commit to git

        Returns:
            Path to created file
        """
        file_path = self.techniques_path / f"{slug}.md"

        # Create frontmatter document (techniques have minimal metadata)
        fm_data = metadata or {}
        post = frontmatter.Post(content)
        post.metadata = fm_data

        # Write to file
        with open(file_path, "w") as f:
            f.write(frontmatter.dumps(post))

        logger.info("Created technique guide", slug=slug, path=str(file_path))

        if auto_commit:
            self._git_commit(
                file_path, f"KB: Add {name} technique guide (autonomous)"
            )

        return file_path

    def create_research_article(
        self,
        topic: str,
        content: str,
        goal_id: Optional[str] = None,
        project_id: Optional[str] = None,
        cost_usd: Optional[float] = None,
        sources: Optional[List[str]] = None,
        auto_commit: bool = True,
    ) -> Path:
        """Create autonomous research article.

        Args:
            topic: Research topic (e.g., 'sustainable-filament-suppliers')
            content: Markdown content body
            goal_id: Associated Goal UUID
            project_id: Associated Project UUID
            cost_usd: Research API cost
            sources: List of source URLs
            auto_commit: Whether to auto-commit to git (default: True for research)

        Returns:
            Path to created file
        """
        # Generate filename: YYYY-Www-topic-slug.md
        now = datetime.utcnow()
        week_num = now.isocalendar()[1]
        slug = self._slugify(topic)
        filename = f"{now.year}-W{week_num:02d}-{slug}.md"
        file_path = self.research_path / filename

        # Build frontmatter
        fm_data = {
            "generated_date": now.isoformat() + "Z",
            "topic": topic,
            "goal_id": goal_id,
            "project_id": project_id,
            "cost_usd": cost_usd,
            "sources": sources or [],
        }

        # Create frontmatter document
        post = frontmatter.Post(content)
        post.metadata = fm_data

        # Write to file
        with open(file_path, "w") as f:
            f.write(frontmatter.dumps(post))

        logger.info(
            "Created research article",
            topic=topic,
            filename=filename,
            path=str(file_path),
        )

        if auto_commit:
            self._git_commit(file_path, f"KB: autonomous update - {topic}")

        return file_path

    def update_material(
        self, slug: str, updates: Dict[str, Any], auto_commit: bool = False
    ) -> Path:
        """Update existing material documentation.

        Args:
            slug: Material slug
            updates: Dictionary of fields to update (frontmatter or content)
            auto_commit: Whether to auto-commit

        Returns:
            Path to updated file
        """
        file_path = self.materials_path / f"{slug}.md"
        if not file_path.exists():
            raise FileNotFoundError(f"Material {slug} not found at {file_path}")

        # Load existing document
        with open(file_path, "r") as f:
            post = frontmatter.load(f)

        # Update frontmatter
        if "metadata" in updates:
            post.metadata.update(updates["metadata"])

        # Update content if provided
        if "content" in updates:
            post.content = updates["content"]

        # Write back
        with open(file_path, "w") as f:
            f.write(frontmatter.dumps(post))

        logger.info("Updated material document", slug=slug, path=str(file_path))

        if auto_commit:
            self._git_commit(file_path, f"KB: Update {slug} material (autonomous)")

        return file_path

    def _slugify(self, text: str) -> str:
        """Convert text to URL-friendly slug.

        Args:
            text: Input text

        Returns:
            Slugified text
        """
        # Convert to lowercase and replace spaces/special chars with hyphens
        slug = re.sub(r"[^\w\s-]", "", text.lower())
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug.strip("-")

    def _git_commit(self, file_path: Path, message: str) -> bool:
        """Commit file to git with message.

        Args:
            file_path: Path to file to commit
            message: Commit message

        Returns:
            True if commit succeeded, False otherwise
        """
        try:
            # Get relative path from repo root
            rel_path = file_path.relative_to(self.kb_path.parent)

            # Git add
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=self.kb_path.parent,
                check=True,
                capture_output=True,
            )

            # Git commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.kb_path.parent,
                check=True,
                capture_output=True,
            )

            logger.info("Git commit successful", file=str(rel_path), message=message)
            return True

        except subprocess.CalledProcessError as e:
            logger.error(
                "Git commit failed",
                file=str(file_path),
                error=e.stderr.decode() if e.stderr else str(e),
            )
            return False

    def list_materials(self) -> List[str]:
        """List all material slugs in knowledge base.

        Returns:
            List of material slugs
        """
        return [f.stem for f in self.materials_path.glob("*.md")]

    def list_techniques(self) -> List[str]:
        """List all technique slugs in knowledge base.

        Returns:
            List of technique slugs
        """
        return [f.stem for f in self.techniques_path.glob("*.md")]

    def list_research(self) -> List[str]:
        """List all research article filenames.

        Returns:
            List of research filenames (with .md extension)
        """
        return [f.name for f in self.research_path.glob("*.md")]


__all__ = ["KnowledgeUpdater"]
