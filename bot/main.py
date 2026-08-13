"""AI Film Studio — Telegram bot (private alpha). TZ 20-bo'lim.

Komandalar TZ 20.2, stage review tugmalari TZ 20.3 bo'yicha.

Kalitlar bo'lmasa demo rejimda ishlaydi — butun oqim, tugmalar,
saqlash va bosqich qulfi bir tiyinsiz sinaladi.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

from kinoai import agents, bible, chain, grammar, presets, store
from kinoai.providers.text import ProviderError, from_env

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("studio")

LLM = from_env()

# TZ 3 — pipeline bosqichlari (MVP: 1-3 + 8)
FLOW = [
    ("brief", "Loyiha brifi"),
    ("producer", "Konsept"),
    ("screenwriter", "Ssenariy"),
    ("script_doctor", "Audit"),
    ("cinematographer", "Kadrlar ro'yxati"),
]
TITLES = dict(FLOW)
ORDER = [k for k, _ in FLOW]


class Wizard(StatesGroup):
    kind = State()
    length = State()
    idea = State()
    edit = State()


# ------------------------------------------------------------- klaviaturalar

def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
        for row in rows
    ])


def review_kb(stage: str) -> InlineKeyboardMarkup:
    """TZ 20.3 — stage review tugmalari."""
    return kb([
        [("✅ Tasdiqlash va qulflash", f"ok:{stage}")],
        [("✏️ AI bilan tahrir", f"edit:{stage}"),
         ("🔄 Qayta yaratish", f"regen:{stage}")],
        [("📝 Qo'lda kiritish", f"manual:{stage}"),
         ("🕘 Versiyalar", f"vers:{stage}")],
        [("📄 To'liq matn", f"full:{stage}"),
         ("⬅️ Oldingi bosqich", f"back:{stage}")],
    ])


MENU = kb([
    [("🎬 Yangi loyiha", "cmd:new")],
    [("📂 Loyihalar", "cmd:projects"), ("📊 Holat", "cmd:status")],
    [("💰 Xarajat", "cmd:cost"), ("⚙️ Sozlamalar", "cmd:settings")],
])

dp = Dispatcher(storage=MemoryStorage())


# ------------------------------------------------------------------ yordamchi

def stage_index(stage: str) -> int:
    return ORDER.index(stage) if stage in ORDER else 0


def next_stage(stage: str) -> str | None:
    i = stage_index(stage)
    return ORDER[i + 1] if i + 1 < len(ORDER) else None


def _txt(v, limit: int = 0) -> str:
    """Har qanday qiymatni matnga aylantiradi.

    LLM ro'yxat elementlarini ba'zan oddiy matn, ba'zan obyekt qilib
    qaytaradi ({"risk": ..., "solution": ...}). Ikkalasi ham to'g'ri —
    shuning uchun render hech qachon shaklga bog'liq bo'lmasligi kerak.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        out = v
    elif isinstance(v, (int, float)):
        out = str(v)
    elif isinstance(v, dict):
        # eng ma'noli maydonni tanlaydi
        for k in ("description", "risk", "issue", "text", "name",
                  "title", "value", "action", "summary"):
            if k in v and isinstance(v[k], str):
                out = v[k]
                break
        else:
            out = "; ".join(f"{k}: {_txt(x)}" for k, x in list(v.items())[:3])
    elif isinstance(v, (list, tuple)):
        out = ", ".join(_txt(x) for x in v)
    else:
        out = str(v)
    return out[:limit] if limit and len(out) > limit else out


def _pick(d: dict, *keys, default=None):
    """Bir necha mumkin bo'lgan kalitdan birinchi topilganini oladi.

    LLM 'duration' o'rniga 'duration_seconds', 'estimated_duration',
    'length' qaytarishi mumkin. Har birini qattiq kutish — xato manbai.
    """
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def _total(content: dict, items: list) -> float:
    """Jami davomiylik. LLM bermasa — elementlardan yig'iladi."""
    t = _num(_pick(content, "total_duration", "total_duration_seconds",
                   "runtime", "total_runtime"))
    if t:
        return t
    return sum(_dur(i) for i in items if isinstance(i, dict))


DURATION_KEYS = ("duration", "duration_seconds", "duration_sec",
                 "estimated_duration", "estimated_duration_seconds",
                 "length", "length_seconds", "seconds", "davomiylik")


def _dur(d: dict) -> float:
    return _num(_pick(d, *DURATION_KEYS))


def _num(v, default: float = 0.0) -> float:
    """LLM raqamni matn qilib qaytarishi mumkin ('45' yoki '45 soniya')."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        import re as _re
        m = _re.search(r"-?\d+(?:\.\d+)?", v)
        if m:
            return float(m.group())
    return default


def _items(content: dict, *keys) -> list:
    """Bir necha mumkin bo'lgan kalitdan birinchi topilgan ro'yxatni oladi.

    LLM 'scenes' o'rniga 'scene_list', 'shots' o'rniga 'shot_list'
    qaytarishi mumkin.
    """
    for k in keys:
        v = content.get(k)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            return list(v.values())
    return []


TG_LIMIT = 3900   # Telegram chegarasi 4096; zaxira qoldiramiz


def _fit(text: str) -> str:
    """Telegram xabar chegarasi. Haqiqiy ssenariy oson oshib ketadi."""
    if len(text) <= TG_LIMIT:
        return text
    cut = text[:TG_LIMIT]
    # HTML tegini o'rtasidan kesmaslik uchun oxirgi tugallangan qatorgacha
    nl = cut.rfind("\n")
    if nl > TG_LIMIT * 0.6:
        cut = cut[:nl]
    return cut + "\n\n<i>… qisqartirildi</i>"


def render(stage: str, content: dict) -> str:
    """Bosqich natijasini o'qiladigan matnga aylantiradi."""
    if stage == "producer":
        risks = _items(content, "risks", "risk_list")
        out = (
            f"<b>{_txt(content.get('title'), 90) or '—'}</b>\n\n"
            f"<i>{_txt(content.get('logline'), 300)}</i>\n\n"
            f"{_txt(content.get('synopsis'), 900)}\n\n"
            f"Janr: {_txt(content.get('genre'), 40) or '—'}  |  "
            f"Ohang: {_txt(content.get('tone'), 40) or '—'}\n"
            f"Mavzu: {_txt(content.get('theme'), 90) or '—'}\n"
            f"Qahramon: {_txt(content.get('protagonist'), 120) or '—'}\n"
            f"Maqsad: {_txt(content.get('goal'), 150) or '—'}\n"
            f"To'siq: {_txt(content.get('conflict'), 150) or '—'}"
        )
        if risks:
            out += "\n\n⚠️ <b>Risklar</b>"
            for r in risks[:4]:
                out += f"\n• {_txt(r, 160)}"
        return out
    if stage == "screenwriter":
        sc = _items(content, "scenes", "scene_list")
        head = (f"<b>Ssenariy</b> — {len(sc)} sahna, "
                f"{_total(content, sc):.0f}s\n\n")
        body = "\n\n".join(
            f"<b>{_txt(s.get('id'), 12)}</b> "
            f"{_txt(_pick(s, 'heading', 'slugline', 'scene_heading', 'location'), 70)} "
            f"({_dur(s):.0f}s)\n"
            f"{_txt(_pick(s, 'action', 'description', 'action_description', 'text'), 260)}"
            for s in sc[:7] if isinstance(s, dict)
        )
        more = f"\n\n… yana {len(sc) - 7} sahna" if len(sc) > 7 else ""
        return head + body + more
    if stage == "script_doctor":
        iss = _items(content, "issues", "issue_list")
        blocker = [i for i in iss
                   if isinstance(i, dict) and i.get("severity") == "blocker"]
        lines = [f"<b>Audit</b> — {len(iss)} ta eslatma"]
        if blocker:
            lines.append(f"🔴 {len(blocker)} ta blocker")
        for i in iss[:6]:
            sev = i.get("severity", "?") if isinstance(i, dict) else "?"
            lines.append(f"• [{sev}] {_txt(i, 180)}")
        v = _txt(content.get("verdict"), 500)
        if v:
            lines.append(f"\n{v}")
        return "\n".join(lines)
    if stage == "cinematographer":
        sh = _items(content, "shots", "shot_list")
        hard = [s for s in sh if isinstance(s, dict)
                and _txt(_pick(s, "generation_difficulty", "difficulty"))
                in ("high", "very_high")]
        lines = [f"<b>Kadrlar</b> — {len(sh)} ta, "
                 f"{_total(content, sh):.0f}s"]
        if hard:
            lines.append(f"⚠️ {len(hard)} ta kadr qiyin generatsiya")
        for s in sh[:10]:
            if not isinstance(s, dict):
                lines.append(f"• {_txt(s, 90)}")
                continue
            lines.append(
                f"<b>{_txt(s.get('id'), 12)}</b> "
                f"{_dur(s):.0f}s "
                f"{_txt(_pick(s, 'shot_size', 'size', 'framing'), 20)} — "
                f"{_txt(_pick(s, 'action', 'description', 'action_description'), 90)}"
            )
        if len(sh) > 10:
            lines.append(f"… yana {len(sh) - 10} kadr")
        return "\n".join(lines)
    return _txt(content, 3000)


async def run_stage(msg: Message, proj: dict, stage: str,
                    instruction: str = "") -> None:
    """Agentni ishga tushiradi, natijani versiya qilib saqlaydi."""
    agent = agents.REGISTRY.get(stage)
    if agent is None:
        await msg.answer("Bu bosqich hali tayyor emas.")
        return

    wait = await msg.answer(f"⏳ {agent.role} ishlamoqda…")
    ctx = agents.context_for(stage, proj)
    task = instruction or _default_instruction(stage, proj)

    try:
        res = await asyncio.to_thread(agent.run, LLM, ctx, task)
    except ProviderError as e:
        await wait.edit_text(f"❌ Xato: {e}\n\nQayta urinib ko'ring.")
        return

    store.add_version(proj, stage, res.data, source="ai")
    store.add_cost(proj, stage, LLM.name, res.cost, res.model)
    proj["stage"] = stage
    if stage == "producer":
        proj["concept"] = res.data
    elif stage == "screenwriter":
        proj["screenplay"] = res.data
    elif stage == "cinematographer":
        raw = _items(res.data, "shots", "shot_list")
        raw = [s for s in raw if isinstance(s, dict)]
        # Kadr grammatikasi: bir xil planlar va teng davomiylikni tuzatadi.
        # AI qayta chaqirilmaydi — bu bepul tuzatish.
        fixed, issues = grammar.apply(
            raw, float(proj.get("target_seconds", 0)),
            proj.get("rhythm") or None)
        # Zanjir: qaysi kadr oldingisining oxiridan boshlanadi
        fixed = chain.plan_chain(fixed)
        proj["shots"] = fixed
        res.data["shots"] = fixed
        if issues:
            proj["grammar_fixes"] = issues
            log.info("grammatika tuzatildi: %s", issues)
    store.save(proj)

    note = "\n\n<i>demo rejim — kalit ulanmagan</i>" if LLM.name == "demo" else ""
    if stage == "cinematographer":
        n_chain, saved = chain.savings(proj.get("shots", []))
        if n_chain:
            note += (f"\n\n🔗 {n_chain} ta kadr oldingisining oxiridan "
                     f"ulanadi — o'tishlar tabiiy, ${saved:.2f} tejaladi")
        if fixes := proj.get("grammar_fixes"):
            note += f"\n✏️ {len(fixes)} ta montaj muammosi avtomatik tuzatildi"
    try:
        await wait.edit_text(
            _fit(render(stage, res.data) + note),
            parse_mode="HTML", reply_markup=review_kb(stage),
        )
    except Exception as e:
        # HTML buzilgan bo'lsa formatsiz yuboramiz — natija yo'qolmasin
        log.warning("render/edit xatosi: %s", e)
        await wait.edit_text(
            _fit(render(stage, res.data)).replace("<b>", "").replace("</b>", "")
            .replace("<i>", "").replace("</i>", ""),
            reply_markup=review_kb(stage),
        )


def _default_instruction(stage: str, proj: dict) -> str:
    if stage == "producer":
        return ("Quyidagi g'oyadan to'liq Concept Package tuz. "
                "Formatga va runtime maqsadiga mos bo'lsin.")
    if stage == "screenwriter":
        return ("Tasdiqlangan konsept asosida to'liq ssenariy yoz. "
                "Har sahnaga SC ID va davomiylik ber.")
    if stage == "script_doctor":
        return ("Ssenariyni audit qil. Har muammoga severity va aniq "
                "tuzatish taklifini ber. O'zing qayta yozma.")
    if stage == "cinematographer":
        return ("Ssenariyni kadrlarga bo'l. Har kadrga SH ID, "
                "davomiylik va generation_difficulty ber.")
    return ""


# ------------------------------------------------------------------ komandalar

@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    mode = "demo" if LLM.name == "demo" else LLM.name
    await m.answer(
        "🎬 <b>AI Film Studio</b>\n\n"
        "Siz rejissyorsiz, AI esa sizning kino jamoangiz.\n\n"
        "G'oyadan tayyor filmgacha — bosqichma-bosqich. Har bosqich "
        "natijasini ko'rib, tasdiqlaysiz yoki o'zgartirasiz.\n\n"
        f"<i>Rejim: {mode}</i>",
        parse_mode="HTML", reply_markup=MENU,
    )


@dp.message(Command("new"))
async def cmd_new(m: Message, state: FSMContext):
    await start_wizard(m, state)


async def start_wizard(m: Message, state: FSMContext):
    """Natija bo'yicha tanlov.

    Foydalanuvchi "Fast Mode / Professional Mode" emas, NIMA
    yaratayotganini tanlaydi. Texnik parametrlarni preset o'zi belgilaydi.
    """
    await state.set_state(Wizard.kind)
    await m.answer("Nima yaratmoqchisiz?",
                   reply_markup=kb(presets.keyboard_rows()))


@dp.message(Command("projects"))
async def cmd_projects(m: Message):
    await show_projects(m, m.from_user.id)


async def show_projects(m: Message, uid: int):
    ps = store.list_projects(uid)
    if not ps:
        await m.answer("Loyiha yo'q. /new bilan boshlang.")
        return
    rows = [[(f"{p['id']} · {p.get('concept', {}).get('title', 'nomsiz')} "
              f"· {TITLES.get(p['stage'], p['stage'])}", f"open:{p['id']}")]
            for p in ps[:10]]
    await m.answer("Loyihalaringiz:", reply_markup=kb(rows))


@dp.message(Command("status"))
async def cmd_status(m: Message):
    await show_status(m, m.from_user.id)


async def show_status(m: Message, uid: int):
    p = store.latest(uid)
    if not p:
        await m.answer("Loyiha yo'q. /new bilan boshlang.")
        return
    i = stage_index(p["stage"])
    bar = "".join("●" if k <= i else "○" for k in range(len(ORDER)))
    v = store.current_version(p, p["stage"])
    await m.answer(
        f"<b>{p['id']}</b> · {p.get('kind')} · {p.get('target_seconds')}s\n"
        f"{bar}  {i + 1}/{len(ORDER)}\n"
        f"Bosqich: <b>{TITLES.get(p['stage'], p['stage'])}</b>\n"
        f"Holat: {v['status'] if v else 'boshlanmagan'}\n"
        f"Xarajat: ${store.total_cost(p):.4f}",
        parse_mode="HTML", reply_markup=MENU,
    )


@dp.message(Command("cost"))
async def cmd_cost(m: Message):
    await show_cost(m, m.from_user.id)


async def show_cost(m: Message, uid: int):
    p = store.latest(uid)
    if not p:
        await m.answer("Loyiha yo'q.")
        return
    by: dict[str, float] = {}
    for e in p.get("ledger", []):
        by[e["action"]] = by.get(e["action"], 0.0) + e["cost"]
    lines = [f"<b>{p['id']}</b> — jami ${store.total_cost(p):.4f}"]
    for k, v in sorted(by.items(), key=lambda x: -x[1]):
        lines.append(f"  {TITLES.get(k, k)}: ${v:.4f}")
    if LLM.name == "demo":
        lines.append("\n<i>demo rejimda xarajat nol</i>")
    await m.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("settings"))
async def cmd_settings(m: Message):
    await show_settings(m, m.from_user.id)


async def show_settings(m: Message, uid: int):
    p = store.latest(uid)
    q = p.get("quality", "balanced") if p else "balanced"
    await m.answer(
        f"Sifat rejimi: <b>{q}</b>\nLLM: <b>{LLM.name}</b>",
        parse_mode="HTML", reply_markup=kb([
            [("Draft", "q:draft"), ("Balanced", "q:balanced"),
             ("Maximum", "q:max")],
        ]),
    )


@dp.message(Command("export"))
async def cmd_export(m: Message):
    await m.answer("Eksport Phase 6 da keladi (TZ 14–16).")


# ------------------------------------------------------------------ wizard

@dp.callback_query(F.data.startswith("preset:"))
async def pick_preset(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":")[1]
    p = presets.get(key)
    await state.update_data(preset=key)

    if p.reuse_bible:
        bs = bible.list_bibles(c.from_user.id)
        if bs:
            rows = [[(b["name"], f"bib:{b['id']}")] for b in bs[:6]]
            rows.append([("➕ Yangi personajlar bilan", "bib:new")])
            await c.message.edit_text(
                presets.describe(p) + "\n\nQaysi personajlar bilan?",
                parse_mode="HTML", reply_markup=kb(rows))
            await c.answer()
            return

    await state.set_state(Wizard.idea)
    await c.message.edit_text(
        presets.describe(p)
        + "\n\n<b>G'oyangizni yozing.</b>\n"
          "Bir jumla ham yetadi. Qanchalik aniq yozsangiz, "
          "natija shunchalik yaqin bo'ladi.",
        parse_mode="HTML")
    await c.answer()


@dp.callback_query(F.data.startswith("bib:"))
async def pick_bible(c: CallbackQuery, state: FSMContext):
    bid = c.data.split(":")[1]
    await state.update_data(bible=None if bid == "new" else bid)
    await state.set_state(Wizard.idea)
    await c.message.edit_text(
        "<b>Epizod g'oyasini yozing.</b>\n"
        "Personajlar oldingi loyihadan olinadi — faqat yangi voqeani "
        "tasvirlang.", parse_mode="HTML")
    await c.answer()


@dp.callback_query(F.data.startswith("kind:"))
async def pick_kind(c: CallbackQuery, state: FSMContext):
    await state.update_data(kind=c.data.split(":")[1])
    await state.set_state(Wizard.length)
    await c.message.edit_text("Uzunlik:", reply_markup=kb([
        [("30 soniya", "len:30"), ("1 daqiqa", "len:60")],
        [("3 daqiqa", "len:180"), ("10 daqiqa", "len:600")],
    ]))
    await c.answer()


@dp.callback_query(F.data.startswith("len:"))
async def pick_length(c: CallbackQuery, state: FSMContext):
    secs = int(c.data.split(":")[1])
    await state.update_data(length=secs)
    await state.set_state(Wizard.idea)
    hint = ("\n\n⚠️ 10 daqiqalik ish 120+ kadr talab qiladi — "
            "uzun va qimmat bo'ladi." if secs >= 600 else "")
    await c.message.edit_text(
        "G'oyangizni yozing.\n\n"
        "Bir jumla ham, bir bet ham bo'lishi mumkin. Nima haqida, "
        "kim haqida, qanday tuyg'u uyg'otsin — qanchalik aniq "
        "yozsangiz, natija shunchalik yaqin bo'ladi." + hint
    )
    await c.answer()


@dp.message(Wizard.idea)
async def got_idea(m: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    p = presets.get(data.get("preset", "ad"))

    proj = store.new_project(m.from_user.id, p.key, p.runtime,
                             aspect=p.aspect, mode=p.mode)
    proj["idea"] = m.text
    proj["preset"] = p.key
    proj["shot_count"] = p.shots
    proj["resolution"] = p.resolution
    proj["audio"] = p.audio
    proj["rhythm"] = p.rhythm
    proj["wants_video"] = p.video
    if bid := data.get("bible"):
        b = bible.load(m.from_user.id, bid)
        if b:
            proj["bible_id"] = bid
            proj["locked_continuity"] = bible.as_context(b)
    store.save(proj)
    await run_stage(m, proj, "producer")


@dp.message(Wizard.edit)
async def got_edit(m: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    proj = store.load(m.from_user.id, d["pid"])
    if not proj:
        await m.answer("Loyiha topilmadi.")
        return
    await run_stage(m, proj, d["stage"],
                    f"Quyidagi talab bo'yicha qayta ishla: {m.text}")


# ------------------------------------------------------------------ tugmalar

@dp.callback_query(F.data.startswith("ok:"))
async def approve(c: CallbackQuery):
    stage = c.data.split(":")[1]
    proj = store.latest(c.from_user.id)
    if not proj:
        await c.answer("Loyiha topilmadi", show_alert=True)
        return
    store.approve(proj, stage, lock=True)
    store.save(proj)
    await c.answer("Qulflandi ✅")

    nxt = next_stage(stage)
    if nxt is None:
        await c.message.answer(
            "🎉 MVP bosqichlari tugadi.\n\n"
            "Keyingi fazalar: storyboard, video generatsiya, ovoz, "
            "montaj (TZ 9–16).", reply_markup=MENU)
        return
    await c.message.answer(f"➡️ Keyingi bosqich: <b>{TITLES[nxt]}</b>",
                           parse_mode="HTML")
    await run_stage(c.message, proj, nxt)


@dp.callback_query(F.data.startswith("regen:"))
async def regen(c: CallbackQuery):
    stage = c.data.split(":")[1]
    proj = store.latest(c.from_user.id)
    if proj:
        await c.answer("Qayta yaratilmoqda")
        await run_stage(c.message, proj, stage,
                        "Butunlay boshqacha yondashuv bilan qayta yarat.")


@dp.callback_query(F.data.startswith("edit:"))
async def edit(c: CallbackQuery, state: FSMContext):
    stage = c.data.split(":")[1]
    proj = store.latest(c.from_user.id)
    if not proj:
        await c.answer("Loyiha topilmadi", show_alert=True)
        return
    await state.set_state(Wizard.edit)
    await state.update_data(stage=stage, pid=proj["id"])
    await c.message.answer("Nimani o'zgartirmoqchisiz? Yozing.")
    await c.answer()


@dp.callback_query(F.data.startswith("manual:"))
async def manual(c: CallbackQuery):
    await c.answer("Qo'lda kiritish keyingi versiyada", show_alert=True)


@dp.callback_query(F.data.startswith("vers:"))
async def versions(c: CallbackQuery):
    stage = c.data.split(":")[1]
    proj = store.latest(c.from_user.id)
    vs = proj.get("versions", {}).get(stage, []) if proj else []
    if not vs:
        await c.answer("Versiya yo'q", show_alert=True)
        return
    lines = [f"<b>{TITLES.get(stage, stage)}</b> — {len(vs)} versiya"]
    for v in vs:
        lines.append(f"  V{v['n']} · {v['status']} · {v['source']}"
                     + (f" · {v['note'][:40]}" if v.get("note") else ""))
    await c.message.answer("\n".join(lines), parse_mode="HTML")
    await c.answer()


def full_text(stage: str, content: dict) -> str:
    """Qisqartirishsiz to'liq matn. Xabarlarga bo'lib yuboriladi."""
    if stage == "screenwriter":
        sc = _items(content, "scenes", "scene_list")
        out = []
        for s in sc:
            if not isinstance(s, dict):
                out.append(_txt(s))
                continue
            out.append(
                f"<b>{_txt(_pick(s, 'id'), 12)}</b> "
                f"{_txt(_pick(s, 'heading', 'slugline', 'scene_heading'), 90)}"
                f"  ({_dur(s):.0f}s)\n"
                f"{_txt(_pick(s, 'action', 'description', 'action_description'))}"
            )
            dlg = _items(s, "dialogue", "dialog", "lines")
            for d in dlg:
                if isinstance(d, dict):
                    who = _txt(_pick(d, "character", "speaker", "name"), 40)
                    line = _txt(_pick(d, "line", "text", "dialogue"))
                    out.append(f"   <b>{who}</b>: {line}")
                else:
                    out.append(f"   {_txt(d)}")
        return "\n\n".join(out)
    if stage == "cinematographer":
        sh = _items(content, "shots", "shot_list")
        out = []
        for s in sh:
            if not isinstance(s, dict):
                out.append(_txt(s))
                continue
            diff = _txt(_pick(s, "generation_difficulty", "difficulty"), 12)
            mark = " ⚠️" if diff in ("high", "very_high") else ""
            out.append(
                f"<b>{_txt(_pick(s, 'id'), 12)}</b>{mark}  {_dur(s):.0f}s  "
                f"{_txt(_pick(s, 'scene', 'scene_id'), 12)}\n"
                f"{_txt(_pick(s, 'shot_size', 'size', 'framing'), 30)} · "
                f"{_txt(_pick(s, 'angle'), 30)} · "
                f"{_txt(_pick(s, 'movement', 'camera_movement'), 40)}\n"
                f"{_txt(_pick(s, 'action', 'description'))}"
                + (f"\n<i>qiyinlik: {diff} — "
                   f"{_txt(_pick(s, 'difficulty_reason', 'reason'), 120)}</i>"
                   if mark else "")
            )
        return "\n\n".join(out)
    if stage == "script_doctor":
        iss = _items(content, "issues", "issue_list")
        out = []
        for i in iss:
            if isinstance(i, dict):
                out.append(
                    f"[{_txt(_pick(i, 'severity'), 12)}] "
                    f"{_txt(_pick(i, 'scene', 'scene_id'), 12)}\n"
                    f"{_txt(_pick(i, 'description', 'issue', 'problem'))}\n"
                    f"<i>{_txt(_pick(i, 'recommendation', 'fix', 'solution'))}</i>"
                )
            else:
                out.append(_txt(i))
        out.append(_txt(_pick(content, "verdict")))
        return "\n\n".join(x for x in out if x)
    if stage == "producer":
        out = []
        for k, v in content.items():
            out.append(f"<b>{k}</b>: {_txt(v)}")
        return "\n\n".join(out)
    return _txt(content)


def chunks(text: str, size: int = TG_LIMIT) -> list[str]:
    """Uzun matnni xabarlarga bo'ladi — qatorlar o'rtasidan kesmaydi."""
    out, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 > size:
            if cur:
                out.append(cur)
            cur = para[:size]
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out or [""]


@dp.callback_query(F.data.startswith("full:"))
async def show_full(c: CallbackQuery):
    stage = c.data.split(":")[1]
    proj = store.latest(c.from_user.id)
    if not proj:
        await c.answer("Loyiha topilmadi", show_alert=True)
        return
    v = store.current_version(proj, stage)
    if not v:
        await c.answer("Natija yo'q", show_alert=True)
        return
    await c.answer()
    parts = chunks(full_text(stage, v["content"]))
    for i, part in enumerate(parts):
        try:
            await c.message.answer(part, parse_mode="HTML")
        except Exception:
            plain = part
            for t in ("<b>", "</b>", "<i>", "</i>"):
                plain = plain.replace(t, "")
            await c.message.answer(plain)
        if i < len(parts) - 1:
            await asyncio.sleep(0.4)


@dp.callback_query(F.data.startswith("back:"))
async def back(c: CallbackQuery):
    stage = c.data.split(":")[1]
    i = stage_index(stage)
    if i == 0:
        await c.answer("Bu birinchi bosqich", show_alert=True)
        return
    prev = ORDER[i - 1]
    proj = store.latest(c.from_user.id)
    if proj:
        proj["stage"] = prev
        store.save(proj)
        v = store.current_version(proj, prev)
        if v:
            await c.message.answer(_fit(render(prev, v["content"])),
                                   parse_mode="HTML",
                                   reply_markup=review_kb(prev))
    await c.answer()


@dp.callback_query(F.data.startswith("open:"))
async def open_project(c: CallbackQuery):
    proj = store.load(c.from_user.id, c.data.split(":")[1])
    if not proj:
        await c.answer("Topilmadi", show_alert=True)
        return
    stage = proj["stage"]
    v = store.current_version(proj, stage)
    if v:
        await c.message.answer(_fit(render(stage, v["content"])),
                               parse_mode="HTML",
                               reply_markup=review_kb(stage))
    else:
        await c.message.answer(f"{proj['id']} — hali natija yo'q.")
    await c.answer()


@dp.callback_query(F.data.startswith("q:"))
async def set_quality(c: CallbackQuery):
    proj = store.latest(c.from_user.id)
    if proj:
        proj["quality"] = c.data.split(":")[1]
        store.save(proj)
    await c.answer("Saqlandi")


@dp.callback_query(F.data.startswith("cmd:"))
async def menu_route(c: CallbackQuery, state: FSMContext):
    """Menyu tugmalari.

    MUHIM: callback'dagi c.message.from_user — bu BOT, foydalanuvchi emas.
    Haqiqiy foydalanuvchi c.from_user da. Shuning uchun uid alohida
    uzatiladi (aiogram 3 da from_user o'zgarmas).
    """
    what = c.data.split(":")[1]
    uid = c.from_user.id
    if what == "new":
        await start_wizard(c.message, state)
    elif what == "projects":
        await show_projects(c.message, uid)
    elif what == "status":
        await show_status(c.message, uid)
    elif what == "cost":
        await show_cost(c.message, uid)
    elif what == "settings":
        await show_settings(c.message, uid)
    await c.answer()


# --------------------------------------------------------------------- ishga

async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN yo'q. .env fayliga qo'ying.")
        sys.exit(1)
    bot = Bot(token)
    log.info("Studio ishga tushdi — LLM: %s", LLM.name)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
