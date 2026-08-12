"""Cost ledger. TZ 8.4 va 22-bo'limlar.

Maqsad: har API chaqiruvining taxminiy va haqiqiy narxini yozib borish.
TZ dagi to'g'ri qoida: "Cost tarixisiz public tarif belgilanmaydi."

Budget guard bu yerda — foydalanuvchi belgilagan chegaradan oshsa,
generatsiya to'xtaydi. Bu yarim tashlangan loyihalardan himoya qiladi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Entry:
    entity_id: str          # SH014
    action: str             # image | video | speech | sound
    provider: str
    model: str = ""
    units: float = 1.0      # soniya, kadr, belgi
    estimated: float = 0.0
    actual: float | None = None
    job_id: str = ""
    at: str = field(default_factory=_now)


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Ledger:
    entries: list[Entry] = field(default_factory=list)

    project_cap: float = 0.0   # 0 = cheklovsiz
    stage_cap: float = 0.0
    retry_cap: int = 3

    # ---- yozish ----

    def estimate(self, entity_id: str, action: str, provider: str,
                 cost: float, model: str = "", units: float = 1.0) -> Entry:
        """Generatsiyadan OLDIN. Budjetdan oshsa — to'xtatadi."""
        if self.project_cap and self.spent() + cost > self.project_cap:
            raise BudgetExceeded(
                f"budjet chegarasi: sarflangan {self.spent():.2f} + "
                f"{cost:.2f} > {self.project_cap:.2f}"
            )
        e = Entry(entity_id=entity_id, action=action, provider=provider,
                  model=model, units=units, estimated=cost)
        self.entries.append(e)
        return e

    def settle(self, entry: Entry, actual: float, job_id: str = "") -> None:
        """Generatsiyadan KEYIN — haqiqiy narx."""
        entry.actual = actual
        if job_id:
            entry.job_id = job_id

    # ---- o'qish ----

    def spent(self) -> float:
        return sum(
            e.actual if e.actual is not None else e.estimated
            for e in self.entries
        )

    def by_action(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self.entries:
            c = e.actual if e.actual is not None else e.estimated
            out[e.action] = out.get(e.action, 0.0) + c
        return out

    def by_entity(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self.entries:
            c = e.actual if e.actual is not None else e.estimated
            out[e.entity_id] = out.get(e.entity_id, 0.0) + c
        return out

    def attempts(self, entity_id: str, action: str = "") -> int:
        return sum(
            1 for e in self.entries
            if e.entity_id == entity_id and (not action or e.action == action)
        )

    def can_retry(self, entity_id: str, action: str = "") -> bool:
        return self.attempts(entity_id, action) < self.retry_cap

    def report(self) -> str:
        lines = [f"Jami: {self.spent():.2f}"
                 + (f" / {self.project_cap:.2f}" if self.project_cap else "")]
        for k, v in sorted(self.by_action().items(),
                           key=lambda x: -x[1]):
            lines.append(f"  {k:8} {v:8.2f}")
        top = sorted(self.by_entity().items(), key=lambda x: -x[1])[:5]
        if top:
            lines.append("Eng qimmat kadrlar:")
            for k, v in top:
                lines.append(f"  {k:12} {v:8.2f}"
                             f"  ({self.attempts(k)} urinish)")
        return "\n".join(lines)
