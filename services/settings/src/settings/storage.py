"""PostgreSQL storage for settings."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .models import AppSettings, UserSettingsRecord

logger = logging.getLogger(__name__)

Base = declarative_base()


class SettingsTable(Base):
    """SQLAlchemy model for settings storage."""

    __tablename__ = "user_settings"

    user_id = Column(String(255), primary_key=True)
    settings_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version = Column(Integer, default=1)


class SettingsStorage:
    """PostgreSQL-backed settings storage."""

    def __init__(self, database_url: Optional[str] = None):
        self._database_url = database_url or os.getenv(
            "DATABASE_URL", "postgresql://kitty:changeme@localhost:5432/kitty"
        )
        self._engine = create_engine(self._database_url)
        self._session_factory = sessionmaker(bind=self._engine)

        # Create table if not exists
        Base.metadata.create_all(self._engine)
        logger.info("Settings storage initialized")

    def get_settings(self, user_id: str) -> Optional[UserSettingsRecord]:
        """Get settings for a user."""
        with self._session_factory() as session:
            row = session.query(SettingsTable).filter_by(user_id=user_id).first()
            if not row:
                return None

            settings_data = json.loads(row.settings_json)
            return UserSettingsRecord(
                user_id=row.user_id,
                settings=AppSettings(**settings_data),
                created_at=row.created_at,
                updated_at=row.updated_at,
                version=row.version,
            )

    def save_settings(
        self,
        user_id: str,
        settings: AppSettings,
        version: Optional[int] = None,
    ) -> UserSettingsRecord:
        """Save settings for a user."""
        with self._session_factory() as session:
            row = session.query(SettingsTable).filter_by(user_id=user_id).first()

            settings_json = settings.model_dump_json()
            now = datetime.utcnow()

            if row:
                # Update existing
                row.settings_json = settings_json
                row.updated_at = now
                row.version = (version or row.version) + 1
            else:
                # Create new
                row = SettingsTable(
                    user_id=user_id,
                    settings_json=settings_json,
                    created_at=now,
                    updated_at=now,
                    version=version or 1,
                )
                session.add(row)

            session.commit()
            session.refresh(row)

            return UserSettingsRecord(
                user_id=row.user_id,
                settings=settings,
                created_at=row.created_at,
                updated_at=row.updated_at,
                version=row.version,
            )

    def delete_settings(self, user_id: str) -> bool:
        """Delete settings for a user."""
        with self._session_factory() as session:
            deleted = (
                session.query(SettingsTable).filter_by(user_id=user_id).delete()
            )
            session.commit()
            return deleted > 0

    def get_or_create_default(self, user_id: str) -> UserSettingsRecord:
        """Get settings or create with defaults."""
        existing = self.get_settings(user_id)
        if existing:
            return existing

        return self.save_settings(user_id, AppSettings())


# Singleton instance
_storage: Optional[SettingsStorage] = None


def get_storage() -> SettingsStorage:
    """Get or create settings storage singleton."""
    global _storage
    if _storage is None:
        _storage = SettingsStorage()
    return _storage
