import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Dialogue, ReviewItem


def seed_dialogues(db: Session, seed_path: Path) -> int:
    existing = db.scalar(select(Dialogue.id).limit(1))
    if existing:
        return 0

    raw = json.loads(seed_path.read_text(encoding="utf-8-sig"))
    dialogues = raw.get("dialogues", [])
    seeded = 0

    for item in dialogues:
        dialogue = Dialogue(
            id=item["id"],
            set_no=item["set_no"],
            title=item["title"],
            level=item["level"],
            scene=item["scene"],
            key_patterns_json=json.dumps(item["key_patterns"], ensure_ascii=False),
            turns_json=json.dumps(item["turns"], ensure_ascii=False),
        )
        review = ReviewItem(
            dialogue_id=item["id"],
            due_date=date.today(),
            interval_days=1,
            repetitions=0,
            easiness=2.5,
            last_score=0,
        )
        db.add(dialogue)
        db.add(review)
        seeded += 1

    db.commit()
    return seeded
