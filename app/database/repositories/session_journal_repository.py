from sqlalchemy import select

from app.database.database import SessionLocal
from app.database.models.session_journal_entry import SessionJournalEntry


class SessionJournalRepository:
    @staticmethod
    def add(entry: SessionJournalEntry) -> SessionJournalEntry:
        with SessionLocal() as session:
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    @staticmethod
    def get_by_project(project_id: int) -> list[SessionJournalEntry]:
        with SessionLocal() as session:
            return list(
                session.scalars(
                    select(SessionJournalEntry)
                    .where(SessionJournalEntry.project_id == project_id)
                    .order_by(
                        SessionJournalEntry.created_at_utc,
                        SessionJournalEntry.id,
                    )
                )
            )

    @staticmethod
    def get_latest(project_id: int) -> SessionJournalEntry | None:
        with SessionLocal() as session:
            return session.scalar(
                select(SessionJournalEntry)
                .where(SessionJournalEntry.project_id == project_id)
                .order_by(
                    SessionJournalEntry.created_at_utc.desc(),
                    SessionJournalEntry.id.desc(),
                )
                .limit(1)
            )

    @staticmethod
    def get_by_entry_uuid(entry_uuid: str) -> SessionJournalEntry | None:
        with SessionLocal() as session:
            return session.scalar(
                select(SessionJournalEntry).where(
                    SessionJournalEntry.entry_uuid == entry_uuid
                )
            )
