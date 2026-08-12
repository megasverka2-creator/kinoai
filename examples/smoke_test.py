import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kinoai import ids, compiler as C
from kinoai.versioning import Artifact, Graph, Impact, Status
from kinoai.ledger import Ledger, BudgetExceeded

# --- ID ---
assert ids.make('shot', 14) == 'SH014'
assert ids.state('CHR001', 3) == 'CHR001_ST03'
assert ids.take('SH014', 3) == 'SH014_T03'
assert ids.parse('CHR001_ST03') == ('character', 1, 3)
assert ids.next_id('shot', ['SH001','SH007']) == 'SH008'
print("ID: ok")

# --- versiya ---
a = Artifact(id='SC004', kind='scene')
a.add({'text':'v1'}, source='ai')
a.approve()
a.add({'text':'v2'}, source='user', note='dialog qisqartirildi')
assert a.current().n == 1          # tasdiqlangan hali ham Master
assert a.head().n == 2
a.approve()
assert a.current().n == 2
print("Versiya: ok")

# --- dependency ---
g = Graph()
g.link('SC004','SH014', Impact.FULL_REGEN)
g.link('SC004','SH015', Impact.FULL_REGEN)
g.link('SH014','KFR_SH014', Impact.FULL_REGEN)
g.link('KFR_SH014','SH014_T03', Impact.FULL_REGEN)
g.link('SH014_T03','CUT_V05', Impact.REVIEW)
print(g.preview('SC004', Impact.REVIEW))
print()
print(g.preview('SC004', Impact.FULL_REGEN))
print()

# --- ledger ---
L = Ledger(project_cap=10.0)
e = L.estimate('SH014','video','prov', 3.5, units=4)
L.settle(e, 3.9, job_id='j1')
L.estimate('SH014','video','prov', 3.5)
L.estimate('SH015','image','prov', 0.2)
try:
    L.estimate('SH016','video','prov', 9.0)
    print("XATO: budjet ushlamadi")
except BudgetExceeded as x:
    print("Budjet guard ishladi:", x)
print()
print(L.report())
print()

# --- compiler: v0.1 XATOSI TUZATILDIMI ---
BASE = ("Vertical 9:16 composition, shot on 35mm film, anamorphic lens, "
        "natural light only. Photographic realism, not illustration")
MODULES = {
  "people": "Central Asian people with warm olive skin, dark almond eyes, broad cheekbones",
  "interior": "Uzbek domestic architecture: sun-dried clay brick, carved wooden doors, patterned cotton textiles",
  "landscape": "Arid Central Asian steppe, salt crust, sparse vegetation",
}
COLD = "Desaturated near-monochrome, cold blue-grey shadows, heavy film grain"

# 3-kadr: qorong'ida sahifa. ODAM YO'Q, INTERYER YO'Q.
p3 = C.Package(shot_id='SH003', scene_id='SC001',
    prompt="Total darkness. A single open notebook page catches the last dim light, floating in black emptiness. High angle looking down",
    identity=["a worn handwritten notebook with yellowed paper"],
    duration=3, forbidden=["no text","not cartoon"])
print("--- SH003 (odamsiz kadr) ---")
print(C.compile_prompt(p3, BASE, MODULES, active=[], grade=COLD))
print()

# 8-kadr: qo'llar, hovli. ODAM BOR, INTERYER BOR.
p8 = C.Package(shot_id='SH008', scene_id='SC003',
    prompt="An elderly wrinkled hand passing a worn notebook into a young open palm. Sunlit courtyard with grapevine canopy blurred behind",
    identity=["a worn handwritten notebook with yellowed paper"],
    duration=4, forbidden=["no text"])
print("--- SH008 (odamli kadr) ---")
print(C.compile_prompt(p8, BASE, MODULES, active=["people","interior"], grade="Warm golden colour grade"))
print()

# difficulty
lvl, why = C.assess_difficulty(C.Package(shot_id='SH020', duration=12), action_beats=3, characters=3)
print("SH020 qiyinlik:", lvl, "|", why)
