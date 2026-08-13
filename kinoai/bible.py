"""Bible — qayta ishlatiladigan continuity.

Serial qilish uchun TZ dagi Universe/Series/Season/Episode iyerarxiyasi
KERAK EMAS. U ma'lumotlar modelini bir necha barobar murakkablashtiradi
va MVP'da qiymat bermaydi.

Buning o'rniga oddiy narsa: Fast plan ichidagi `continuity` blokini
loyihadan ajratib, alohida saqlash. Yangi loyiha ochilganda foydalanuvchi
mavjud Bible'ni tanlaydi — personajlar, lokatsiyalar va uslub bir xil
qoladi. Ssenariy esa yangi bo'ladi.

50 qator kod, serialning 80% qiymati.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"


def _dir(user_id: int) -> Path:
    d = ROOT / str(user_id) / "bibles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create(user_id: int, name: str, continuity: dict,
           source_project: str = "") -> dict:
    """Tasdiqlangan loyihadan Bible yaratadi."""
    d = _dir(user_id)
    n = len(list(d.glob("BIB*.json"))) + 1
    bid = f"BIB{n:03d}"
    b = {
        "id": bid,
        "user_id": user_id,
        "name": name or f"Bible {n}",
        "continuity": continuity,
        "source_project": source_project,
        "episodes": [],
        "created_at": time.time(),
    }
    save(b)
    return b


def save(b: dict) -> None:
    (_dir(b["user_id"]) / f"{b['id']}.json").write_text(
        json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load(user_id: int, bid: str) -> dict | None:
    p = _dir(user_id) / f"{bid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def list_bibles(user_id: int) -> list[dict]:
    out = []
    for f in sorted(_dir(user_id).glob("BIB*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return sorted(out, key=lambda b: b.get("created_at", 0), reverse=True)


def add_episode(b: dict, project_id: str, title: str) -> None:
    b.setdefault("episodes", []).append({
        "project_id": project_id,
        "title": title,
        "n": len(b.get("episodes", [])) + 1,
        "at": time.time(),
    })
    save(b)


def summary(b: dict) -> str:
    c = b.get("continuity", {})
    chars = c.get("characters", [])
    locs = c.get("locations", [])
    eps = b.get("episodes", [])
    names = ", ".join(
        x.get("name", "?") for x in chars if isinstance(x, dict)
    )[:120]
    return (
        f"<b>{b.get('name')}</b>  ({b.get('id')})\n"
        f"Personajlar: {names or '—'}\n"
        f"Lokatsiyalar: {len(locs)} ta\n"
        f"Epizodlar: {len(eps)} ta"
    )


def as_context(b: dict) -> dict:
    """Planning call uchun kontekst.

    MUHIM: bu blok o'zgarmas deb beriladi. AI faqat yangi ssenariy
    yozadi, personajlarni qayta o'ylab topmaydi.
    """
    c = b.get("continuity", {})
    return {
        "locked_continuity": c,
        "previous_episodes": [
            e.get("title", "") for e in b.get("episodes", [])
        ][-5:],
        "instruction": (
            "Bu personajlar, lokatsiyalar va uslub OLDIN tasdiqlangan. "
            "Ularning visual_identity va wardrobe tavsifini AYNAN "
            "o'zgartirmasdan ishlat. Faqat yangi ssenariy va yangi "
            "kadrlar yoz."
        ),
    }
