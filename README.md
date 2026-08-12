# KinoAI — AI studiya yadrosi

Bosqichma-bosqich film/multfilm ishlab chiqarish tizimi.
Bu **birinchi versiya, o'zingiz uchun**: auth yo'q, to'lov yo'q, interfeys yo'q.
Faqat yadro — ishlaydigan.

## Nima ishlaydi

- Loyiha holati (ssenariy, kadrlar, uslub bibliyasi) — bitta JSON faylda
- Prompt avtomatik yig'iladi: kadr + uslub + elementlar + rang bloki
- Bosqich qulfi: yopilmagan bosqichdan keyingisiga o'tib bo'lmaydi
- Generatsiyadan oldin ogohlantirish (kredit tejaydi)
- Animatik yig'ish — suratlardan, arzon
- Yakuniy montaj — FFmpeg, diktor va musiqa bilan

## O'rnatish

Faqat Python 3.10+ va FFmpeg kerak. Boshqa bog'liqlik yo'q.

```bash
ffmpeg -version    # bo'lishi shart
```

## Buyruqlar

```bash
python -m kinoai.cli status   examples/daftar.json
python -m kinoai.cli check    examples/daftar.json
python -m kinoai.cli prompts  examples/daftar.json
python -m kinoai.cli advance  examples/daftar.json
python -m kinoai.cli animatic examples/daftar.json  animatik.mp4
python -m kinoai.cli render   examples/daftar.json  film.mp4
```

## Tuzilma

| Fayl | Vazifasi |
|---|---|
| `project.py` | Loyiha modeli, kadr slotlari, bosqich qulfi |
| `prompt.py` | Prompt yig'uvchi va tekshiruvchi |
| `assemble.py` | FFmpeg montaj |
| `providers/base.py` | AI xizmat interfeysi |
| `cli.py` | Buyruq qatori |

## Ikkita asosiy qaror

**1. Kadr — bu slot, manba emas.**
Har kadrda `source` maydoni bor: `ai`, `upload`, `external`, `empty`.
Tizim kadrning qayerdan kelganiga befarq — telefon videosi ham,
AI generatsiyasi ham, DaVinci'dan qaytgan fayl ham bir xil yo'ldan o'tadi.
Qo'lda ishlash "istisno" emas, tizimning tabiiy qismi.

**2. Provayder — interfeys ortida.**
Higgsfield to'g'ridan-to'g'ri chaqirilmaydi. `Provider` sinfi ortida turadi.
Ertaga boshqa xizmat arzonroq bo'lsa — bitta fayl yoziladi, tizim tegilmaydi.

## Keyingi qadam: provayder ulash

`providers/base.py` dagi `Provider` dan meros oling:

```python
from kinoai.providers.base import Provider, Take

class Higgsfield(Provider):
    name = "higgsfield"

    def __init__(self, api_key: str):
        self.key = api_key

    def image(self, prompt, aspect="9:16", n=1):
        ...  # so'rov yuborish, faylni saqlash
        return [Take(path=saqlangan_yol, cost=narx)]

    def video(self, prompt, seconds, start_image="", end_image="",
              aspect="9:16", n=1):
        ...

    def speech(self, text, voice=""):
        ...
```

Avval `DryRun` provayderi bilan sinang — u hech narsa yaratmaydi,
faqat nima yuborilishini yozadi. Butun oqimni bir tiyinsiz tekshirasiz.

## Ish tartibi

1. `preproduksiya` — kadrlarni yozing, uslub blokini sozlang
2. `check` — ogohlantirishlarni tuzating
3. `animatik` — suratlar yarating (arzon), yig'ing, ko'ring
4. Yoqmasa — 1-qadamga qayting. **Video generatsiyaga hali o'tmang.**
5. `produksiya` — faqat tasdiqlangandan keyin video yarating
6. `render` — yakuniy montaj

4-qadam eng muhimi. Butun pul 5-qadamda yonadi, shuning uchun
undan oldin filmni qo'pol ko'rinishda ko'rib olish shart.

## Hali yo'q (ataylab)

- Provayder implementatsiyasi — kalitlar sizda
- Navbat va fon vazifalari — uzun loyihalar uchun keyin kerak bo'ladi
- Musiqa — litsenziyalangan kutubxona yoki alohida API
- EDL/XML eksport — tashqi montaj ilovalari uchun
- Sahnalarga bo'lish — 5 daqiqadan uzun ishlar uchun zarur

---

# v0.2 — TZ integratsiyasi

TZ v1.0 dan to'rtta markaziy narsa yadroga kiritildi.

## Yangi modullar

| Fayl | TZ bo'limi | Vazifasi |
|---|---|---|
| `ids.py` | 16 | Immutable ID: SH014 butun pipeline bo'ylab o'zgarmaydi |
| `versioning.py` | 2.1, 2.4, 18 | Status, versiya tarixi, dependency graph |
| `ledger.py` | 8.4, 22 | Cost ledger, budget guard, retry cheklovi |
| `compiler.py` | 8 | Canonical package -> prompt (provayderdan mustaqil) |

## Tuzatilgan xato (v0.1)

Uslub bloki bo'linmas edi va har kadrga to'liq yopishardi. Natijada
odamsiz kadrga ham "Central Asian people with olive skin" qo'shilardi —
model esa kadrda yo'q odamni chizishga urinadi.

Endi uslub modullarga bo'lingan. Har kadr faqat o'ziga keraklisini
oladi:

```python
compile_prompt(pkg, base, modules, active=[])                  # odamsiz kadr
compile_prompt(pkg, base, modules, active=["people","interior"])  # odamli
```

Shuningdek qismiy takror ham olib tashlanadi ("Photographic realism,
not illustration" + "photographic realism" -> bittasi qoladi).

## Ta'sir hisoboti

O'zgartirishdan OLDIN nima buzilishini ko'rsatadi:

```python
g = Graph()
g.link("SC004", "SH014", Impact.FULL_REGEN)
print(g.preview("SC004", Impact.FULL_REGEN))
```

Bu foydalanuvchi pulini tejaydi: "bu o'zgarish 14 ta kadrni qayta
yaratishga majbur qiladi" degan ogohlantirish.

## Generation Difficulty

Generatsiyadan oldin qiyinlikni baholaydi va sababini aytadi:

```python
assess_difficulty(pkg, action_beats=3, characters=3)
# -> ("very_high", "12s — 10s dan uzun kadr buziladi; 3 ta harakat...")
```

## Sinov

```bash
python3 examples/smoke_test.py
```

## TZ dan ATAYLAB kiritilmagan

Bular TZ da qolsin, lekin birinchi qurilishga kirmasin:

- Universe / Series / Season / Episode — ma'lumotlar modelini bir necha
  barobar murakkablashtiradi, MVP'da qiymati nol
- 19 ta agent — boshida 4 tasi yetadi
- Easy / Professional / Hybrid uch rejim — bitta rejim
- Branch va diff — versiya saqlansin, branch keyin
- QC Supervisor 9 ta audit moduli — MVP'da odam qaraydi
- To'liq dependency invalidation engine — hozircha oddiy bayroq mantiqi

---

# v0.3 — Telegram bot (TZ 20-bo'lim)

## Ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env
python -m bot.main
```

`.env` bo'sh bo'lsa bot **demo rejimda** ishlaydi: haqiqiy LLM
chaqirilmaydi, oqim/tugmalar/saqlash/bosqich qulfi bir tiyinsiz
sinaladi. Faqat `TELEGRAM_BOT_TOKEN` majburiy.

## Komandalar (TZ 20.2)

| Komanda | Natija |
|---|---|
| `/start` | Studio kirish |
| `/new` | Yangi loyiha wizard |
| `/projects` | Loyihalar ro'yxati |
| `/status` | Joriy bosqich va progress |
| `/cost` | Loyiha xarajati |
| `/settings` | Sifat rejimi |
| `/export` | Phase 6 da |

## Stage review tugmalari (TZ 20.3)

Tasdiqlash va qulflash · AI bilan tahrir · Qayta yaratish ·
Qo'lda kiritish · Versiyalar · Oldingi bosqich

## MVP oqimi

```
brief -> producer -> screenwriter -> script_doctor -> cinematographer
```

Har bosqich natijasi versiya sifatida saqlanadi. Tasdiqlangan versiya
**o'chirilmaydi** — tahrir yangi versiya yaratadi. Orqaga qaytish xavfsiz.

## Agentlar (TZ 15)

TZ dagi 19 tadan 4 tasi ishlaydi:

| Agent | O'zgartira olmaydigan master |
|---|---|
| Creative Producer | Original idea / Must Keep |
| Screenwriter | Locked scene / user constraints |
| Script Doctor | Current screenplay (faqat taklif beradi) |
| Cinematographer | Locked Style Bible |

Agentlar bir-biriga chat tarixi uzatmaydi. `agents.context_for()` har
bosqichga faqat kerakli tasdiqlangan kontekstni yig'adi (TZ 15.1) — bu
token xarajati va gallyutsinatsiyani kamaytiradi.

## Railway'ga joylash

1. GitHub'ga push
2. Railway'da New Project -> Deploy from GitHub
3. Variables: `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY` yoki `OPENAI_API_KEY`
4. Deploy

`railway.json` va `Procfile` tayyor. Bot polling rejimida ishlaydi,
web port kerak emas.

⚠️ Railway diski vaqtinchalik — `/data/` qayta deploy'da o'chadi.
Doimiy saqlash uchun Volume yoki PostgreSQL kerak (TZ 17).
