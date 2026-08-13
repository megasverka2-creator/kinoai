"""Oxirgi freym ulanishi (end-frame chaining).

MUAMMO (test videosida ko'rindi):
  Har kadr faqat START rasmdan yaratilgan. Ya'ni 2-kadr 1-kadrning
  qayerda tugaganini BILMAYDI. Natijada to'rtta mustaqil klip
  yonma-yon qo'yilgan — film emas.

YECHIM:
  N-kadrning oxirgi freymini ajratib olib, N+1 uchun START rasm
  sifatida beriladi. Kadrlar tabiiy ulanadi.

XARAJAT: manfiy. 4 kadr uchun 4 emas, 1 ta rasm generatsiya qilinadi
— qolgan 3 tasi bepul, oldingi videodan olinadi.

Ikki strategiya bor, ikkalasi ham qo'llab-quvvatlanadi:
  chain   — to'liq ulanish (bir sahna ichida uzluksiz harakat)
  fresh   — yangi START rasm (sahna o'zgarganda kerak)
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg: {r.stderr[-800:]}")


def last_frame(video: str, out: str, back_off: float = 0.12) -> str:
    """Videoning oxirgi freymini rasm qilib saqlaydi.

    back_off — eng oxirgi freymdan bir oz oldin olamiz. Sabab: ko'p
    modelda oxirgi freym siqilishdan xiralashadi yoki qorayadi.
    """
    dur = duration(video)
    ts = max(0.0, dur - back_off)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-ss", f"{ts}", "-i", video,
          "-frames:v", "1", "-q:v", "2", out])
    return out


def duration(video: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def plan_chain(shots: list[dict]) -> list[dict]:
    """Har kadr uchun START manbasini belgilaydi.

    Qoida: sahna o'zgarmasa — oldingi kadrning oxiridan ulanadi.
    Sahna o'zgarsa — yangi rasm generatsiya qilinadi.
    """
    out = [dict(s) for s in shots]
    for i, s in enumerate(out):
        if i == 0:
            s["start_source"] = "generate"
            s["chain_from"] = ""
            continue
        prev = out[i - 1]
        same_scene = (
            str(s.get("scene_id") or s.get("scene") or "")
            == str(prev.get("scene_id") or prev.get("scene") or "")
        )
        if same_scene and not s.get("force_new_start"):
            s["start_source"] = "chain"
            s["chain_from"] = prev.get("shot_id") or prev.get("id") or ""
        else:
            s["start_source"] = "generate"
            s["chain_from"] = ""
    return out


def savings(shots: list[dict], per_image: float = 0.04) -> tuple[int, float]:
    """Nechta rasm generatsiyasi tejaladi."""
    chained = sum(1 for s in shots if s.get("start_source") == "chain")
    return chained, chained * per_image


def continuity_hint(prev: dict) -> str:
    """Keyingi kadr promptiga qo'shiladigan davomiylik ko'rsatmasi.

    Bu chain ishlatilmagan holatda ham foydali — model oldingi
    kadr qayerda tugaganini bilib turadi.
    """
    end = (prev.get("end_state") or prev.get("end_frame_en")
           or prev.get("action") or "")
    if not end:
        return ""
    return (f"This shot continues directly from the previous moment: "
            f"{str(end).strip().rstrip('.')}. Maintain identical character "
            f"positions, wardrobe, lighting and background at the start.")


def build_start_images(shots: list[dict], video_paths: dict[str, str],
                       workdir: str) -> dict[str, str]:
    """Tayyor videolardan zanjir rasmlarini ajratib oladi.

    video_paths: shot_id -> tayyor video fayli
    Qaytaradi: shot_id -> START rasm yo'li
    """
    d = Path(workdir)
    d.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    for s in shots:
        sid = s.get("shot_id") or s.get("id") or ""
        src = s.get("chain_from")
        if s.get("start_source") != "chain" or not src:
            continue
        v = video_paths.get(src)
        if not v or not Path(v).exists():
            continue
        out[sid] = last_frame(v, str(d / f"{sid}_start.jpg"))
    return out
