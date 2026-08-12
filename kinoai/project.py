"""Loyiha holati: ssenariy, kadrlar, uslub bibliyasi.

Asosiy g'oya: har bir kadr — bu SLOT. Slotda uchta narsa bor:
  1. nima bo'lishi kerak  (tavsif, davomiylik)
  2. hozir nima turibdi    (fayl yo'li)
  3. u qayerdan keldi      (ai / upload / external)

Shuning uchun tizim kadrning manbasiga befarq. AI dan kelganmi,
telefondan yuklanganmi, DaVinci'dan qaytganmi — montaj bir xil ishlaydi.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class Stage(str, Enum):
    """Bosqichlar. Har biri tugallangach keyingisi ochiladi."""

    DEVELOPMENT = "rivojlanish"
    PREPRODUCTION = "preproduksiya"
    ANIMATIC = "animatik"
    PRODUCTION = "produksiya"
    POST = "postproduksiya"
    DELIVERY = "yetkazish"

    @classmethod
    def order(cls) -> list[Stage]:
        return [
            cls.DEVELOPMENT,
            cls.PREPRODUCTION,
            cls.ANIMATIC,
            cls.PRODUCTION,
            cls.POST,
            cls.DELIVERY,
        ]

    def next(self) -> Stage | None:
        seq = Stage.order()
        i = seq.index(self)
        return seq[i + 1] if i + 1 < len(seq) else None


class Source(str, Enum):
    """Kadr qayerdan keldi."""

    AI = "ai"              # generatsiya qilingan
    UPLOAD = "upload"      # foydalanuvchi yuklagan (telefon, kamera)
    EXTERNAL = "external"  # tashqi montaj ilovasidan qaytgan
    EMPTY = "empty"        # hali bo'sh


@dataclass
class Element:
    """Qayta ishlatiladigan personaj / muhit / buyum.

    Bu "script supervisor" vazifasi: daftar 1-kadrda ham, 19-kadrda ham
    bir xil bo'lishi kerak. Element ID barcha promptlarga avtomatik qo'shiladi.
    """

    id: str
    name: str
    kind: str = "prop"       # character | environment | prop
    ref_id: str = ""         # provayderdagi ID (Higgsfield element_id va h.k.)
    note: str = ""


@dataclass
class Shot:
    """Bitta kadr sloti."""

    n: int
    scene: str = ""
    description: str = ""          # nima bo'lishi kerak (o'zbekcha, odam uchun)
    prompt: str = ""               # generatsiya uchun (inglizcha, tizim yig'adi)
    duration: float = 4.0
    elements: list[str] = field(default_factory=list)   # Element.id lar
    grade: str = ""                # rang bloki kaliti (masalan "cold" / "warm")
    narration: str = ""            # shu kadrga tushadigan diktor matni

    source: Source = Source.EMPTY
    file: str = ""                 # tayyor video/surat yo'li
    still: str = ""                # animatik uchun surat
    takes: list[str] = field(default_factory=list)  # barcha urinishlar
    locked: bool = False           # tanlandi, boshqa o'zgarmaydi

    def ready(self) -> bool:
        return bool(self.file) and self.source is not Source.EMPTY


@dataclass
class StyleBible:
    """Uslub bibliyasi.

    MUHIM: uslub bitta katta blok EMAS. U modullarga bo'linadi.

    `base`    — har kadrda (optika, plyonka, realizm)
    `modules` — faqat kerakli kadrlarda (odamlar, interyer, va h.k.)

    Sabab: 'Central Asian people' ni kadrda odam yo'q bo'lsa ham yozsangiz,
    model odam qo'shadi. 'Uzbek architecture' ni cho'l kadriga yozsangiz,
    model u yerga uy tiqadi. Kadrda yo'q narsani promptda aytmang.
    """

    base: str = ""                                        # har doim
    modules: dict[str, str] = field(default_factory=dict)  # tanlab
    grades: dict[str, str] = field(default_factory=dict)   # rang bloklari
    negative: str = ""
    aspect: str = "9:16"
    model_image: str = ""
    model_video: str = ""


@dataclass
class Project:
    title: str
    kind: str = "film"                      # film | multfilm
    target_seconds: int = 60
    stage: Stage = Stage.DEVELOPMENT

    logline: str = ""
    script: str = ""
    style: StyleBible = field(default_factory=StyleBible)
    elements: list[Element] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)

    narration_file: str = ""
    music_file: str = ""
    output: str = ""

    # ---------- saqlash ----------

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> Project:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        raw["stage"] = Stage(raw.get("stage", Stage.DEVELOPMENT.value))
        raw["style"] = StyleBible(**raw.get("style", {}))
        raw["elements"] = [Element(**e) for e in raw.get("elements", [])]
        shots = []
        for s in raw.get("shots", []):
            s["source"] = Source(s.get("source", Source.EMPTY.value))
            shots.append(Shot(**s))
        raw["shots"] = shots
        return cls(**raw)

    # ---------- bosqich boshqaruvi ----------

    def element(self, eid: str) -> Element | None:
        return next((e for e in self.elements if e.id == eid), None)

    def blockers(self) -> list[str]:
        """Joriy bosqichni yopish uchun nima yetishmayapti."""
        b: list[str] = []
        if self.stage is Stage.DEVELOPMENT:
            if not self.logline:
                b.append("logline yo'q")
            if not self.script:
                b.append("ssenariy yo'q")
        elif self.stage is Stage.PREPRODUCTION:
            if not self.shots:
                b.append("kadrlar ro'yxati bo'sh")
            if not self.style.base:
                b.append("uslub bloki yo'q")
            for s in self.shots:
                if not s.description:
                    b.append(f"{s.n}-kadr tavsifsiz")
        elif self.stage is Stage.ANIMATIC:
            missing = [s.n for s in self.shots if not s.still]
            if missing:
                b.append(f"surat yo'q: {missing}")
        elif self.stage is Stage.PRODUCTION:
            missing = [s.n for s in self.shots if not s.ready()]
            if missing:
                b.append(f"kadr tayyor emas: {missing}")
        elif self.stage is Stage.POST:
            if not self.output:
                b.append("yig'ilmagan")
        return b

    def advance(self) -> Stage:
        """Keyingi bosqichga o'tish. Yopilmagan bo'lsa — xato."""
        b = self.blockers()
        if b:
            raise RuntimeError("Bosqich yopilmagan: " + "; ".join(b))
        nxt = self.stage.next()
        if nxt is None:
            raise RuntimeError("Oxirgi bosqich")
        self.stage = nxt
        return self.stage

    def total_seconds(self) -> float:
        return sum(s.duration for s in self.shots)
