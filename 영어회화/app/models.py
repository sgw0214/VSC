from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Dialogue(Base):
    __tablename__ = "dialogues"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    set_no: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    scene: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    key_patterns_json: Mapped[str] = mapped_column(Text, nullable=False)
    turns_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    review_item = relationship("ReviewItem", back_populates="dialogue", uselist=False)
    review_logs = relationship("ReviewLog", back_populates="dialogue")


class ReviewItem(Base):
    __tablename__ = "review_items"

    dialogue_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("dialogues.id", ondelete="CASCADE"),
        primary_key=True,
    )
    easiness: Mapped[float] = mapped_column(Float, default=2.5, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    repetitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, default=date.today, index=True, nullable=False)
    last_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    dialogue = relationship("Dialogue", back_populates="review_item")


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dialogue_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("dialogues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recalled_sentence: Mapped[str] = mapped_column(Text, default="", nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    dialogue = relationship("Dialogue", back_populates="review_logs")
