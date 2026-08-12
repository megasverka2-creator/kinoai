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
