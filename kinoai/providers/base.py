"""Provayder interfeysi.

MUHIM: tizim hech qachon to'g'ridan-to'g'ri Higgsfield yoki boshqa
xizmatga bog'lanmaydi. Hammasi shu interfeys orqali o'tadi.

Sabab amaliy: bugun Higgsfield, ertaga boshqasi arzonroq yoki yaxshiroq
bo'ladi. Interfeys bo'lsa — bitta fayl yozasiz. Bo'lmasa — hamma joyni
qayta yozasiz.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Take:
    """Bitta urinish natijasi."""

    path: str
    cost: float = 0.0
    meta: dict | None = None


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def image(self, prompt: str, aspect: str = "9:16", n: int = 1) -> list[Take]:
        """Surat yaratadi. ARZON — animatik va tanlov uchun shu ishlatiladi."""

    @abstractmethod
    def video(
        self,
        prompt: str,
        seconds: float,
        start_image: str = "",
        end_image: str = "",
        aspect: str = "9:16",
        n: int = 1,
    ) -> list[Take]:
        """Video yaratadi. QIMMAT — faqat tasdiqlangan kadrlar uchun."""

    @abstractmethod
    def speech(self, text: str, voice: str = "") -> Take:
        """Diktor ovozi."""

    def estimate(self, prompt: str, seconds: float, kind: str = "video") -> float:
        """Generatsiyadan oldin narx. Har provayder o'zi hisoblaydi."""
        return 0.0


class DryRun(Provider):
    """Sinov uchun. Hech narsa yaratmaydi, faqat nima bo'lishini yozadi.

    Buni birinchi ishlatib ko'ring — butun oqim bir tiyinsiz tekshiriladi.
    """

    name = "dryrun"

    def __init__(self) -> None:
        self.log: list[str] = []

    def image(self, prompt, aspect="9:16", n=1):
        self.log.append(f"IMAGE x{n} [{aspect}] {prompt[:90]}...")
        return [Take(path="", meta={"dry": True}) for _ in range(n)]

    def video(self, prompt, seconds, start_image="", end_image="",
              aspect="9:16", n=1):
        self.log.append(
            f"VIDEO x{n} [{seconds}s {aspect}]"
            f"{' +start' if start_image else ''}"
            f"{' +end' if end_image else ''} {prompt[:80]}..."
        )
        return [Take(path="", meta={"dry": True}) for _ in range(n)]

    def speech(self, text, voice=""):
        self.log.append(f"SPEECH [{voice or 'default'}] {text[:60]}...")
        return Take(path="", meta={"dry": True})
