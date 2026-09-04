from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


class SessionJournalEntry(Base):
    __tablename__ = "session_journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_uuid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_version_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    project = relationship("Project")
