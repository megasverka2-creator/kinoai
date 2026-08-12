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

from kinoai import agents, store
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
        [("⬅️ Oldingi bosqich", f"back:{stage}")],
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


def render(stage: str, content: dict) -> str:
    """Bosqich natijasini o'qiladigan matnga aylantiradi."""
    if stage == "producer":
        risks = content.get("risks") or []
        return (
            f"<b>{content.get('title', '—')}</b>\n\n"
            f"<i>{content.get('logline', '')}</i>\n\n"
            f"{content.get('synopsis', '')}\n\n"
            f"Janr: {content.get('genre', '—')}  |  "
            f"Ohang: {content.get('tone', '—')}\n"
            f"Mavzu: {content.get('theme', '—')}\n"
            f"Qahramon: {content.get('protagonist', '—')}\n"
            f"Maqsad: {content.get('goal', '—')}\n"
            f"To'siq: {content.get('conflict', '—')}\n"
            + (f"\n⚠️ Risklar: {', '.join(risks[:4])}" if risks else "")
        )
    if stage == "screenwriter":
        sc = content.get("scenes", [])
        head = f"<b>Ssenariy</b> — {len(sc)} sahna, " \
               f"{content.get('total_duration', 0):.0f}s\n\n"
        body = "\n".join(
            f"<b>{s.get('id')}</b> {s.get('heading', '')} "
            f"({s.get('duration', 0):.0f}s)\n{s.get('action', '')[:220]}"
            for s in sc[:8]
        )
        more = f"\n\n… yana {len(sc) - 8} sahna" if len(sc) > 8 else ""
        return head + body + more
    if stage == "script_doctor":
        iss = content.get("issues", [])
        blocker = [i for i in iss if i.get("severity") == "blocker"]
        lines = [f"<b>Audit</b> — {len(iss)} ta eslatma"]
        if blocker:
            lines.append(f"🔴 {len(blocker)} ta blocker")
        for i in iss[:6]:
            lines.append(f"• [{i.get('severity', '?')}] "
                         f"{i.get('description', '')[:160]}")
        lines.append(f"\n{content.get('verdict', '')}")
        return "\n".join(lines)
    if stage == "cinematographer":
        sh = content.get("shots", [])
        hard = [s for s in sh
                if s.get("generation_difficulty") in ("high", "very_high")]
        lines = [f"<b>Kadrlar</b> — {len(sh)} ta, "
                 f"{content.get('total_duration', 0):.0f}s"]
        if hard:
            lines.append(f"⚠️ {len(hard)} ta kadr qiyin generatsiya")
        for s in sh[:10]:
            lines.append(
                f"<b>{s.get('id')}</b> {s.get('duration', 0):.0f}s "
                f"{s.get('shot_size', '')} — {s.get('action', '')[:90]}"
            )
        if len(sh) > 10:
            lines.append(f"… yana {len(sh) - 10} kadr")
        return "\n".join(lines)
    return str(content)[:3000]


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
        proj["shots"] = res.data.get("shots", [])
    store.save(proj)

    note = "\n\n<i>demo rejim — kalit ulanmagan</i>" if LLM.name == "demo" else ""
    await wait.edit_text(
        render(stage, res.data) + note,
        parse_mode="HTML", reply_markup=review_kb(stage),
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
    await state.set_state(Wizard.kind)
    await m.answer("Format tanlang:", reply_markup=kb([
        [("🎥 Film", "kind:film"), ("🎨 Multfilm", "kind:multfilm")],
        [("📱 Reels / Shorts", "kind:shorts"), ("📺 Reklama", "kind:ad")],
    ]))


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
    proj = store.new_project(
        m.from_user.id, data.get("kind", "film"), data.get("length", 60)
    )
    proj["idea"] = m.text
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
            await c.message.answer(render(prev, v["content"]),
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
        await c.message.answer(render(stage, v["content"]),
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
