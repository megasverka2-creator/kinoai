"""Loyihalarni saqlash.

MVP'da JSON fayllar. TZ 17 dagi PostgreSQL sxemasi Phase 0 da keladi,
ammo maydonlar nomi hozirdanoq bir xil — ko'chirish oson bo'lsin.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"


def _dir(user_id: int) -> Path:
    d = ROOT / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_project(user_id: int, kind: str, target_seconds: int,
                aspect: str = "9:16", mode: str = "easy") -> dict:
    d = _dir(user_id)
    n = len(list(d.glob("PRJ*.json"))) + 1
    pid = f"PRJ{n:03d}"
    proj = {
        "id": pid,
        "user_id": user_id,
        "kind": kind,
        "mode": mode,
        "target_seconds": target_seconds,
        "aspect": aspect,
        "quality": "balanced",
        "stage": "brief",
        "status": "draft",
        "idea": "",
        "must_keep": [],
        "concept": {},
        "screenplay": {},
        "shots": [],
        "style": {},
        "versions": {},      # stage_key -> [ {n, content, status, at} ]
        "ledger": [],
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    save(proj)
    return proj


def path_of(user_id: int, pid: str) -> Path:
    return _dir(user_id) / f"{pid}.json"


def save(proj: dict) -> None:
    proj["updated_at"] = time.time()
    path_of(proj["user_id"], proj["id"]).write_text(
        json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load(user_id: int, pid: str) -> dict | None:
    p = path_of(user_id, pid)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def list_projects(user_id: int) -> list[dict]:
    out = []
    for f in sorted(_dir(user_id).glob("PRJ*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return sorted(out, key=lambda p: p.get("updated_at", 0), reverse=True)


def latest(user_id: int) -> dict | None:
    ps = list_projects(user_id)
    return ps[0] if ps else None


# ------------------------------------------------------------- versiyalash

def add_version(proj: dict, stage_key: str, content: dict,
                source: str = "ai", note: str = "") -> dict:
    """Yangi versiya. Eskisi O'CHIRILMAYDI. TZ 2.4."""
    vs = proj.setdefault("versions", {}).setdefault(stage_key, [])
    v = {
        "n": len(vs) + 1,
        "content": content,
        "status": "draft",
        "source": source,
        "note": note,
        "at": time.time(),
    }
    vs.append(v)
    return v


def current_version(proj: dict, stage_key: str) -> dict | None:
    vs = proj.get("versions", {}).get(stage_key, [])
    for v in reversed(vs):
        if v["status"] in ("approved", "locked"):
            return v
    return vs[-1] if vs else None


def approve(proj: dict, stage_key: str, lock: bool = True) -> dict | None:
    vs = proj.get("versions", {}).get(stage_key, [])
    if not vs:
        return None
    vs[-1]["status"] = "locked" if lock else "approved"
    return vs[-1]


def add_cost(proj: dict, action: str, provider: str,
             cost: float, model: str = "") -> None:
    proj.setdefault("ledger", []).append({
        "action": action, "provider": provider, "model": model,
        "cost": cost, "at": time.time(),
    })


def total_cost(proj: dict) -> float:
    return sum(e.get("cost", 0.0) for e in proj.get("ledger", []))
