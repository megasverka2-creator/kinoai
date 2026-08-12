"""Immutable ID tizimi.

TZ 16-bo'lim. Bu butun tizimning umurtqasi: SH014 storyboard'da ham,
take'da ham, timeline'da ham, QC'da ham AYNAN shu ID bo'lib qoladi.

ID hech qachon o'zgarmaydi. Kadr tartibi o'zgarsa — `order` maydoni
o'zgaradi, ID emas.
"""

from __future__ import annotations

import re

# Entity turi -> prefiks
PREFIX = {
    "project": "PRJ",
    "scene": "SC",
    "shot": "SH",
    "character": "CHR",
    "costume": "CST",
    "prop": "PRP",
    "location": "LOC",
    "style": "STY",
    "keyframe": "KFR",
    "take": "T",
    "voice": "VOI",
    "dialogue": "DLG",
    "sfx": "SFX",
    "ambience": "AMB",
    "music": "MUS",
    "cut": "CUT",
    "export": "EXP",
}

_RE = re.compile(r"^([A-Z]{1,4})(\d{3})(?:_ST(\d{2}))?$")


def make(kind: str, n: int) -> str:
    """make('shot', 14) -> 'SH014'"""
    if kind not in PREFIX:
        raise ValueError(f"noma'lum entity turi: {kind}")
    return f"{PREFIX[kind]}{n:03d}"


def state(base_id: str, n: int) -> str:
    """Holat ID: state('CHR001', 3) -> 'CHR001_ST03'

    Nam kiyim, jarohat, yosh o'zgarishi — bitta identity ostidagi holat.
    Yangi personaj EMAS.
    """
    return f"{base_id}_ST{n:02d}"


def take(shot_id: str, n: int) -> str:
    """take('SH014', 3) -> 'SH014_T03'"""
    return f"{shot_id}_T{n:02d}"


def parse(entity_id: str) -> tuple[str, int, int | None]:
    """'CHR001_ST03' -> ('character', 1, 3)"""
    m = _RE.match(entity_id)
    if not m:
        raise ValueError(f"yaroqsiz ID: {entity_id}")
    pre, num, st = m.groups()
    kind = next((k for k, v in PREFIX.items() if v == pre), None)
    if kind is None:
        raise ValueError(f"noma'lum prefiks: {pre}")
    return kind, int(num), int(st) if st else None


def next_id(kind: str, existing: list[str]) -> str:
    """Mavjudlaridan keyingi bo'sh ID. Bo'shliqlarni TO'LDIRMAYDI —
    o'chirilgan ID qayta ishlatilmaydi, aks holda tarix buziladi."""
    pre = PREFIX[kind]
    nums = [
        int(e[len(pre):len(pre) + 3])
        for e in existing
        if e.startswith(pre) and e[len(pre):len(pre) + 3].isdigit()
    ]
    return make(kind, max(nums, default=0) + 1)
