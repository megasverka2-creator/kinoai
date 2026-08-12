"""TextProvider. TZ 19.2.

Provider-agnostic qoida: biznes logikada "Anthropic/OpenAI" nomi
bo'lmasin. Ular faqat shu faylda, adapter konfiguratsiyasida qoladi.

Kalitlar bo'lmasa DemoText ishlaydi — butun oqim bir tiyinsiz
sinaladi. TZ 26, Phase 0.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(RuntimeError):
    pass


@dataclass
class TextResult:
    data: dict
    raw: str = ""
    cost: float = 0.0
    model: str = ""


def _extract_json(raw: str) -> dict:
    """LLM javobidan JSON ajratib olish.

    Modellar ba'zan ```json bilan o'raydi yoki oldidan matn yozadi.
    """
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # birinchi { dan oxirgi } gacha
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        return json.loads(s[i:j + 1])
    raise ProviderError("javobdan JSON ajratib bo'lmadi")


class TextProvider(ABC):
    name = "base"

    @abstractmethod
    def generate(self, system: str, user: str,
                 max_tokens: int = 4000) -> TextResult:
        ...

    def structured(self, system: str, user: str, required: list[str],
                   max_tokens: int = 4000) -> TextResult:
        """Structured output + bir marta auto-repair. TZ 25.

        Validatsiyadan o'tmasa bir marta tuzatishga urinadi, keyin xato.
        """
        sys_json = (
            system
            + "\n\nFaqat JSON qaytar. Hech qanday izoh, markdown yoki "
              "kod bloki qo'shma. Majburiy kalitlar: "
            + ", ".join(required)
        )
        res = self.generate(sys_json, user, max_tokens)
        missing = [k for k in required if k not in res.data]
        if not missing:
            return res

        # auto-repair — bir marta
        fix = self.generate(
            sys_json,
            f"Oldingi javobda quyidagi kalitlar yo'q edi: "
            f"{', '.join(missing)}. Quyidagi ma'lumotni to'ldirib, "
            f"to'liq JSON qaytar:\n{json.dumps(res.data, ensure_ascii=False)}",
            max_tokens,
        )
        still = [k for k in required if k not in fix.data]
        if still:
            raise ProviderError(f"majburiy kalitlar yo'q: {still}")
        fix.cost += res.cost
        return fix


class DemoText(TextProvider):
    """Kalitsiz rejim. Haqiqiy LLM chaqirmaydi.

    Oqimni, tugmalarni, saqlashni va bosqich qulfini tekshirish uchun.
    Javob so'ralgan sxema bo'yicha yig'iladi, shuning uchun har qanday
    yangi agent uchun ham ishlaydi.
    """

    name = "demo"

    TEMPLATES = {
        "logline": "Bir jumlalik hikoya mag'zi (demo).",
        "title": "Ishchi nom",
        "synopsis": "Uch xatboshilik qisqacha bayon. Demo rejimda "
                    "haqiqiy LLM chaqirilmaydi — oqimni tekshirish uchun.",
        "genre": "drama",
        "theme": "xotira va davomiylik",
        "tone": "sokin, ta'sirchan",
        "protagonist": "Bosh qahramon",
        "goal": "Maqsad",
        "conflict": "To'siq",
        "stakes": "Yo'qotish xavfi",
        "ending_direction": "Ochiq, umidli yakun",
        "complexity": "medium",
        "risks": ["personaj barqarorligi", "davr detallari"],
        "characters": ["Qahramon", "Bobo"],
        "locations": ["Xona", "Ko'cha"],
        "props": ["Daftar"],
        "total_duration": 60.0,
        "verdict": "Demo audit: jiddiy muammo topilmadi.",
        "scenes": [
            {"id": "SC001", "heading": "ICH. XONA - KECHA",
             "action": "Demo sahna tavsifi.", "dialogue": [],
             "duration": 24.0},
            {"id": "SC002", "heading": "TASH. KO'CHA - TONG",
             "action": "Ikkinchi demo sahna.", "dialogue": [],
             "duration": 36.0},
        ],
        "issues": [
            {"severity": "minor", "scene": "SC001",
             "description": "Demo eslatma: sahna davomiyligi tekshirilsin.",
             "recommendation": "Qisqartirish mumkin."},
        ],
        "shots": [
            {"id": "SH001", "scene": "SC001", "duration": 4.0,
             "shot_size": "wide", "angle": "eye level", "movement": "static",
             "action": "Demo kadr tavsifi.",
             "generation_difficulty": "low", "difficulty_reason": ""},
            {"id": "SH002", "scene": "SC001", "duration": 5.0,
             "shot_size": "close-up", "angle": "high", "movement": "push in",
             "action": "Ikkinchi demo kadr.",
             "generation_difficulty": "medium",
             "difficulty_reason": "ikkita harakat"},
        ],
    }

    def generate(self, system: str, user: str,
                 max_tokens: int = 4000) -> TextResult:
        data = {"result": "demo", "note": "kalit ulanmagan"}
        return TextResult(data=data, raw=json.dumps(data), model="demo")

    def structured(self, system: str, user: str, required: list[str],
                   max_tokens: int = 4000) -> TextResult:
        """So'ralgan har bir kalitni to'ldiradi.

        Shu sabab yangi agent qo'shilganda demo rejim buzilmaydi.
        """
        data = {
            k: self.TEMPLATES.get(k, f"[demo:{k}]")
            for k in required
        }
        return TextResult(data=data, raw=json.dumps(data, ensure_ascii=False),
                          cost=0.0, model="demo")


class AnthropicText(TextProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.key = api_key
        self.model = model

    def generate(self, system: str, user: str,
                 max_tokens: int = 4000) -> TextResult:
        import urllib.request

        body = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "content-type": "application/json",
                "x-api-key": self.key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = json.loads(r.read())
        except Exception as e:
            raise ProviderError(f"anthropic: {e}") from e

        raw = "".join(
            b.get("text", "") for b in payload.get("content", [])
            if b.get("type") == "text"
        )
        usage = payload.get("usage", {})
        return TextResult(
            data=_extract_json(raw), raw=raw, model=self.model,
            cost=_cost(usage.get("input_tokens", 0),
                       usage.get("output_tokens", 0), 3.0, 15.0),
        )


class OpenAIText(TextProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.key = api_key
        self.model = model

    def generate(self, system: str, user: str,
                 max_tokens: int = 4000) -> TextResult:
        import urllib.request

        body = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self.key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = json.loads(r.read())
        except Exception as e:
            raise ProviderError(f"openai: {e}") from e

        raw = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage", {})
        return TextResult(
            data=_extract_json(raw), raw=raw, model=self.model,
            cost=_cost(usage.get("prompt_tokens", 0),
                       usage.get("completion_tokens", 0), 2.5, 10.0),
        )


def _cost(inp: int, out: int, in_rate: float, out_rate: float) -> float:
    """USD, 1M token uchun narx bo'yicha."""
    return (inp * in_rate + out * out_rate) / 1_000_000


def from_env() -> TextProvider:
    """Muhit o'zgaruvchilaridan provayder tanlaydi.

    Kalit yo'q bo'lsa demo rejim — bu XATO EMAS, ataylab.
    """
    if key := os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicText(key, os.getenv("LLM_MODEL", "claude-sonnet-4-6"))
    if key := os.getenv("OPENAI_API_KEY"):
        return OpenAIText(key, os.getenv("LLM_MODEL", "gpt-4o"))
    return DemoText()
