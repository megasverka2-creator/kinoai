"""Prompt yig'uvchi.

Foydalanuvchi HECH QACHON prompt yozmaydi. U o'zbekcha tavsif beradi,
tizim esa uslub bibliyasi va elementlarni qo'shib to'liq promptni yig'adi.

Tartib ahamiyatli va tasodifiy emas:
    subyekt -> harakat -> kamera -> yorug'lik/kayfiyat -> uslub -> rang

Sabab: video modellar promptning boshiga ko'proq e'tibor beradi.
Uslub oxirida turishi kerak, aks holda u kadrning mazmunini bosib ketadi.
"""

from __future__ import annotations

from .project import Project, Shot


# Inkorni ijobiyga aylantirish. Negativ promptlar deyarli ishlamaydi,
# shuning uchun "X bo'lmasin" ni "Y bo'lsin" ga aylantiramiz.
POSITIVE_REWRITE = {
    "no text": "clean surfaces free of any writing",
    "no blur": "sharp focus throughout",
    "no crowd": "a single figure alone in frame",
    "not cartoon": "photographic realism",
}


def element_clause(p: Project, shot: Shot) -> str:
    """Kadrdagi elementlarni promptga qo'shiladigan matnga aylantiradi."""
    parts = []
    for eid in shot.elements:
        el = p.element(eid)
        if el is None:
            continue
        if el.ref_id:
            # Provayder o'zi rasmni ulaydi (Higgsfield <<<uuid>>> uslubi)
            parts.append(f"<<<{el.ref_id}>>>")
        else:
            # el.note faqat odam uchun — promptga TUSHMAYDI
            parts.append(el.name)
    return ", ".join(parts)


def build(p: Project, shot: Shot) -> str:
    """Bitta kadr uchun to'liq prompt."""
    chunks: list[str] = []

    # 1. Subyekt va harakat — foydalanuvchi bergan tavsif
    if shot.prompt:
        chunks.append(shot.prompt.strip().rstrip("."))
    elif shot.description:
        chunks.append(shot.description.strip().rstrip("."))

    # 2. Elementlar — barqarorlik uchun
    els = element_clause(p, shot)
    if els:
        chunks.append(els)

    # 3. Uslub bloki — har kadrda AYNAN bir xil, qayta yozilmaydi
    if p.style.base:
        chunks.append(p.style.base.strip().rstrip("."))

    # 4. Rang bloki — kadrning bosqichiga qarab
    grade = p.style.grades.get(shot.grade, "")
    if grade:
        chunks.append(grade.strip().rstrip("."))

    # 5. Inkorlar ijobiyga aylantirilib qo'shiladi
    if p.style.negative:
        for raw in p.style.negative.split(","):
            key = raw.strip().lower()
            chunks.append(POSITIVE_REWRITE.get(key, key))

    return ". ".join(c for c in chunks if c) + "."


def build_all(p: Project) -> dict[int, str]:
    return {s.n: build(p, s) for s in p.shots}


def validate(p: Project, shot: Shot) -> list[str]:
    """Generatsiyadan OLDIN ogohlantirish. Kredit tejaydi."""
    warn: list[str] = []

    if shot.duration > 10:
        warn.append(
            f"{shot.n}-kadr {shot.duration}s — 10s dan uzun kadr buziladi, "
            "ikkiga bo'ling"
        )
    # 5s ~ bitta harakat, 10s ~ ikkita. Ko'p fe'l = buzilgan kadr.
    verbs = sum(
        shot.description.lower().count(v)
        for v in (" va ", " keyin ", " so'ng ", " then ", " and then ")
    )
    if verbs >= 2 and shot.duration <= 5:
        warn.append(
            f"{shot.n}-kadr: 5 soniyaga bitta harakat sig'adi, "
            "tavsifda bir nechta harakat bor"
        )
    if not shot.elements and any(
        e.kind == "character" for e in p.elements
    ):
        warn.append(f"{shot.n}-kadr: element ulanmagan — barqarorlik yo'qoladi")
    if not shot.grade and p.style.grades:
        warn.append(f"{shot.n}-kadr: rang bloki tanlanmagan")

    return warn
