from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


class ProjectVersion(Base):
    __tablename__ = "project_versions"

    id: Mapped[int] = mapped_column(primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    created_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
    )

    package_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    backup_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    package_checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_versions.id"),
        nullable=True,
    )

    lineage_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="main",
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    project = relationship("Project")

    parent_version = relationship(
        "ProjectVersion",
        remote_side=[id],
    )