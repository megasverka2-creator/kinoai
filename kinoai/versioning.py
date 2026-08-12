"""Versiyalash, stage-gate holatlari va dependency graph.

TZ 2.1, 2.3, 2.4 va 18-bo'limlar.

Markaziy qoida: tasdiqlangan versiya O'ZGARMAYDI. Tahrir yangi versiya
yaratadi. Shuning uchun orqaga qaytish xavfsiz — eski holat yo'qolmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Status(str, Enum):
    """TZ 2.1 — universal stage-gate holatlari."""

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    LOCKED = "locked"                    # Current Master
    OUTDATED = "outdated"                # upstream o'zgardi, qayta ko'r
    NEEDS_REGENERATION = "needs_regen"   # upstream jiddiy o'zgardi
    ARCHIVED = "archived"

    def is_usable(self) -> bool:
        """Keyingi bosqich bu artefaktdan foydalana oladimi."""
        return self in (Status.APPROVED, Status.LOCKED)


class Impact(str, Enum):
    """TZ 18.2 — upstream o'zgarish qanchalik pastga tarqaladi."""

    METADATA = "metadata"      # sarlavha o'zgardi — hech nima qilinmaydi
    REVIEW = "review"          # dialog, minor style — qayta ko'rish
    PARTIAL_REGEN = "partial"  # kostyum, sahna holati — faqat ta'sirlangan
    FULL_REGEN = "full"        # identity yoki global style — hammasi

    def to_status(self) -> Status | None:
        return {
            Impact.METADATA: None,
            Impact.REVIEW: Status.OUTDATED,
            Impact.PARTIAL_REGEN: Status.NEEDS_REGENERATION,
            Impact.FULL_REGEN: Status.NEEDS_REGENERATION,
        }[self]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Version:
    """Bitta artefaktning bitta versiyasi."""

    n: int
    content: dict = field(default_factory=dict)
    status: Status = Status.DRAFT
    source: str = "ai"              # ai | user | upload | import
    parent: int | None = None
    note: str = ""                  # nima va nega o'zgardi
    created_at: str = field(default_factory=_now)


@dataclass
class Artifact:
    """Versiyalangan entity. Har SC, SH, CHR, LOC, STY shu ko'rinishda."""

    id: str                          # SH014
    kind: str                        # shot
    versions: list[Version] = field(default_factory=list)

    # ---- versiya boshqaruvi ----

    def current(self) -> Version | None:
        """Current Master — oxirgi LOCKED yoki APPROVED."""
        for v in reversed(self.versions):
            if v.status.is_usable():
                return v
        return self.versions[-1] if self.versions else None

    def head(self) -> Version | None:
        return self.versions[-1] if self.versions else None

    def add(self, content: dict, source: str = "ai", note: str = "") -> Version:
        prev = self.head()
        v = Version(
            n=len(self.versions) + 1,
            content=content,
            source=source,
            parent=prev.n if prev else None,
            note=note,
        )
        self.versions.append(v)
        return v

    def approve(self, lock: bool = True) -> Version:
        v = self.head()
        if v is None:
            raise RuntimeError(f"{self.id}: versiya yo'q")
        v.status = Status.LOCKED if lock else Status.APPROVED
        return v

    def mark(self, status: Status) -> None:
        """Upstream o'zgargani uchun belgilash. Tasdiqlangan versiya
        O'CHIRILMAYDI — faqat holati o'zgaradi."""
        v = self.current()
        if v is not None:
            v.status = status

    @property
    def status(self) -> Status:
        v = self.current()
        return v.status if v else Status.DRAFT


@dataclass
class Edge:
    """upstream -> downstream bog'lanish."""

    upstream: str
    downstream: str
    impact: Impact = Impact.REVIEW


class Graph:
    """Dependency graph. TZ 18-bo'lim.

    MVP darajasi ataylab sodda: to'liq invalidation engine emas,
    balki "yuqorida o'zgardi -> pastdagilarni belgila" mantiqi.
    Keyinchalik chuqurlashtiriladi.
    """

    def __init__(self, edges: list[Edge] | None = None) -> None:
        self.edges: list[Edge] = edges or []

    def link(self, upstream: str, downstream: str,
             impact: Impact = Impact.REVIEW) -> None:
        if not any(e.upstream == upstream and e.downstream == downstream
                   for e in self.edges):
            self.edges.append(Edge(upstream, downstream, impact))

    def downstream_of(self, entity_id: str) -> list[Edge]:
        return [e for e in self.edges if e.upstream == entity_id]

    def impact_set(self, entity_id: str,
                   impact: Impact) -> dict[str, Impact]:
        """Rekursiv ta'sir doirasi.

        Ta'sir pastga tushganda KUCHAYMAYDI — full_regen pastda review
        bo'lib qolishi mumkin, lekin review pastda full_regen bo'lmaydi.
        """
        order = [Impact.METADATA, Impact.REVIEW,
                 Impact.PARTIAL_REGEN, Impact.FULL_REGEN]
        out: dict[str, Impact] = {}
        stack: list[tuple[str, Impact]] = [(entity_id, impact)]
        seen: set[str] = set()

        while stack:
            node, imp = stack.pop()
            for e in self.downstream_of(node):
                eff = order[min(order.index(imp), order.index(e.impact))]
                prev = out.get(e.downstream)
                if prev is None or order.index(eff) > order.index(prev):
                    out[e.downstream] = eff
                    if e.downstream not in seen:
                        seen.add(e.downstream)
                        stack.append((e.downstream, eff))
        return out

    def preview(self, entity_id: str, impact: Impact) -> str:
        """O'zgartirishdan OLDIN ko'rsatiladigan ta'sir hisoboti.

        Bu foydalanuvchini pulini tejaydi: 'bu o'zgarish 14 ta kadrni
        qayta yaratishga majbur qiladi' degan ogohlantirish."""
        hits = self.impact_set(entity_id, impact)
        if not hits:
            return f"{entity_id}: ta'sirlangan artefakt yo'q"
        by: dict[Impact, list[str]] = {}
        for k, v in hits.items():
            by.setdefault(v, []).append(k)
        lines = [f"{entity_id} o'zgarishi ({impact.value}) ta'siri:"]
        for imp in (Impact.FULL_REGEN, Impact.PARTIAL_REGEN,
                    Impact.REVIEW, Impact.METADATA):
            if imp in by:
                ids = sorted(by[imp])
                lines.append(f"  {imp.value:9} -> {len(ids)}: "
                             f"{', '.join(ids[:8])}"
                             f"{' ...' if len(ids) > 8 else ''}")
        return "\n".join(lines)
