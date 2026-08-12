"""'Daftar' filmini loyiha fayli sifatida yaratadi — tizim uchun namuna."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kinoai.project import Project, Shot, Element, StyleBible, Stage

BASE = ("Vertical 9:16 composition, shot on 35mm film, anamorphic lens, "
        "shallow depth of field, natural light only. Central Asian people "
        "with warm olive skin, dark almond eyes, broad cheekbones, black hair. "
        "Uzbek domestic architecture: sun-dried clay brick, carved wooden doors, "
        "patterned cotton textiles. Photographic realism, not illustration")

GRADES = {
    "cold": ("Desaturated near-monochrome, cold blue-grey shadows, heavy film "
             "grain, low contrast, faded highlights"),
    "turn": ("Colour returning after monochrome, first warm golden light, "
             "soft and hopeful"),
    "warm": ("Warm golden colour grade, rich saturation, soft natural "
             "highlights, gentle contrast"),
    "bright": "Bright clean daylight, high key, no harsh shadows",
}

ELS = [
    Element(id="daftar", name="a worn handwritten notebook with yellowed paper",
            kind="prop", note="filmning qahramoni — barcha kadrlarda bir xil"),
    Element(id="kema", name="a large rusted fishing vessel on dry seabed",
            kind="environment", note="5 va 11-kadrda aynan bir xil rakurs"),
]

SHOTS = [
 (1,"Daftar","A dark room at night. On a low wooden table an open notebook, an inkwell and a single burning candle. Frost on the window behind. Static wide shot, notebook in lower third",4,["daftar"],"cold","Bir daftar bor edi. Tugatilmagan."),
 (2,"To'xtagan qo'l","Extreme close-up of a weathered hand holding a wooden pen above a half-written page, frozen mid-motion. A thin blade of hard white light falls across the page",4,["daftar"],"cold","Uni yozgan qo'l — o'ttiz sakkizinchi yilning kuzida to'xtadi."),
 (3,"Sham o'chdi","Total darkness. A single open notebook page catches the last dim light, floating in black emptiness. High angle looking down",3,["daftar"],"cold","Daftar qoldi. Yashirindi. Kutdi."),
 (4,"Paxta","An endless cotton field under a white overexposed sky. In the foreground a child's small hand reaching into a cotton boll. Low camera angle from ground level",3,[],"cold","Yer bir ekinga majbur bo'ldi."),
 (5,"Orol","A large rusted fishing vessel tilted on cracked dry seabed, no water anywhere. Wide shot from below against a pale empty sky",3,["kema"],"cold","Dengiz chekindi."),
 (6,"Til qaytdi","A blank enamel plaque on a plastered school wall, morning sunlight striking it directly. Low angle looking up, deep blue sky above",3,[],"turn","Keyin — til qaytdi."),
 (7,"Bayroq","A flag rising on a tall pole seen from directly below against the sun, fabric backlit and glowing. Extreme low angle, lens flare",3,[],"warm","Keyin — nom qaytdi."),
 (8,"Uzatish","An elderly wrinkled hand passing a worn notebook into a young open palm. Sunlit courtyard with grapevine canopy blurred behind. Close-up on hands",4,["daftar"],"warm","Daftar qo'ldan qo'lga o'tdi."),
 (9,"Non","A farmer's dusty calloused hands holding a round flatbread over ripe golden wheat. Medium close shot, warm low sun behind",4,[],"warm",""),
 (10,"Yangi avlod","A young woman at a desk at night, face lit only by the cool glow of a screen off-frame, concentrating. The worn notebook lies beside her keyboard",4,["daftar"],"warm","Har bir qo'l unga bir satr qo'shdi."),
 (11,"Orol tiriladi","The same rusted vessel on dry seabed, now young green saxaul saplings growing around its hull. Ground level looking up past the saplings. Golden hour",4,["kema"],"warm","Va eng qora sahifa — yashil bo'la boshladi."),
 (12,"Bo'sh sahifa","Looking straight down at a blank notebook page as a child's hand begins to write with a pencil. The pencil tip has just touched the paper",5,["daftar"],"bright","Yangi hayot va kelajakni — biz yozamiz."),
]

p = Project(
    title="Daftar", kind="film", target_seconds=60, stage=Stage.PREPRODUCTION,
    logline=("1938-yilda to'xtagan qo'lyozma daftar avloddan avlodga o'tadi "
             "va bugungi bola uning bo'sh sahifasini yozishni boshlaydi."),
    script="(to'liq ssenariy alohida saqlanadi)",
    style=StyleBible(base=BASE, grades=GRADES,
                     negative="no text, not cartoon", aspect="9:16",
                     model_image="nano_banana_2", model_video="seedance_2_0"),
    elements=ELS,
    shots=[Shot(n=n, scene=sc, prompt=pr, duration=d, elements=e,
                grade=g, narration=nr)
           for n, sc, pr, d, e, g, nr in SHOTS],
)
for s in p.shots:
    s.description = s.scene

p.save("examples/daftar.json")
print(f"Yaratildi: examples/daftar.json  ({len(p.shots)} kadr, {p.total_seconds():.0f}s)")
