"""Montaj: kadrlar + diktor + musiqa -> bitta fayl.

Bu qism ko'p loyihani to'xtatadi. Kadr yaratish oson, ularni to'g'ri
ritmda va ovoz bilan sinxron yig'ish qiyin. Shuning uchun u alohida
modul va boshidan yozilgan.

Manba muhim emas: AI kadri ham, telefon videosi ham, tashqi montajdan
qaytgan fayl ham bir xil yo'ldan o'tadi (normalize -> concat -> mix).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .project import Project, Source

# Vertikal format. Boshqa format kerak bo'lsa shu yerda o'zgartiriladi.
W, H, FPS = 1080, 1920, 30


def _run(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg xato:\n{r.stderr[-2000:]}")


def normalize(src: str, dst: str, seconds: float) -> None:
    """Har xil manbani bir xil formatga keltiradi.

    Surat bo'lsa — videoga aylantiradi (sekin zoom bilan, Ken Burns uslubi).
    Video bo'lsa — o'lcham/FPS/davomiylikni tekislaydi.
    """
    ext = Path(src).suffix.lower()
    is_still = ext in {".jpg", ".jpeg", ".png", ".webp"}

    if is_still:
        frames = max(1, int(seconds * FPS))
        # zoompan: statik suratga jonlilik beradi, animatik uchun ham shu
        vf = (
            f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
            f"crop={W*2}:{H*2},"
            f"zoompan=z='min(zoom+0.0008,1.12)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
            f"setsar=1"
        )
        _run([
            "ffmpeg", "-y", "-loop", "1", "-i", src,
            "-t", f"{seconds}", "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            dst,
        ])
    else:
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,fps={FPS}"
        )
        _run([
            "ffmpeg", "-y", "-i", src, "-t", f"{seconds}",
            "-vf", vf, "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            dst,
        ])


def build_video(p: Project, out: str, use_stills: bool = False) -> str:
    """Kadrlarni ketma-ket ulaydi.

    use_stills=True  -> ANIMATIK (arzon, suratlardan)
    use_stills=False -> yakuniy film (video kadrlardan)
    """
    tmp = Path(tempfile.mkdtemp(prefix="kinoai_"))
    parts: list[Path] = []

    for s in p.shots:
        src = s.still if use_stills else s.file
        if not src:
            if use_stills:
                raise RuntimeError(f"{s.n}-kadr uchun surat yo'q")
            raise RuntimeError(f"{s.n}-kadr uchun fayl yo'q")
        if not Path(src).exists():
            raise RuntimeError(f"{s.n}-kadr fayli topilmadi: {src}")

        dst = tmp / f"{s.n:03d}.mp4"
        normalize(src, str(dst), s.duration)
        parts.append(dst)

    lst = tmp / "list.txt"
    lst.write_text(
        "".join(f"file '{q}'\n" for q in parts), encoding="utf-8"
    )
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c", "copy", out,
    ])
    return out


def mix_audio(
    video: str,
    out: str,
    narration: str = "",
    music: str = "",
    music_db: float = -18.0,
) -> str:
    """Diktor + musiqa. Musiqa diktor ostiga tushiriladi (ducking emas,
    oddiy daraja — boshlang'ich versiya uchun yetarli)."""
    if not narration and not music:
        Path(out).write_bytes(Path(video).read_bytes())
        return out

    args = ["ffmpeg", "-y", "-i", video]
    inputs = 1
    filters = []
    labels = []

    if narration:
        args += ["-i", narration]
        filters.append(f"[{inputs}:a]volume=1.0[nar]")
        labels.append("[nar]")
        inputs += 1
    if music:
        args += ["-i", music]
        filters.append(f"[{inputs}:a]volume={music_db}dB[mus]")
        labels.append("[mus]")
        inputs += 1

    if len(labels) == 2:
        filters.append("[nar][mus]amix=inputs=2:duration=first:dropout_transition=0[aout]")
        amap = "[aout]"
    else:
        amap = labels[0]

    args += [
        "-filter_complex", ";".join(filters),
        "-map", "0:v", "-map", amap,
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        out,
    ]
    _run(args)
    return out


def render(p: Project, out: str, animatic: bool = False) -> str:
    """To'liq yig'ish."""
    tmp = Path(tempfile.mkdtemp(prefix="kinoai_out_"))
    silent = str(tmp / "silent.mp4")
    build_video(p, silent, use_stills=animatic)
    return mix_audio(
        silent, out,
        narration=p.narration_file,
        music="" if animatic else p.music_file,
    )


def report(p: Project) -> str:
    """Yig'ishdan oldingi holat."""
    lines = [f"{p.title} — {p.stage.value}",
             f"kadrlar: {len(p.shots)}  |  jami: {p.total_seconds():.1f}s"
             f"  (maqsad {p.target_seconds}s)"]
    by_src: dict[str, int] = {}
    for s in p.shots:
        by_src[s.source.value] = by_src.get(s.source.value, 0) + 1
    lines.append("manba: " + ", ".join(f"{k}={v}" for k, v in by_src.items()))
    missing = [s.n for s in p.shots if not s.ready()]
    if missing:
        lines.append(f"tayyor emas: {missing}")
    return "\n".join(lines)
