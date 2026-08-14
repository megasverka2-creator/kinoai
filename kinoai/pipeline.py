"""Generatsiya pipeline: storyboard -> video -> montaj.

Eng muhim qarori — ZANJIR. Kadr `chain` bo'lsa, u uchun rasm
generatsiya QILINMAYDI: oldingi kadr videosining oxirgi freymi
olinadi. Bu ikki narsani beradi:

  1. O'tishlar tabiiy bo'ladi (test videosidagi asosiy nuqson)
  2. Rasm narxi tejaladi

Buning narxi: zanjirlangan kadrlar PARALLEL yaratilmaydi — SH002
SH001 tugashini kutadi. Shuning uchun sahnalar bo'yicha guruhlanadi:
sahna ichida ketma-ket, sahnalar orasida parallel bo'lishi mumkin.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import chain
from .providers.media import Asset, MediaProvider, Uploader


def _sid(shot: dict) -> str:
    return str(shot.get("shot_id") or shot.get("id") or "SH000")


def _txt(shot: dict, *keys: str) -> str:
    for k in keys:
        v = shot.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


@dataclass
class Progress:
    """Har qadamda chaqiriladigan xabar — bot foydalanuvchiga yuboradi."""

    on_image: object = None      # (shot_id, path, caption) -> None
    on_video: object = None      # (shot_id, path, seconds) -> None
    on_error: object = None      # (shot_id, message) -> None
    on_note: object = None       # (text) -> None


@dataclass
class Result:
    images: dict[str, str] = field(default_factory=dict)
    videos: dict[str, str] = field(default_factory=dict)
    cost: float = 0.0
    errors: list[str] = field(default_factory=list)
    final: str = ""


def build_image_prompt(shot: dict, continuity: dict) -> str:
    """Rasm prompti: kadr + identity + uslub.

    Identity HAR promptda to'liq takrorlanadi — modellar chaqiruvlar
    orasida xotirasiz.
    """
    parts = [_txt(shot, "start_image_prompt", "start_frame_en")]

    names = [str(x).lower() for x in (shot.get("characters") or [])]
    for c in continuity.get("characters", []):
        if not isinstance(c, dict):
            continue
        nm = str(c.get("name", "")).lower()
        # kadrda kim borligi aytilmagan bo'lsa — hammasi qo'shiladi
        if names and nm and not any(nm in n or n in nm for n in names):
            continue
        vi = c.get("visual_identity", "")
        wd = c.get("wardrobe", "")
        if vi:
            parts.append(f"{c.get('name', '')}: {vi}. {wd}".strip())

    for l in continuity.get("locations", []):
        if isinstance(l, dict) and l.get("visual_identity"):
            parts.append(l["visual_identity"])
            break

    st = continuity.get("style", {})
    if isinstance(st, dict) and st.get("visual_rules"):
        parts.append(st["visual_rules"])

    parts.append("No text, no lettering, no signage anywhere in frame")

    size = str(shot.get("shot_size", "")).replace("_", " ")
    move = str(shot.get("movement", ""))
    if size:
        parts.append(f"{size} shot")
    if move and move != "static":
        parts.append(move)

    return ". ".join(p.rstrip(".") for p in parts if p) + "."


def build_video_prompt(shot: dict, prev: dict | None = None) -> str:
    parts = [_txt(shot, "video_prompt", "action_uz", "action")]
    if prev is not None and shot.get("start_source") == "chain":
        if hint := chain.continuity_hint(prev):
            parts.append(hint)
    move = str(shot.get("movement", ""))
    if move:
        parts.append(f"Camera: {move}")
    return ". ".join(p.rstrip(".") for p in parts if p) + "."


def estimate(shots: list[dict], mp: MediaProvider,
             wants_video: bool = True) -> dict:
    """Generatsiyadan OLDIN narx. Foydalanuvchi shuni tasdiqlaydi."""
    to_generate = sum(1 for s in shots
                      if s.get("start_source") != "chain")
    chained = len(shots) - to_generate
    secs = sum(float(s.get("duration", 0) or 0) for s in shots)
    img = mp.est_image(to_generate)
    vid = mp.est_video(secs) if wants_video else 0.0
    return {
        "images": to_generate,
        "chained": chained,
        "seconds": secs,
        "image_cost": img,
        "video_cost": vid,
        "total": img + vid,
        "saved": mp.est_image(chained),
    }


def run_storyboard(shots: list[dict], continuity: dict, aspect: str,
                   mp: MediaProvider, workdir: str,
                   prog: Progress | None = None) -> Result:
    """Faqat generatsiya kerak bo'lgan kadrlar uchun rasm.

    Zanjirlangan kadrlar bu bosqichda tashlanadi — ularning START
    rasmi video bosqichida oldingi klipdan olinadi.
    """
    r = Result()
    d = Path(workdir) / "images"
    d.mkdir(parents=True, exist_ok=True)

    for s in shots:
        sid = _sid(s)
        if s.get("start_source") == "chain":
            continue
        try:
            a = mp.image(build_image_prompt(s, continuity), aspect,
                         str(d / f"{sid}.jpg"))
            r.images[sid] = a.path
            r.cost += a.cost
            if prog and prog.on_image:
                prog.on_image(sid, a.path, _txt(s, "start_frame_uz",
                                                "action_uz"))
        except Exception as e:
            msg = f"{sid}: {e}"
            r.errors.append(msg)
            if prog and prog.on_error:
                prog.on_error(sid, str(e))
    return r


def run_video(shots: list[dict], images: dict[str, str], aspect: str,
              resolution: str, audio: bool, mp: MediaProvider,
              up: Uploader, workdir: str,
              prog: Progress | None = None) -> Result:
    """Zanjir tartibida video generatsiya.

    Ketma-ket ishlaydi, chunki zanjirlangan kadr oldingisining
    tayyor bo'lishini kutadi.
    """
    r = Result()
    d = Path(workdir) / "videos"
    d.mkdir(parents=True, exist_ok=True)
    frames = Path(workdir) / "frames"

    prev_shot: dict | None = None
    for s in shots:
        sid = _sid(s)
        secs = float(s.get("duration", 5) or 5)
        start_path = ""

        if s.get("start_source") == "chain":
            src_id = s.get("chain_from", "")
            prev_video = r.videos.get(src_id, "")
            if prev_video and Path(prev_video).exists():
                try:
                    start_path = chain.last_frame(
                        prev_video, str(frames / f"{sid}_start.jpg"))
                except Exception as e:
                    r.errors.append(f"{sid}: zanjir uzildi — {e}")
            if not start_path:
                # zanjir uzilsa — rasm bilan davom etamiz
                start_path = images.get(sid, "")
        else:
            start_path = images.get(sid, "")

        start_url = ""
        if start_path and Path(start_path).exists():
            try:
                start_url = up.put(start_path)
            except Exception as e:
                r.errors.append(f"{sid}: yuklash xatosi — {e}")

        try:
            a = mp.video(
                build_video_prompt(s, prev_shot), secs,
                str(d / f"{sid}.mp4"),
                start_image=start_path, start_url=start_url,
                aspect=aspect, resolution=resolution, audio=audio,
            )
            r.videos[sid] = a.path
            r.cost += a.cost
            if prog and prog.on_video:
                prog.on_video(sid, a.path, secs)
        except Exception as e:
            r.errors.append(f"{sid}: {e}")
            if prog and prog.on_error:
                prog.on_error(sid, str(e))

        prev_shot = s
    return r


def assemble(shots: list[dict], videos: dict[str, str], out: str,
             aspect: str = "16:9") -> str:
    """FFmpeg concat. Barcha klip bir formatga keltiriladi."""
    w, h = (1080, 1920) if aspect == "9:16" else (1280, 720)
    tmp = Path(out).parent / "_norm"
    tmp.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    for s in shots:
        sid = _sid(s)
        src = videos.get(sid)
        if not src or not Path(src).exists():
            continue
        dst = tmp / f"{sid}.mp4"
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h},setsar=1,fps=24")
        subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-vf", vf,
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-ar", "48000", "-ac", "2",
             "-shortest", str(dst)],
            capture_output=True,
        )
        if dst.exists():
            parts.append(dst)

    if not parts:
        raise RuntimeError("montaj uchun klip yo'q")

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-c:a", "aac", out],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"concat: {res.stderr[-500:]}")
    return out
