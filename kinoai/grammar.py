"""Kadr grammatikasi va davomiylik taqsimoti.

MUAMMO (test videosida ko'rindi):
  4 ta kadr ham bir xil chiqdi — ko'z darajasi, uch personaj o'rtada,
  o'xshash masofa. Va har biri aynan 5.000 soniya.

  Bu AI ning aybi emas. Model o'zi tanlaganda har doim "xavfsiz"
  o'rtacha planni beradi, chunki promptda kadr grammatikasi yo'q edi.
  Teng davomiylik esa `runtime / shot_count` formulasidan kelib chiqqan.

YECHIM:
  1. Plan JSONda shot_size majburiy va qo'shni kadrlar bir xil bo'lmasin
  2. Davomiylik teng emas — ritm bo'yicha taqsimlanadi
  3. Har kadrda kamera harakati boshqacha

Bu qism generatsiyaga PUL SARFLAMAYDI — faqat prompt va validatsiya.
"""

from __future__ import annotations

# Kadr o'lchamlari — yaqinlik darajasi bo'yicha tartiblangan
SIZES = ["extreme_wide", "wide", "medium", "close", "extreme_close"]
SIZE_RANK = {s: i for i, s in enumerate(SIZES)}

MOVES = ["static", "slow push in", "slow pull out", "pan left",
         "pan right", "tilt up", "tilt down", "tracking", "crane up"]

# O'zbekcha nomlar — foydalanuvchiga ko'rsatish uchun
SIZE_UZ = {
    "extreme_wide": "juda umumiy",
    "wide": "umumiy",
    "medium": "o'rta",
    "close": "yaqin",
    "extreme_close": "juda yaqin",
}


def normalize_size(raw: str) -> str:
    """LLM turlicha yozadi: 'wide shot', 'WS', 'close-up', 'CU'."""
    if not raw:
        return ""
    s = str(raw).lower().replace("-", " ").replace("_", " ").strip()
    table = {
        # UZUNROQ kalit BIRINCHI tekshiriladi. Aks holda 'ecu' ichidagi
        # 'cu' oldin mos kelib, extreme_close o'rniga close chiqadi.
        "extreme close": "extreme_close", "ecu": "extreme_close",
        "macro": "extreme_close", "detail": "extreme_close",
        "extreme wide": "extreme_wide", "ews": "extreme_wide",
        "establishing": "extreme_wide", "aerial": "extreme_wide",
        "closeup": "close", "close": "close", "cu": "close",
        "medium": "medium", "mid": "medium", "ms": "medium",
        "wide": "wide", "long": "wide", "full": "wide", "ws": "wide",
    }
    for k, v in sorted(table.items(), key=lambda kv: -len(kv[0])):
        if s == k or s.startswith(k + " ") or f" {k}" in f" {s}":
            return v
    return "medium"


def check(shots: list[dict]) -> list[str]:
    """Grammatika buzilishlarini topadi. Generatsiyadan OLDIN chaqiriladi."""
    issues: list[str] = []
    sizes = [normalize_size(s.get("shot_size", "")) for s in shots]

    # 1. Qo'shni kadrlar bir xil bo'lmasin — bu "jump cut"
    for i in range(1, len(sizes)):
        if sizes[i] and sizes[i] == sizes[i - 1]:
            issues.append(
                f"{i}-{i+1} kadr ikkalasi ham '{SIZE_UZ.get(sizes[i], sizes[i])}' "
                f"— tomoshabin nima o'zgarganini sezmaydi"
            )

    # 2. Kamida uchta xil o'lcham bo'lsin
    distinct = len({s for s in sizes if s})
    if len(shots) >= 4 and distinct < 3:
        issues.append(
            f"{len(shots)} kadrda faqat {distinct} xil plan — monoton"
        )

    # 3. Kamera harakati takrorlanmasin
    moves = [str(s.get("movement", "")).lower().strip() for s in shots]
    for i in range(1, len(moves)):
        if moves[i] and moves[i] == moves[i - 1] and moves[i] != "static":
            issues.append(f"{i}-{i+1} kadrda bir xil kamera harakati")

    # 4. Teng davomiylik — slaydshou ritmi
    durs = [float(s.get("duration", 0) or 0) for s in shots]
    if len(set(durs)) == 1 and len(durs) > 2 and durs[0]:
        issues.append(
            f"barcha kadr aynan {durs[0]:.0f}s — bu slaydshou ritmi, "
            f"film ritmi emas"
        )

    return issues


def repair(shots: list[dict], rhythm: list[str] | None = None) -> list[dict]:
    """Grammatikani avtomatik tuzatadi.

    LLM qayta chaqirilmaydi — bu bepul tuzatish.
    """
    if not shots:
        return shots
    out = [dict(s) for s in shots]
    n = len(out)

    plan = list(rhythm) if rhythm else default_rhythm(n)
    while len(plan) < n:
        plan.append(plan[len(plan) % max(1, len(plan))])

    # Agar plan butunlay monoton bo'lsa (AI hamma kadrga bir xil o'lcham
    # bergan), qisman tuzatish yetarli emas — ritmni TO'LIQ qo'llaymiz.
    given = [normalize_size(s.get("shot_size", "")) for s in out]
    monotone = len({g for g in given if g}) <= 1
    if monotone:
        for i, s in enumerate(out):
            s["shot_size"] = plan[i]
        given = plan

    for i, s in enumerate(out):
        cur = normalize_size(s.get("shot_size", ""))
        prev = normalize_size(out[i - 1].get("shot_size", "")) if i else ""
        if not cur or cur == prev:
            want = plan[i]
            if want == prev:
                # rejadagisi ham bir xil bo'lsa — eng uzoq variantni ol
                want = max(SIZES,
                           key=lambda x: abs(SIZE_RANK[x] - SIZE_RANK[prev]))
            s["shot_size"] = want
        else:
            s["shot_size"] = cur

    # kamera harakatlari takrorlanmasin
    used = ""
    for i, s in enumerate(out):
        mv = str(s.get("movement", "")).strip()
        if not mv or mv == used:
            mv = MOVES[(i * 3 + 1) % len(MOVES)]
        s["movement"] = mv
        used = mv

    return out


def default_rhythm(n: int) -> list[str]:
    """Kadr soniga qarab standart ritm.

    Kino montajining oddiy qoidasi: umumiydan boshlanadi (tomoshabin
    joyni tushunadi), yaqinlashadi (hissiyot), umumiyga qaytadi (yakun).
    """
    base = {
        2: ["wide", "close"],
        3: ["wide", "close", "medium"],
        4: ["wide", "close", "medium", "wide"],
        5: ["wide", "close", "medium", "extreme_close", "wide"],
        6: ["wide", "medium", "close", "medium", "extreme_close", "wide"],
    }
    if n in base:
        return base[n]
    out: list[str] = []
    cycle = ["wide", "close", "medium", "extreme_close"]
    for i in range(n):
        out.append(cycle[i % len(cycle)])
    out[0] = "wide"
    out[-1] = "wide"
    return out


def distribute(total: float, n: int, sizes: list[str] | None = None,
               lo: float = 3.0, hi: float = 8.0) -> list[float]:
    """Davomiylikni TENG EMAS taqsimlaydi.

    Mantiq: yaqin plan qisqaroq (hissiyot tez o'qiladi), umumiy plan
    uzunroq (tomoshabinga makonni ko'rish uchun vaqt kerak).
    """
    if n <= 0:
        return []
    weight = {"extreme_wide": 1.30, "wide": 1.20, "medium": 1.00,
              "close": 0.85, "extreme_close": 0.70}
    ws = [weight.get(normalize_size(s), 1.0) for s in (sizes or [])]
    while len(ws) < n:
        ws.append(1.0)
    ws = ws[:n]

    unit = total / sum(ws)
    durs = [max(lo, min(hi, round(unit * w, 1))) for w in ws]

    # yig'indini maqsadga tenglashtirish
    for _ in range(60):
        diff = round(total - sum(durs), 1)
        if abs(diff) < 0.15:
            break
        step = 0.1 if diff > 0 else -0.1
        moved = False
        order = sorted(range(n), key=lambda i: -durs[i]) if diff < 0 \
            else sorted(range(n), key=lambda i: durs[i])
        for i in order:
            nv = round(durs[i] + step, 1)
            if lo <= nv <= hi:
                durs[i] = nv
                moved = True
                break
        if not moved:
            break
    return durs


def apply(shots: list[dict], total: float,
          rhythm: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """To'liq tuzatish: grammatika + davomiylik.

    Qaytaradi: tuzatilgan kadrlar va nima tuzatilgani ro'yxati.
    """
    before = check(shots)
    fixed = repair(shots, rhythm)
    if total > 0:
        sizes = [s.get("shot_size", "") for s in fixed]
        for s, d in zip(fixed, distribute(total, len(fixed), sizes)):
            s["duration"] = d
    return fixed, before
