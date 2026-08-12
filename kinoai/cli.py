"""Buyruq qatori.

    python -m kinoai.cli status   loyiha.json
    python -m kinoai.cli prompts  loyiha.json
    python -m kinoai.cli check    loyiha.json
    python -m kinoai.cli advance  loyiha.json
    python -m kinoai.cli animatic loyiha.json  out.mp4
    python -m kinoai.cli render   loyiha.json  out.mp4
"""

from __future__ import annotations

import sys

from .project import Project
from . import prompt as P
from . import assemble as A


def cmd_status(path: str) -> int:
    p = Project.load(path)
    print(A.report(p))
    b = p.blockers()
    if b:
        print("\nBosqichni yopish uchun:")
        for x in b:
            print("  -", x)
    else:
        nxt = p.stage.next()
        print(f"\nBosqich yopiq. Keyingisi: {nxt.value if nxt else '—'}")
    return 0


def cmd_prompts(path: str) -> int:
    p = Project.load(path)
    for s in p.shots:
        grade = s.grade or "grade tanlanmagan"
        print(f"\n--- {s.n}. {s.scene or s.description[:40]} "
              f"({s.duration}s, {grade}) ---")
        print(P.build(p, s))
    return 0


def cmd_check(path: str) -> int:
    p = Project.load(path)
    total = 0
    for s in p.shots:
        for w in P.validate(p, s):
            print("!", w)
            total += 1
    print(f"\n{total} ta ogohlantirish")
    return 0


def cmd_advance(path: str) -> int:
    p = Project.load(path)
    try:
        new = p.advance()
    except RuntimeError as e:
        print("XATO:", e)
        return 1
    p.save(path)
    print("Yangi bosqich:", new.value)
    return 0


def cmd_animatic(path: str, out: str) -> int:
    p = Project.load(path)
    print("Animatik yig'ilmoqda (suratlardan)...")
    A.render(p, out, animatic=True)
    print("Tayyor:", out)
    return 0


def cmd_render(path: str, out: str) -> int:
    p = Project.load(path)
    print("Film yig'ilmoqda...")
    A.render(p, out, animatic=False)
    p.output = out
    p.save(path)
    print("Tayyor:", out)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd, path = argv[1], argv[2]
    out = argv[3] if len(argv) > 3 else "out.mp4"
    table = {
        "status": lambda: cmd_status(path),
        "prompts": lambda: cmd_prompts(path),
        "check": lambda: cmd_check(path),
        "advance": lambda: cmd_advance(path),
        "animatic": lambda: cmd_animatic(path, out),
        "render": lambda: cmd_render(path, out),
    }
    fn = table.get(cmd)
    if fn is None:
        print("Noma'lum buyruq:", cmd)
        return 1
    return fn()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
