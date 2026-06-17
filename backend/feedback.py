"""Post-call remarks — visitors leave a note about the experience; I (the owner)
later pick which ones to showcase.

Storage is a plain append-only JSONL file next to the code: one feedback object
per line. No DB for a toy experiment. Each entry lands with `showcase=false`; I
flip that by hand (edit the line / a tiny script) for the ones worth featuring,
and the public showcase endpoint only returns those.
"""

import json
import os
import time
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "feedback.jsonl")


class Feedback(BaseModel):
    text: str
    name: str | None = None
    rating: int | None = None
    may_feature: bool = False   # the visitor's consent; I still choose per entry


@router.post("/feedback")
async def submit(fb: Feedback):
    entry = {
        "id": uuid.uuid4().hex[:12],
        "text": fb.text.strip()[:2000],
        "name": (fb.name or "").strip()[:80] or None,
        "rating": fb.rating,
        "may_feature": bool(fb.may_feature),
        "showcase": False,        # owner-controlled; never set true from the API
        "created_at": time.time(),
    }
    if not entry["text"]:
        return {"ok": False, "error": "empty"}
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}


@router.get("/feedback/showcase")
async def showcase():
    """Only the entries I've marked `showcase=true` — for a future testimonials
    strip on the page. Bad/half-written lines are skipped, never fatal."""
    items = []
    if os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("showcase"):
                    items.append({"text": e.get("text", ""), "name": e.get("name")})
    return {"items": items}
