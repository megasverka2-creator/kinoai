"""AI agentlar. TZ 15-bo'lim.

Markaziy qoida (TZ 15.1): agentlar bir-biriga cheksiz chat tarixi
uzatmaydi. Orchestrator har bosqich uchun faqat kerakli TASDIQLANGAN
strukturaviy kontekstni yig'adi. Bu token xarajati va gallyutsinatsiya
riskini kamaytiradi.

MVP'da TZ dagi 19 ta agentdan 4 tasi ishlaydi. Qolganlari keyingi
fazalarda.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .providers.text import TextProvider, TextResult


@dataclass
class Agent:
    """Bitta agent: rol, cheklov va chiqish sxemasi."""

    key: str
    role: str
    system: str
    required: list[str]
    forbidden_to_change: str = ""   # TZ 15 — yozishi mumkin bo'lmagan master

    def run(self, provider: TextProvider, context: dict,
            instruction: str) -> TextResult:
        user = (
            "KONTEKST (tasdiqlangan faktlar, o'zgartirilmaydi):\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
            + "\n\nVAZIFA:\n" + instruction
        )
        return provider.structured(self.system, user, self.required)


# ---------------------------------------------------------------- agentlar

CREATIVE_PRODUCER = Agent(
    key="producer",
    role="Creative Producer",
    forbidden_to_change="Original idea / Must Keep",
    system=(
        "Sen professional kino prodyuserisan. Foydalanuvchi g'oyasidan "
        "Concept Package tuzasan.\n"
        "QAT'IY QOIDA: foydalanuvchining original g'oyasi va 'Must Keep' "
        "talablarini hech qachon o'zgartirma yoki almashtirma. Ular "
        "o'zgarmas manba.\n"
        "Hikoyani tanqidiy baholaysan: runtime realmi, personaj soni "
        "haddan tashqari emasmi, AI-generatsiya uchun qanday risklar bor. "
        "Har riskga yechim taklif qil.\n"
        "Barcha matn o'zbek tilida."
    ),
    required=["title", "logline", "synopsis", "genre", "theme", "tone",
              "protagonist", "goal", "conflict", "stakes",
              "ending_direction", "complexity", "risks"],
)

SCREENWRITER = Agent(
    key="screenwriter",
    role="Professional Screenwriter",
    forbidden_to_change="Locked scene / user constraints",
    system=(
        "Sen professional ssenaristsan. Tasdiqlangan konsept asosida "
        "production-ready ssenariy yozasan.\n"
        "Har sahnaga o'zgarmas ID ber: SC001, SC002, ... Bu ID keyingi "
        "barcha bosqichlarda ishlatiladi va hech qachon o'zgarmaydi.\n"
        "Har sahnaga taxminiy davomiylik (soniyada) ber. Yig'indi umumiy "
        "runtime maqsadiga mos kelsin.\n"
        "Scene heading formati: ICH./TASH. JOY - VAQT\n"
        "Vizual hikoya dialogdan ustun. Dialog kerak bo'lmasa yozma.\n"
        "Barcha matn o'zbek tilida."
    ),
    required=["scenes", "characters", "locations", "total_duration"],
)

SCRIPT_DOCTOR = Agent(
    key="script_doctor",
    role="Script Doctor",
    forbidden_to_change="Current screenplay (tasdiqsiz almashtirmaydi)",
    system=(
        "Sen Script Doctor'san. Ssenariyni audit qilasan: dramaturgiya, "
        "temp, mantiqiy teshiklar, motivatsiya, continuity, ishlab "
        "chiqarish risklari.\n"
        "QAT'IY QOIDA: ssenariyni O'ZING QAYTA YOZMAYSAN. Faqat "
        "muammolarni topasan va aniq tuzatish taklif qilasan. Yakuniy "
        "qarorni foydalanuvchi qabul qiladi.\n"
        "Har muammoga severity ber: blocker / major / minor.\n"
        "Barcha matn o'zbek tilida."
    ),
    required=["issues", "verdict"],
)

CINEMATOGRAPHER = Agent(
    key="cinematographer",
    role="Cinematographer",
    forbidden_to_change="Locked Style Bible",
    system=(
        "Sen operatorsan. Tasdiqlangan ssenariyni kadrlarga bo'lasan.\n"
        "Har kadrga o'zgarmas ID: SH001, SH002, ...\n"
        "Har kadr uchun: sahna ID, davomiylik, plan kattaligi, rakurs, "
        "obyektiv, kamera harakati, personajlar, lokatsiya, harakat, "
        "yorug'lik.\n"
        "MUHIM: 5 soniyaga bitta harakat sig'adi, 10 soniyaga ikkita. "
        "Undan ortiq bo'lsa kadrni bo'l.\n"
        "Har kadrga generation_difficulty ber: low/medium/high/very_high "
        "va sababini yoz.\n"
        "Kadrlar davomiyligi yig'indisi umumiy runtime'ga mos kelsin.\n"
        "Barcha matn o'zbek tilida, faqat texnik atamalar inglizcha."
    ),
    required=["shots", "total_duration"],
)


REGISTRY = {a.key: a for a in
            (CREATIVE_PRODUCER, SCREENWRITER, SCRIPT_DOCTOR, CINEMATOGRAPHER)}


def context_for(stage_key: str, project: dict) -> dict:
    """Orchestrator: bosqichga FAQAT kerakli tasdiqlangan kontekstni beradi.

    TZ 15.1. Butun loyihani uzatish — token isrofi va gallyutsinatsiya
    manbai.
    """
    base = {
        "format": project.get("kind"),
        "runtime_target_seconds": project.get("target_seconds"),
        "aspect_ratio": project.get("aspect", "9:16"),
    }
    if stage_key == "producer":
        return base | {
            "original_idea": project.get("idea", ""),
            "must_keep": project.get("must_keep", []),
        }
    if stage_key == "screenwriter":
        return base | {"concept": project.get("concept", {})}
    if stage_key == "script_doctor":
        return base | {
            "concept": project.get("concept", {}),
            "screenplay": project.get("screenplay", {}),
        }
    if stage_key == "cinematographer":
        return base | {
            "screenplay": project.get("screenplay", {}),
            "style": project.get("style", {}),
        }
    return base
