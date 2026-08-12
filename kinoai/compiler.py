"""Prompt Compiler. TZ 8-bo'lim.

Ikki bosqichli: avval provayderdan MUSTAQIL canonical package tuziladi,
keyin adapter uni o'z formatiga tarjima qiladi.

Bu yerda v0.1 dagi ASOSIY XATO tuzatilgan:

    v0.1 da uslub bloki bo'linmas edi va har kadrga to'liq yopishardi.
    Natijada "Total darkness, a notebook page" kadriga ham
    "Central Asian people with warm olive skin" qo'shilardi. Kadrda
    odam yo'q — model esa odam qo'shishga urinadi.

    Endi uslub MODULLARGA bo'lingan. Har kadr faqat o'ziga keraklisini
    oladi. Kadrda yo'q narsa promptda aytilmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Package:
    """Canonical Generation Package. TZ 8.2.

    Provayder nomi bu yerda YO'Q va bo'lmasligi kerak.
    """

    shot_id: str
    scene_id: str = ""

    identity: list[str] = field(default_factory=list)   # CHR/CST/PRP refs
    world: list[str] = field(default_factory=list)      # LOC refs
    visual: list[str] = field(default_factory=list)     # STY/KFR refs

    prompt: str = ""              # canonical positive instruction
    forbidden: list[str] = field(default_factory=list)  # negative rules

    duration: float = 4.0
    aspect: str = "9:16"
    quality: str = "balanced"     # draft | balanced | max

    start_frame: str = ""
    end_frame: str = ""

    prev_end_state: str = ""      # continuity — TZ 8.2
    next_start_state: str = ""

    needs_audio: bool = False
    difficulty: str = "low"       # low | medium | high | very_high
    difficulty_reason: str = ""


# Inkorni ijobiyga aylantirish — negativ promptlar deyarli ishlamaydi
POSITIVE = {
    "no text": "clean surfaces free of any writing",
    "no lettering": "clean surfaces free of any writing",
    "no blur": "sharp focus throughout",
    "no crowd": "a single figure alone in frame",
    "not cartoon": "photographic realism",
    "no modern objects": "period-accurate objects only",
}


def _dedupe(chunks: list[str]) -> list[str]:
    """Takrorni olib tashlaydi.

    To'liq mos kelish yetarli emas: v0.1 da base'dagi 'Photographic
    realism, not illustration' va inkordan aylangan 'photographic
    realism' ikkalasi ham qolib ketardi. Shuning uchun qismiy
    ichkilikni ham tekshiramiz.
    """
    kept: list[str] = []
    keys: list[str] = []
    for c in chunks:
        key = c.strip().rstrip(".").lower()
        if not key:
            continue
        # allaqachon bor bo'lgan bo'lakning ichida turibdimi
        if any(key in k for k in keys):
            continue
        # o'zi kengroq bo'lsa — eskisini almashtiradi
        narrower = [i for i, k in enumerate(keys) if k in key]
        for i in reversed(narrower):
            kept.pop(i)
            keys.pop(i)
        kept.append(c.strip().rstrip("."))
        keys.append(key)
    return kept


def compile_prompt(pkg: Package, style_base: str,
                   modules: dict[str, str], active: list[str],
                   grade: str = "") -> str:
    """Package + uslub -> yakuniy matn.

    Tartib ahamiyatli: modellar promptning boshiga ko'proq e'tibor
    beradi, shuning uchun uslub OXIRIDA turadi.

        subyekt/harakat -> referenslar -> asosiy uslub
        -> tanlangan modullar -> rang -> ijobiyga aylantirilgan inkorlar
    """
    chunks: list[str] = [pkg.prompt]

    for ref in pkg.identity + pkg.world + pkg.visual:
        chunks.append(ref)

    chunks.append(style_base)

    # FAQAT kadrga tegishli modullar
    for key in active:
        if key in modules:
            chunks.append(modules[key])

    if grade:
        chunks.append(grade)

    for rule in pkg.forbidden:
        chunks.append(POSITIVE.get(rule.strip().lower(), rule.strip()))

    return ". ".join(_dedupe(chunks)) + "."


def assess_difficulty(pkg: Package, action_beats: int = 1,
                      characters: int = 0) -> tuple[str, str]:
    """Generation Difficulty. TZ 8.2.

    Generatsiyadan OLDIN ogohlantiradi va kredit tejaydi.
    """
    score = 0
    why: list[str] = []

    if pkg.duration > 10:
        score += 2
        why.append(f"{pkg.duration}s — 10s dan uzun kadr buziladi")
    elif pkg.duration > 6:
        score += 1

    if action_beats > 2:
        score += 2
        why.append(f"{action_beats} ta harakat — kadrni bo'lish kerak")
    elif action_beats == 2 and pkg.duration < 8:
        score += 1
        why.append("ikkita harakat uchun 8s dan kam")

    if characters > 2:
        score += 2
        why.append(f"{characters} personaj bir kadrda — identity buziladi")
    elif characters == 2:
        score += 1

    if len(pkg.identity) > 3:
        score += 1
        why.append("juda ko'p reference — model chalkashadi")

    if pkg.needs_audio:
        score += 1

    level = ("low" if score <= 1 else
             "medium" if score <= 3 else
             "high" if score <= 5 else "very_high")
    return level, "; ".join(why)


def continuity_check(a: Package, b: Package) -> list[str]:
    """SHxxx END holati SHyyy START holatiga mos keladimi. TZ 7.4."""
    issues: list[str] = []
    if a.prev_end_state and b.next_start_state:
        pass  # to'liq semantik tekshiruv keyingi versiyada
    if a.end_frame and b.start_frame and a.end_frame != b.start_frame:
        issues.append(
            f"{a.shot_id} oxiri {b.shot_id} boshiga ulanmagan"
        )
    a_ids = set(a.identity)
    b_ids = set(b.identity)
    if a_ids and b_ids and not (a_ids & b_ids) and a.scene_id == b.scene_id:
        issues.append(
            f"{a.shot_id} va {b.shot_id} bir sahnada, lekin umumiy "
            f"personaj/buyum yo'q — continuity shubhali"
        )
    return issues
