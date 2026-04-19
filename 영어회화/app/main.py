import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .audio import ensure_dialogue_wav, ensure_playlist_wav
from .models import Dialogue, ReviewItem, ReviewLog
from .schemas import (
    DialogueOut,
    ReviewAttemptIn,
    ReviewAttemptOut,
    ReviewQueueItem,
    ReviewResetIn,
    StatsOut,
)
from .seed import seed_dialogues

ROOT_DIR = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT_DIR / "data" / "dialogues_seed.json"
SPEECH_CACHE_DIR = ROOT_DIR / "data" / "audio_cache"
STATIC_DIR = ROOT_DIR / "static"
SERVER_BOOT_ID = uuid.uuid4().hex

app = FastAPI(title="English Conversation Memorizer", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def serialize_dialogue(row: Dialogue) -> DialogueOut:
    return DialogueOut(
        id=row.id,
        set_no=row.set_no,
        title=row.title,
        level=row.level,
        scene=row.scene,
        key_patterns=json.loads(row.key_patterns_json),
        turns=json.loads(row.turns_json),
    )


def apply_srs(review: ReviewItem, score: int) -> None:
    today = date.today()
    if score < 3:
        review.repetitions = 0
        review.interval_days = 1
    else:
        if review.repetitions == 0:
            review.interval_days = 1
        elif review.repetitions == 1:
            review.interval_days = 3
        else:
            review.interval_days = max(1, round(review.interval_days * review.easiness))
        review.repetitions += 1

    quality_gap = 5 - score
    review.easiness = max(
        1.3,
        review.easiness + (0.1 - quality_gap * (0.08 + quality_gap * 0.02)),
    )
    review.last_score = score
    review.due_date = today + timedelta(days=review.interval_days)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if SEED_PATH.exists():
            seed_dialogues(db, SEED_PATH)


@app.get("/", include_in_schema=False)
def read_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Dialogue.id))) or 0
    return {
        "status": "ok",
        "dialogue_count": total,
        "server_boot_id": SERVER_BOOT_ID,
    }


@app.get("/api/scenes")
def list_scenes(db: Session = Depends(get_db)):
    rows = db.execute(select(distinct(Dialogue.scene)).order_by(Dialogue.scene)).all()
    return [scene for (scene,) in rows]


@app.get("/api/dialogues", response_model=List[DialogueOut])
def list_dialogues(
    level: Optional[str] = Query(default=None),
    scene: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Dialogue).order_by(Dialogue.set_no).limit(limit)
    filters = []
    if level:
        filters.append(Dialogue.level == level)
    if scene:
        filters.append(Dialogue.scene == scene)
    if filters:
        stmt = stmt.where(and_(*filters))

    rows = db.scalars(stmt).all()
    return [serialize_dialogue(item) for item in rows]


@app.get("/api/dialogues/{dialogue_id}", response_model=DialogueOut)
def get_dialogue(dialogue_id: str, db: Session = Depends(get_db)):
    row = db.get(Dialogue, dialogue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Dialogue not found")
    return serialize_dialogue(row)


@app.get("/api/audio/dialogue/{dialogue_id}.wav", include_in_schema=False)
def get_dialogue_audio(dialogue_id: str, db: Session = Depends(get_db)):
    row = db.get(Dialogue, dialogue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Dialogue not found")

    turns = json.loads(row.turns_json)
    try:
        wav_path = ensure_dialogue_wav(SPEECH_CACHE_DIR, dialogue_id, turns)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Audio synthesis failed: {exc}")

    return FileResponse(
        wav_path,
        media_type="audio/wav",
        filename=f"{dialogue_id}.wav",
    )


@app.get("/api/audio/playlist.wav", include_in_schema=False)
def get_playlist_audio(ids: str = Query(default=""), db: Session = Depends(get_db)):
    dialogue_ids = [item.strip() for item in ids.split(",") if item.strip()]
    if not dialogue_ids:
        raise HTTPException(status_code=400, detail="No dialogue ids provided.")
    if len(dialogue_ids) > 50:
        raise HTTPException(status_code=400, detail="Too many dialogue ids.")

    rows = db.scalars(select(Dialogue).where(Dialogue.id.in_(dialogue_ids))).all()
    row_map = {row.id: row for row in rows}

    source_files = []
    ordered_ids = []
    for dialogue_id in dialogue_ids:
        row = row_map.get(dialogue_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Dialogue not found: {dialogue_id}")
        turns = json.loads(row.turns_json)
        try:
            wav_path = ensure_dialogue_wav(SPEECH_CACHE_DIR, dialogue_id, turns)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Audio synthesis failed: {exc}")
        source_files.append(wav_path)
        ordered_ids.append(dialogue_id)

    try:
        playlist_path = ensure_playlist_wav(SPEECH_CACHE_DIR / "playlist_cache", ordered_ids, source_files)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Playlist synthesis failed: {exc}")

    return FileResponse(
        playlist_path,
        media_type="audio/wav",
        filename="playlist.wav",
    )


@app.get("/api/review/next", response_model=List[ReviewQueueItem])
def next_reviews(
    limit: int = Query(default=200, ge=1, le=500),
    due_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    today = date.today()
    stmt = select(ReviewItem, Dialogue).join(Dialogue, Dialogue.id == ReviewItem.dialogue_id)
    if due_only:
        stmt = stmt.where(ReviewItem.due_date <= today)
    stmt = stmt.order_by(ReviewItem.due_date, Dialogue.set_no).limit(limit)
    pairs = db.execute(stmt).all()
    return [
        ReviewQueueItem(
            dialogue=serialize_dialogue(dialogue),
            due_date=review.due_date,
            interval_days=review.interval_days,
            repetitions=review.repetitions,
            easiness=review.easiness,
        )
        for review, dialogue in pairs
    ]


@app.post("/api/review/attempt", response_model=ReviewAttemptOut)
def submit_attempt(payload: ReviewAttemptIn, db: Session = Depends(get_db)):
    dialogue = db.get(Dialogue, payload.dialogue_id)
    if not dialogue:
        raise HTTPException(status_code=404, detail="Dialogue not found")

    review = db.get(ReviewItem, payload.dialogue_id)
    if not review:
        review = ReviewItem(dialogue_id=payload.dialogue_id, due_date=date.today())
        db.add(review)
        db.flush()

    review_log = ReviewLog(
        dialogue_id=payload.dialogue_id,
        recalled_sentence=payload.recalled_sentence.strip(),
        score=payload.score,
        attempt_at=datetime.now(),
    )
    db.add(review_log)

    apply_srs(review, payload.score)
    db.commit()
    db.refresh(review)

    return ReviewAttemptOut(
        dialogue_id=payload.dialogue_id,
        due_date=review.due_date,
        interval_days=review.interval_days,
        repetitions=review.repetitions,
        easiness=review.easiness,
        last_score=review.last_score,
    )


@app.post("/api/review/reset", response_model=ReviewAttemptOut)
def reset_review(payload: ReviewResetIn, db: Session = Depends(get_db)):
    dialogue = db.get(Dialogue, payload.dialogue_id)
    if not dialogue:
        raise HTTPException(status_code=404, detail="Dialogue not found")

    review = db.get(ReviewItem, payload.dialogue_id)
    if not review:
        review = ReviewItem(dialogue_id=payload.dialogue_id, due_date=date.today())
        db.add(review)

    review.due_date = date.today()
    review.interval_days = 1
    review.repetitions = 0
    review.easiness = 2.5
    review.last_score = 0
    review.updated_at = datetime.now()

    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)
    latest_today_log = db.scalar(
        select(ReviewLog)
        .where(
            and_(
                ReviewLog.dialogue_id == payload.dialogue_id,
                ReviewLog.attempt_at >= today_start,
                ReviewLog.attempt_at < tomorrow_start,
            )
        )
        .order_by(ReviewLog.attempt_at.desc())
        .limit(1)
    )
    if latest_today_log:
        db.delete(latest_today_log)

    db.commit()
    db.refresh(review)

    return ReviewAttemptOut(
        dialogue_id=payload.dialogue_id,
        due_date=review.due_date,
        interval_days=review.interval_days,
        repetitions=review.repetitions,
        easiness=review.easiness,
        last_score=review.last_score,
    )


@app.get("/api/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    today = date.today()

    total_dialogues = db.scalar(select(func.count(Dialogue.id))) or 0
    due_today = db.scalar(
        select(func.count(ReviewItem.dialogue_id)).where(ReviewItem.due_date <= today)
    ) or 0
    reviewed_today = db.scalar(
        select(func.count(ReviewItem.dialogue_id)).where(ReviewItem.due_date > today)
    ) or 0

    return StatsOut(
        total_dialogues=total_dialogues,
        due_today=due_today,
        reviewed_today=reviewed_today,
    )
