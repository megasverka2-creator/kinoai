"""Presetlar — foydalanuvchi NIMA yaratayotganini tanlaydi.

Muammo: hozirgi /start da "Fast Mode / Professional Mode" tanlanadi.
Bu TEXNIK tanlov va foydalanuvchi uchun ma'nosiz — u "Fast Mode nima?"
deb o'ylaydi.

Yechim: natija bo'yicha tanlov. Preset barcha texnik parametrni
o'zi belgilaydi: format, uzunlik, kadr soni, sifat, rejim.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Preset:
    key: str
    label: str
    hint: str                  # foydalanuvchi ko'radigan qisqa izoh

    aspect: str = "16:9"
    runtime: int = 20
    shots: int = 4
    resolution: str = "480p"
    audio: bool = True
    mode: str = "fast"

    video: bool = True         # False -> faqat rasmlar (storyboard)
    reuse_bible: bool = False  # oldingi loyihadan continuity olish

    # kadr grammatikasi — shu preset uchun tavsiya etilgan ketma-ketlik
    rhythm: list[str] = field(default_factory=list)

    def est_video_cost(self, per_second: float = 0.22) -> float:
        return 0.0 if not self.video else self.runtime * per_second

    def est_image_cost(self, per_image: float = 0.04) -> float:
        return self.shots * per_image


PRESETS: dict[str, Preset] = {
    "reels": Preset(
        key="reels", label="📱 Reels / Shorts",
        hint="9:16 vertikal · 20 soniya · ijtimoiy tarmoq uchun",
        aspect="9:16", runtime=20, shots=5,
        rhythm=["wide", "close", "medium", "extreme_close", "wide"],
    ),
    "ad": Preset(
        key="ad", label="📺 Reklama roligi",
        hint="16:9 · 20 soniya · mahsulot yoki xizmat",
        aspect="16:9", runtime=20, shots=4,
        rhythm=["wide", "close", "medium", "wide"],
    ),
    "cartoon": Preset(
        key="cartoon", label="🎨 Qisqa multfilm",
        hint="16:9 · 30 soniya · hikoya va personajlar",
        aspect="16:9", runtime=30, shots=6,
        rhythm=["wide", "medium", "close", "medium", "close", "wide"],
    ),
    "episode": Preset(
        key="episode", label="📖 Serial epizodi",
        hint="oldingi loyihadagi personajlar bilan davom etadi",
        aspect="16:9", runtime=30, shots=6, reuse_bible=True,
        rhythm=["medium", "close", "wide", "close", "medium", "wide"],
    ),
    "storyboard": Preset(
        key="storyboard", label="🖼 Storyboard",
        hint="faqat rasmlar · videosiz · eng arzon",
        aspect="16:9", runtime=0, shots=8, video=False,
        rhythm=["wide", "medium", "close", "wide",
                "medium", "extreme_close", "medium", "wide"],
    ),
    "pro": Preset(
        key="pro", label="🎬 Professional",
        hint="to'liq nazorat · har bosqichni o'zingiz tasdiqlaysiz",
        aspect="16:9", runtime=60, shots=12, resolution="720p", mode="pro",
    ),
}


def keyboard_rows() -> list[list[tuple[str, str]]]:
    """Telegram tugmalari uchun."""
    return [[(p.label, f"preset:{p.key}")] for p in PRESETS.values()]


def get(key: str) -> Preset:
    return PRESETS.get(key, PRESETS["ad"])


def describe(p: Preset) -> str:
    """Tanlovdan keyin ko'rsatiladigan xulosa — foydalanuvchi nima
    olishini oldindan biladi."""
    lines = [f"<b>{p.label}</b>", p.hint, ""]
    if p.video:
        lines.append(f"Format: {p.aspect} · {p.runtime}s · {p.shots} kadr")
        lines.append(f"Sifat: {p.resolution}"
                     + (" · ovoz bilan" if p.audio else " · ovozsiz"))
        lines.append(f"Taxminiy xarajat: "
                     f"~${p.est_video_cost() + p.est_image_cost():.2f}")
    else:
        lines.append(f"{p.shots} ta kadr rasmi · {p.aspect}")
        lines.append(f"Taxminiy xarajat: ~${p.est_image_cost():.2f}")
    if p.reuse_bible:
        lines.append("\n<i>Mavjud personajlaringiz ishlatiladi</i>")
    return "\n".join(lines)
