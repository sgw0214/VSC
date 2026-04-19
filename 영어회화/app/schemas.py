from datetime import date
from typing import List

from pydantic import BaseModel, Field


class DialogueTurn(BaseModel):
    speaker: str
    en: str
    ko: str


class DialogueOut(BaseModel):
    id: str
    set_no: int
    title: str
    level: str
    scene: str
    key_patterns: List[str]
    turns: List[DialogueTurn]


class ReviewQueueItem(BaseModel):
    dialogue: DialogueOut
    due_date: date
    interval_days: int
    repetitions: int
    easiness: float


class ReviewAttemptIn(BaseModel):
    dialogue_id: str
    recalled_sentence: str = ""
    score: int = Field(ge=0, le=5)


class ReviewAttemptOut(BaseModel):
    dialogue_id: str
    due_date: date
    interval_days: int
    repetitions: int
    easiness: float
    last_score: int


class ReviewResetIn(BaseModel):
    dialogue_id: str


class StatsOut(BaseModel):
    total_dialogues: int
    due_today: int
    reviewed_today: int
