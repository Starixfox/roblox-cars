"""GAC AION RAY7 (Sketchfab, GARAGISTA, CC BY 4.0) -> Roblox, with damage parts.
Adapted from the GT3 RS pipeline (porsche-gt3rs/scripts/prep2.py).

Usage (via run.ps1 / wrap.py):  prep.py high   or   prep.py lite

Output part names:  <Group>__<Material>[_n]                unchunked part
                    <Group>__C<nn>__<Material>[_n]         chunk part
                    <Group>__C<nn>__DMG__<Material>[_n]    cracked glass twin, hidden in game
Detachable: Hood, Trunk, Door_L, Door_R, Door_RL, Door_RR, FrontBumper, RearBumper,
            Mirror_L, Mirror_R, Wheel_LF, Wheel_RF, Wheel_LR, Wheel_RR
Ride-along: Mirror_* and Glass_Door_L/R on Door_L/R, Glass_Door_RL/RR on Door_RL/RR
Fixed: Body_Front, Body_Mid, Body_Rear, Interior, SteeringWheel, Brakes, HeadLight_L/R,
       TailLight_L/R, Glass_Windshield, Glass_Rear, Glass_Roof, Glass_Quarter_L/R
"""
import bpy, bmesh, os, sys, json, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

VARIANT = (sys.argv[1] if len(sys.argv) > 1 else "high").lower()
ROOT = r"C:\Users\jordan\RobloxCars\gac-aion-ray7"
GLB = os.path.join(ROOT, "source", "source", "GAC AION RAY7.glb")
OUT = os.path.join(ROOT, "roblox")
NAME = "GAC_AionRay7_" + VARIANT.capitalize()
MAX_TRIS = 19000
TEX_MAX = 1024 if VARIANT == "high" else 512
SMOOTH_ANGLE = math.radians(35)
# source is 3.94x real size, centred at x=-0.12, tyres 0.484 below z=0: real size 4.96 m
SRC_TO_REAL = Matrix.Scale(0.25, 4) @ Matrix.Translation((0.12, -0.075, 0.484))

ROLE_BUDGET = {
    "high": {"Body": 44000, "Interior": 15000, "SteeringWheel": 2000, "Glass": 5000,
             "Lights": 6000, "Brakes": 1600, "Wheel": 5500},
    "lite": {"Body": 17000, "Interior": 4000, "SteeringWheel": 600, "Glass": 2000,
             "Lights": 2000, "Brakes": 500, "Wheel": 1600},
}[VARIANT]

DETACHABLE = {"Hood", "Trunk", "Door_L", "Door_R", "Door_RL", "Door_RR", "FrontBumper", "RearBumper",
              "Wing", "Mirror_L", "Mirror_R", "Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR"}
CRACK_GROUPS = {"Glass_Windshield", "Glass_Rear", "Glass_Roof", "Glass_Door_L", "Glass_Door_R",
                "Glass_Door_RL", "Glass_Door_RR", "Glass_Quarter_L", "Glass_Quarter_R"}

CHUNKS = {
    "high": {"Hood": 10, "Trunk": 8, "Door_L": 8, "Door_R": 8, "Door_RL": 7, "Door_RR": 7,
             "FrontBumper": 11, "RearBumper": 11, "Body_Front": 9, "Body_Mid": 9, "Body_Rear": 10,
             "Glass_Windshield": 22, "Glass_Rear": 14, "Glass_Roof": 10, "Glass_Door_L": 9, "Glass_Door_R": 9,
             "Glass_Door_RL": 7, "Glass_Door_RR": 7, "Glass_Quarter_L": 4, "Glass_Quarter_R": 4},
    "lite": {"Hood": 7, "Trunk": 6, "Door_L": 5, "Door_R": 5, "Door_RL": 5, "Door_RR": 5,
             "FrontBumper": 7, "RearBumper": 7, "Body_Front": 7, "Body_Mid": 7, "Body_Rear": 7,
             "Glass_Windshield": 13, "Glass_Rear": 8, "Glass_Roof": 7, "Glass_Door_L": 6, "Glass_Door_R": 6,
             "Glass_Door_RL": 5, "Glass_Door_RR": 5, "Glass_Quarter_L": 3, "Glass_Quarter_R": 3},
}[VARIANT]
GLASS_MAX_EDGE = 0.11 if VARIANT == "high" else 0.17

# ---- brand marks / junk -----------------------------------------------------------
DELETE_OBJS = {
    "Plane001.001",                       # dealer advert sticker (QR codes) behind the mirror
    "HYPERSSRPart197.001", "ST.001",      # steering wheel AION logo + marks
    "RAY40.001",                          # front AION lettering
    "RAY12.001",                          # rear AION lettering
    "RAY126.001", "7484.001", "RAY18.001", "RAY128.001",   # caliper logo plates
    "1151.001",                           # steering wheel AION lettering (chrome)
    "RAY139.001",                         # near-copy of RAY95 (left door trim), z-fights
}
# LOGO_BLUE = hub inserts, 1_NULL = black copies of the panels / shadow cards (z-fight after decimation)
DELETE_MATS = {"LOGO_BLUE", "1_WhiteLogo", "Material #27", "1_NULL"}
# objects whose lettering is cut into a panel: replaced by a plain box of the same size
REPLACE_WITH_BOX = {"RAY89.001"}          # front AION plate between the headlights
# separate letter islands that lie completely inside a box (real metres): deleted
DELETE_ISLANDS_IN_BOX = [
    ({"RAY42.001", "RAY64.001", "RAY90.001", "RAY93.001"}, (-0.14, 0.14), (2.36, 2.48), (0.862, 0.915)),  # rear AION
    ({"RAY90.001", "RAY113.001", "RAY117.001"}, (-0.66, -0.33), (2.20, 2.52), (0.62, 0.86)),              # Ray7 script
    ({"RAY90.001", "RAY113.001", "RAY117.001"}, (0.33, 0.66), (2.20, 2.52), (0.62, 0.86)),
]

# ---- classification tables (object names as imported) -------------------------------
D = ".001"
PAINT_OBJ = {  # body-colour panels (and their black backs) -> group or ZONE
    "RAY02": "Door_L", "RAY114": "Door_R", "RAY112": "Door_RL", "RAY116": "Door_RR",
    "RAY104": "Door_L", "RAY106": "Door_R", "RAY105": "Door_RL", "RAY107": "Door_RR",
    "RAY145": "Door_L", "RAY143": "Door_R", "RAY146": "Door_RL", "RAY144": "Door_RR",
    "RAY108": "FrontBumper", "RAY120": "FrontBumper", "RAY110": "Hood",
    "RAY121": "Trunk", "RAY113": "Trunk", "RAY117": "RearBumper",
    "RAY109": "ZONE", "RAY147": "ZONE", "RAY111": "ZONE", "RAY115": "ZONE", "RAY142": "ZONE",
    "RAY118": "ZONE", "RAY119": "ZONE", "RAY04": "ZONE",
}
PAINT_OBJ = {k + D: v for k, v in PAINT_OBJ.items()}
# exterior objects that do not sit under the RAY00 node
EXTRA_BODY = {n + D for n in ("1111111", "15317", "RAY138", "RAY88", "RAY29", "RAY141", "RAY15",
                              "RAY04", "RAY104", "RAY105", "RAY106", "RAY107", "RAY142", "RAY143",
                              "RAY144", "RAY145", "RAY146", "GEO_Plate001", "GEO_Plate002",
                              "mesh004", "mesh006", "GEO_wiperF_arm_5", "GEO_wiperF_arm_6",
                              "GEO_wiperF_arm_1", "GEO_wiperF_arm_010")}
HEAD_LIGHTS = {n + D for n in ("RAY100", "RAY36", "RAY22", "RAY23", "RAY41", "RAY65", "RAY28", "RAY56",
                               "RAY30", "RAY92", "RAY37", "RAY54")}
TAIL_LIGHTS = {n + D for n in ("RAY34", "RAY43", "RAY26", "RAY27", "RAY63", "RAY91", "RAY25", "RAY77",
                               "RAY31", "RAY94", "RAY33", "RAY44", "RAY38", "RAY66")}
TRUNK_BAR = {n + D for n in ("RAY42", "RAY93", "RAY64", "RAY03", "R", "RAY90", "RAY61", "RAY62")}
# black door trims and window frames that lie completely within one door
FORCE_GROUP = {"RAY139.001": "Door_L", "RAY95.001": "Door_L", "RAY140.001": "Door_R", "RAY67.001": "Door_R",
               "1111111.001": "Door_L", "RAY138.001": "Door_RL", "RAY88.001": "Door_RL",
               "RAY141.001": "Door_RR", "RAY29.001": "Door_RR"}
MIRROR_OBJ = {n + D for n in ("RAY39", "RAY78", "RAY47", "RAY48")}
GLASS_OBJ = {n + D for n in ("RAY05", "RAY20", "RAY21", "RAY72", "RAY73", "RAY74", "RAY75", "RAY76",
                             "RAY129", "RAY130", "RAY131", "RAY132", "RAY133", "RAY134", "RAY135", "RAY136")}
ROOF_GLASS = {"RAY21" + D, "RAY131" + D}
GLASS_MATS = {"1_Glass_Black", "insideglass", "1_LightGlassBlack"}

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
scene = bpy.context.scene
log = {"variant": VARIANT, "removed": [], "roles": {}, "groups": {}, "parts": []}

for o in [o for o in scene.objects if o.parent is None]:
    o.matrix_world = SRC_TO_REAL @ o.matrix_world
bpy.context.view_layer.update()


def tris_me(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def tris(o):
    return tris_me(o.data)


def meshes():
    return [o for o in scene.objects if o.type == 'MESH']


def override(o):
    return bpy.context.temp_override(object=o, active_object=o,
                                     selected_objects=[o], selected_editable_objects=[o])


def side(x):
    return "L" if x > 0 else "R"   # car faces -Y, so +X is the driver's left


def ancestors(o):
    out = []
    p = o.parent
    while p:
        out.append(p.name)
        p = p.parent
    return out


def principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat and mat.node_tree else None


# =============================================================== 0. record hierarchy, world matrices
anc = {o.name: ancestors(o) for o in meshes()}
world = {o.name: o.matrix_world.copy() for o in meshes()}


def wbounds(o):
    pts = [world[o.name] @ v.co for v in o.data.vertices]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


# =============================================================== 1. duplicates, logos, materials
seen = []
for o in sorted(meshes(), key=lambda o: o.name):
    if not o.data.polygons:
        continue
    key = (tuple(m.name for m in o.data.materials if m), tris(o))
    lo, hi = wbounds(o)
    dup = None
    for k, l2, h2, n2 in seen:
        if k == key and (lo - l2).length < 0.008 and (hi - h2).length < 0.008:
            dup = n2
            break
    if dup:
        log["removed"].append(f"{o.name} (duplicate of {dup})")
        bpy.data.objects.remove(o, do_unlink=True)
    else:
        seen.append((key, lo, hi, o.name))

for o in list(meshes()):
    mats = {m.name for m in o.data.materials if m}
    if o.name in DELETE_OBJS or mats & DELETE_MATS:
        log["removed"].append(o.name)
        bpy.data.objects.remove(o, do_unlink=True)


def set_bsdf(b, metal, rough):
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough


# Sketchfab conversion made every material alpha-blended and fully metallic: make them sane.
for m in bpy.data.materials:
    b = principled(m)
    if not b:
        continue
    nt = m.node_tree
    for n in [n for n in nt.nodes if n.type == 'TEX_IMAGE' and not n.outputs[0].links]:
        nt.nodes.remove(n)
    n = m.name
    if n in GLASS_MATS:
        set_bsdf(b, 0.0, 0.05)
        continue
    if n != "Alpha":   # interior warning stickers keep their alpha
        for l in list(b.inputs["Alpha"].links):
            nt.links.remove(l)
        b.inputs["Alpha"].default_value = 1.0
        try:
            m.surface_render_method = 'DITHERED'
        except Exception:
            m.blend_method = 'OPAQUE'
    if n in ("1_BODY", "1_BODY2"):
        set_bsdf(b, 0.35, 0.28)
        for l in list(b.inputs["Normal"].links):
            nt.links.remove(l)
    elif any(k in n.lower() for k in ("chrome", "rimc", "mirror", "paint_silver")):
        set_bsdf(b, 0.95, 0.18)
    elif n == "EXT_tyre":
        set_bsdf(b, 0.0, 0.9)
    elif n in ("TailRED", "RedNM", "WhiteNM", "1_Beam", "lights_glass"):
        set_bsdf(b, 0.0, 0.3)
    elif n in ("1_BLACKRF", "1_BlackRF", "1_NULL", "JiaoTiao", "GT500_2019_Coloured_Material"):
        set_bsdf(b, 0.0, 0.45)
    else:
        set_bsdf(b, 0.0, 0.65)


def img_px(img):
    w, h = img.size
    a = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, img.channels)


def img_set(img, a):
    img.pixels.foreach_set(a.ravel())
    img.update()
    img.pack()


def fill_rects(img_name, rects_top_left, color=None):
    """rects in pixel coords of the image file, origin top-left (as seen in a viewer).
    color=None: fill with the median colour of a thin border around the rect."""
    img = bpy.data.images.get(img_name)
    if not img:
        print("missing image", img_name)
        return
    a = img_px(img)
    h, w = a.shape[:2]
    for x0, y0, x1, y1 in rects_top_left:
        X0, X1 = max(0, int(x0)), min(w, int(x1))
        # The PNGs in the download's textures/ folder are stored upside down compared to the
        # images embedded in the glb, so their top-left coords are already Blender rows.
        Y0, Y1 = max(0, int(y0)), min(h, int(y1))
        if color is None:
            b = 6
            ring = np.concatenate([
                a[max(0, Y0 - b):Y0, X0:X1].reshape(-1, a.shape[2]),
                a[Y1:min(h, Y1 + b), X0:X1].reshape(-1, a.shape[2]),
                a[Y0:Y1, max(0, X0 - b):X0].reshape(-1, a.shape[2]),
                a[Y0:Y1, X1:min(w, X1 + b)].reshape(-1, a.shape[2])])
            c = np.median(ring, axis=0)
            a[Y0:Y1, X0:X1] = c
        else:
            a[Y0:Y1, X0:X1, :len(color)] = color
    img_set(img, a)
    log["removed"].append(f"texture {img_name}: {len(rects_top_left)} areas blanked")


# interior screen atlas: small brand icon on the cluster, steering wheel logo in the screen photo
fill_rects("aion_hypergt_Int1_Diffuse", [(790, 70, 850, 125), (282, 1190, 476, 1372)])
# warning sticker atlas: TOYOTA logo
fill_rects("000002DA6BA25BF8-000002DA6BA25BF8.dds", [(262, 4, 532, 64)])
# screens: dealer advert with QR codes in the upper half
fill_rects("1AMo-1AMo.dds", [(0, 0, 1024, 520)], (0.01, 0.01, 0.012))
# license plates ("Ray 7"): completely blank
fill_rects("Plate_D-Plate_D.dds", [(0, 0, 4096, 4096)], (0.015, 0.015, 0.015))


def blank_tyre(img_name, flat_from_ring):
    """Replace the sidewall ring (MICHELIN / Pilot Sport text) with a plain fill."""
    img = bpy.data.images.get(img_name)
    if not img:
        print("missing image", img_name)
        return
    a = img_px(img)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = w / 2, h / 2
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (w / 1024)
    tread = (xx >= 245 * w / 1024) & (xx <= 780 * w / 1024) & (yy >= h - 815 * h / 1024) & (yy <= h - 205 * h / 1024)
    ring = (r >= 380) & ~tread
    if flat_from_ring:
        fill = np.median(a[(r >= 380) & (r <= 400) & ~tread], axis=0)
    else:
        fill = np.array([0.5, 0.5, 1.0, 1.0][:a.shape[2]], dtype=np.float32)
    a[ring] = fill
    img_set(img, a)
    log["removed"].append(f"texture {img_name}: sidewall lettering blanked")


blank_tyre("245_Tyre_D-245_Tyre_D.dds", True)
blank_tyre("245_Tyre_D_nm", False)

# =============================================================== 2. roles
def role_of(o):
    n = o.name
    a = anc[n]
    mats = {m.name for m in o.data.materials if m}
    if any(p.startswith(("WHEEL_", "DISC_")) for p in a):
        lo, hi = wbounds(o)
        c = (lo + hi) / 2
        return "Wheel_" + side(c.x) + ("F" if c.y < 0 else "R")
    if any(p.startswith("SUSP_") for p in a):
        return "Brakes"
    if any(p.startswith("STEER_HR") for p in a):
        return "SteeringWheel"
    if n in GLASS_OBJ:
        return "Glass"
    if n in HEAD_LIGHTS or n in TAIL_LIGHTS:
        return "Lights"
    if n in MIRROR_OBJ:
        return "Body"
    if "RAY00" in a or n in EXTRA_BODY:
        return "Body"
    if mats & GLASS_MATS:
        return "Glass"
    return "Interior"


role = {o.name: role_of(o) for o in meshes()}
lights_side = {n: ("HeadLight_" if n in HEAD_LIGHTS else "TailLight_") for n in HEAD_LIGHTS | TAIL_LIGHTS}

# =============================================================== 3. bake transforms
for o in list(meshes()):
    o.parent = None
    o.data = o.data.copy()
    o.data.transform(world[o.name])
    o.matrix_world = Matrix.Identity(4)
    if o.data.has_custom_normals:
        with override(o):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00005)
    bm.to_mesh(o.data)
    bm.free()
for o in [o for o in scene.objects if o.type == 'EMPTY']:
    bpy.data.objects.remove(o, do_unlink=True)


def bounds(pts):
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


# wheel hub centres from the tyres
wheel_centers = {}
for o in meshes():
    r = role[o.name]
    if r.startswith("Wheel_") and any(m and m.name == "EXT_tyre" for m in o.data.materials):
        lo, hi = bounds([v.co for v in o.data.vertices])
        wheel_centers[r] = (lo + hi) / 2
print("wheel centres:", {k: tuple(round(x, 3) for x in v) for k, v in wheel_centers.items()})


def island_list_bm(bm):
    bm.faces.ensure_lookup_table()
    seen_f, out = set(), []
    for f in bm.faces:
        if f.index in seen_f:
            continue
        stack, isl = [f], []
        seen_f.add(f.index)
        while stack:
            g = stack.pop()
            isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen_f:
                        seen_f.add(h.index)
                        stack.append(h)
        out.append(isl)
    return out


def delete_islands(o, test):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    kill = []
    for isl in island_list_bm(bm):
        pts = [v.co for f in isl for v in f.verts]
        lo, hi = bounds(pts)
        if test(lo, hi):
            kill += isl
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.to_mesh(o.data)
    bm.free()
    return len(kill)


for names, xa, ya, za in DELETE_ISLANDS_IN_BOX:
    for n in names:
        o = bpy.data.objects.get(n)
        if not o:
            continue
        k = delete_islands(o, lambda lo, hi: xa[0] <= lo.x and hi.x <= xa[1] and ya[0] <= lo.y and hi.y <= ya[1]
                           and za[0] <= lo.z and hi.z <= za[1])
        log["removed"].append(f"{n}: {k} lettering faces in box")
        print(f"lettering {n}: {k} faces")

for n in REPLACE_WITH_BOX:
    o = bpy.data.objects.get(n)
    if not o:
        continue
    lo, hi = bounds([v.co for v in o.data.vertices])
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((lo.x + (v.co.x + 0.5) * (hi.x - lo.x), lo.y + (v.co.y + 0.5) * (hi.y - lo.y),
                       lo.z + (v.co.z + 0.5) * (hi.z - lo.z)))
    for f in bm.faces:
        f.material_index = 0
    bm.to_mesh(o.data)
    bm.free()
    log["removed"].append(f"{n}: lettered plate replaced by a plain box")

# centre caps: AION letters are small islands right on the hub axis
for o in meshes():
    r = role[o.name]
    if r.startswith("Wheel_") and r in wheel_centers and \
            any(m and m.name == "GT500_2019_Coloured_Material" for m in o.data.materials):
        c = wheel_centers[r]
        k = delete_islands(o, lambda lo, hi: max(hi - lo) < 0.03 and
                           math.hypot((lo.y + hi.y) / 2 - c.y, (lo.z + hi.z) / 2 - c.z) < 0.04)
        if k:
            log["removed"].append(f"{o.name}: {k} cap lettering faces")
            print(f"cap lettering {o.name}: {k} faces")


def cover_object(name, verts, faces, matname):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(bpy.data.materials[matname])
    me.update()
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    return o


# centre caps: the AION lettering is engraved in the cap, cover it with a plain black disc
for r, c in wheel_centers.items():
    s = 1 if c.x > 0 else -1
    xs = [v.co.x * s for o in meshes() if role.get(o.name) == r
          and any(m and m.name == "GT500_2019_Coloured_Material" for m in o.data.materials)
          for v in o.data.vertices if math.hypot(v.co.y - c.y, v.co.z - c.z) < 0.031]
    if not xs:
        continue
    x = (max(xs) + 0.0015) * s
    n = 32
    verts = [(x, c.y, c.z)] + [(x, c.y + 0.031 * math.cos(2 * math.pi * i / n), c.z + 0.031 * math.sin(2 * math.pi * i / n))
                               for i in range(n)]
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    o = cover_object("CapCover_" + r, verts, faces, "GT500_2019_Coloured_Material")
    role[o.name] = r
    log["removed"].append(f"{r}: centre cap lettering covered by a plain disc")

# rear AION badge: letters are cut into the light bar centre, cover with a plain black plate
ys = [v.co.y for n in ("RAY42.001", "RAY64.001", "RAY90.001", "RAY93.001") if bpy.data.objects.get(n)
      for v in bpy.data.objects[n].data.vertices
      if abs(v.co.x) < 0.13 and 0.862 < v.co.z < 0.915]
if ys:
    y1 = max(ys) + 0.002
    y0 = y1 - 0.008
    x0, x1, z0, z1 = -0.128, 0.128, 0.866, 0.910
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    o = cover_object("RearLogoCover", verts, faces, "1_BLACKRF")
    role[o.name] = "Body"
    TRUNK_BAR.add(o.name)
    log["removed"].append("rear AION badge covered by a plain plate")

# =============================================================== 4. damage groups
FRONT_DOOR_Y = (-1.0, 0.18)   # front door y range (real metres); rear door 0.18 .. 1.25
REAR_DOOR_Y = (0.18, 1.25)


def zone(y):
    return "Body_Front" if y < -1.0 else ("Body_Rear" if y > 1.25 else "Body_Mid")


def paint_group(objname, c):
    g = PAINT_OBJ[objname]
    return zone(c.y) if g == "ZONE" else g


pv, pp, pgroup = [], [], []
for o in meshes():
    if o.name in PAINT_OBJ:
        base = len(pv)
        pv += [v.co.copy() for v in o.data.vertices]
        for p in o.data.polygons:
            pp.append([base + i for i in p.vertices])
            pgroup.append(paint_group(o.name, p.center))
paint_bvh = BVHTree.FromPolygons(pv, pp)


def nearest_panel(co, maxd=0.03):
    hit = paint_bvh.find_nearest(co, maxd)
    return pgroup[hit[2]] if hit and hit[0] is not None else None


def islands(me):
    edge_faces = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            edge_faces.setdefault(ek, []).append(p.index)
    seen_f, out = set(), []
    for p in me.polygons:
        if p.index in seen_f:
            continue
        stack, isl = [p.index], []
        seen_f.add(p.index)
        while stack:
            f = stack.pop()
            isl.append(f)
            for ek in me.polygons[f].edge_keys:
                for h in edge_faces[ek]:
                    if h not in seen_f:
                        seen_f.add(h)
                        stack.append(h)
        out.append(isl)
    return out


def in_mirror_box(c):
    return 0.78 <= abs(c.x) <= 1.12 and -0.92 <= c.y <= -0.50 and 0.84 <= c.z <= 1.12


def region_group(c, objname=""):
    """Areas where black trim belongs to a panel even when not touching its paint."""
    def outside_arch(fr):
        ws = [w for k, w in wheel_centers.items() if k.endswith(fr)]
        return all(math.hypot(c.y - w.y, c.z - w.z) > 0.44 for w in ws)
    if c.y < -1.80 and c.z < 0.66 and abs(c.x) < 0.95 and outside_arch("F"):
        return "FrontBumper"          # lower grille, intakes, splitter, bumper backing
    if c.y > 1.75 and c.z < 0.64 and abs(c.x) < 0.95 and outside_arch("R"):
        return "RearBumper"           # diffuser, bumper backing
    return None


def body_island_group(me, isl, objname=""):
    pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
    lo, hi = bounds(pts)
    c = (lo + hi) / 2
    size = hi - lo
    if objname in MIRROR_OBJ or (in_mirror_box(c) and max(size) < 0.35):
        return {"*": "Mirror_" + side(c.x)}
    if max(size) > 0.9:
        return None                   # big piece spanning several panels: decide per face
    if max(size) <= 0.9:
        step = max(1, len(isl) // 60)
        reg = [region_group(me.polygons[f].center, objname) for f in isl[::step]]
        for g in ("FrontBumper", "RearBumper"):
            if reg.count(g) >= 0.6 * len(reg):
                return {"*": g}
    votes = {}
    step = max(1, len(isl) // 60)
    for f in isl[::step]:
        g = nearest_panel(me.polygons[f].center, 0.045)
        if g:
            votes[g] = votes.get(g, 0) + 1
    total = len(isl[::step])
    if votes:
        g, n = max(votes.items(), key=lambda kv: kv[1])
        if n >= 0.3 * total and not g.startswith("Body_"):
            return {"*": g}
    return {"*": zone(c.y)}


def door_by_y(c):
    s = side(c.x)
    if FRONT_DOOR_Y[0] <= c.y < FRONT_DOOR_Y[1]:
        return "Door_" + s
    if REAR_DOOR_Y[0] <= c.y < REAR_DOOR_Y[1]:
        return "Door_R" + s
    return None


def glass_island_group(objname, c):
    if objname in ROOF_GLASS:
        return "Glass_Roof"
    if abs(c.x) < 0.45:
        return "Glass_Windshield" if c.y < 0.4 else "Glass_Rear"
    s = side(c.x)
    if -0.80 <= c.y < FRONT_DOOR_Y[1]:
        return "Glass_Door_" + s
    if REAR_DOOR_Y[0] <= c.y < 1.10:
        return "Glass_Door_R" + s
    return "Glass_Quarter_" + s


def extract(o, fids, name):
    nm = o.data.copy()
    keep = set(fids)
    bm = bmesh.new()
    bm.from_mesh(nm)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context='FACES')
    bm.to_mesh(nm)
    bm.free()
    no = bpy.data.objects.new(name, nm)
    scene.collection.objects.link(no)
    return no


parts = []   # (object, role, group)
for o in list(meshes()):
    r = role[o.name]
    me = o.data
    assign = {}
    if o.name in TRUNK_BAR:
        for p in me.polygons:
            c = p.center
            assign[p.index] = "Trunk" if abs(c.x) < 0.60 else "TailLight_" + side(c.x)
        r = "Lights"
    elif o.name in FORCE_GROUP:
        for p in me.polygons:
            c = p.center
            assign[p.index] = ("Mirror_" + side(c.x)) if in_mirror_box(c) and abs(c.x) > 0.86 else FORCE_GROUP[o.name]
    elif r == "Body":
        if o.name in PAINT_OBJ:
            for p in me.polygons:
                assign[p.index] = paint_group(o.name, p.center)
        else:
            for isl in islands(me):
                res = body_island_group(me, isl, o.name)
                if res is None:
                    for f in isl:
                        c = me.polygons[f].center
                        if in_mirror_box(c) and abs(c.x) > 0.86:
                            assign[f] = "Mirror_" + side(c.x)
                            continue
                        g = region_group(c, o.name) or nearest_panel(c)
                        assign[f] = g if g and not g.startswith("Body_") else zone(c.y)
                else:
                    for f in isl:
                        assign[f] = res["*"]
    elif r == "Glass":
        for isl in islands(me):
            pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
            lo, hi = bounds(pts)
            c = (lo + hi) / 2
            if o.name == "RAY20" + D or o.name == "RAY130" + D or (hi - lo).y > 1.6:
                # windshield + rear window in one mesh: per face
                for f in isl:
                    fc = me.polygons[f].center
                    assign[f] = glass_island_group(o.name, fc) if abs(fc.x) > 0.45 else \
                        ("Glass_Windshield" if fc.y < 0.4 else "Glass_Rear")
            else:
                g = glass_island_group(o.name, c)
                for f in isl:
                    assign[f] = g
    elif r == "Lights":
        pre = lights_side[o.name]
        for p in me.polygons:
            assign[p.index] = pre + side(p.center.x)
    elif r == "Interior":
        for isl in islands(me):
            pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
            lo, hi = bounds(pts)
            c = (lo + hi) / 2
            size = hi - lo
            g = "Interior"
            if abs(c.x) > 0.58 and size.x < 0.25 and c.z > 0.22:
                if size.y < 1.2:
                    g = door_by_y(c) or "Interior"
                else:
                    for f in isl:
                        fc = me.polygons[f].center
                        assign[f] = door_by_y(fc) or "Interior"
                    continue
            for f in isl:
                assign[f] = g
    else:
        for p in me.polygons:
            assign[p.index] = r
    by_g = {}
    for f, g in assign.items():
        by_g.setdefault(g, []).append(f)
    rr = "Wheel" if r.startswith("Wheel_") else r
    if len(by_g) == 1:
        parts.append((o, rr, next(iter(by_g))))
        continue
    for g, fids in by_g.items():
        no = extract(o, fids, f"{o.name}@{g}")
        parts.append((no, rr, g))
    bpy.data.objects.remove(o, do_unlink=True)

# Bay floors: when the hood / trunk lid falls off you see a dark bay, not a hole
liner_mat = bpy.data.materials.new("BayLiner")
liner_mat.use_nodes = True
lb = principled(liner_mat)
lb.inputs["Base Color"].default_value = (0.025, 0.025, 0.028, 1)
lb.inputs["Roughness"].default_value = 0.85
lb.inputs["Metallic"].default_value = 0.0


def add_liner(panel, group, z, name, inset=0.06):
    objs = [o for o, r, g in parts if g == panel and r == "Body"]
    pts = [v.co for o in objs for v in o.data.vertices]
    if not pts:
        return
    lo, hi = bounds(pts)
    cv, cp = [], []
    for o in objs:
        base = len(cv)
        cv += [v.co.copy() for v in o.data.vertices]
        cp += [[base + i for i in p.vertices] for p in o.data.polygons]
    cover = BVHTree.FromPolygons(cv, cp)

    def covered(x, y):   # the panel is above this point (2 cm in from its edge)
        return all(cover.ray_cast(Vector((x + dx, y + dy, z)), Vector((0, 0, 1)), 1.0)[0] is not None
                   for dx, dy in ((0.02, 0), (-0.02, 0), (0, 0.02), (0, -0.02)))
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    nx, ny = 14, 16
    co = [[(lo.x + inset + (hi.x - lo.x - 2 * inset) * i / nx, lo.y + inset + (hi.y - lo.y - 2 * inset) * j / ny)
           for j in range(ny + 1)] for i in range(nx + 1)]
    ok = [[covered(*co[i][j]) for j in range(ny + 1)] for i in range(nx + 1)]
    vs = [[bm.verts.new((co[i][j][0], co[i][j][1], z)) for j in range(ny + 1)] for i in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            if ok[i][j] and ok[i + 1][j] and ok[i + 1][j + 1] and ok[i][j + 1]:
                bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    for f in bm.faces:
        if f.normal.z < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(liner_mat)
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    parts.append((o, "Body", group))
    print(f"liner {name}: x {lo.x:.2f}..{hi.x:.2f} y {lo.y:.2f}..{hi.y:.2f} z {z:.2f}")


add_liner("Hood", "Body_Front", 0.62, "FrunkFloor")
add_liner("Trunk", "Body_Rear", 0.70, "TrunkFloor", inset=0.10)

grp_before = {}
for o, r, g in parts:
    grp_before[g] = grp_before.get(g, 0) + tris(o)
print("groups:", json.dumps(grp_before, indent=0))

# =============================================================== 5. simplify per role
def weight(o):
    mats = " ".join(m.name for m in o.data.materials if m)
    if "1_BODY" in mats:
        return 4.0
    if "EXT_tyre" in mats or "RimC" in mats:
        return 3.0
    if any(k in mats for k in ("Glass", "glass", "Chrome", "chrome", "TailRED", "WhiteNM", "Mirror")):
        return 2.0
    if "Paint_Silver_BRAKE" in mats or "1_NULL" in mats:
        return 0.5
    return 1.0


def target_tris(t, w, r, floor=100):
    return max(min(t, floor), t * min(1.0, r * w))


def ratio_for(objs, budget):
    counts = [(tris(o), weight(o)) for o in objs]
    if sum(t for t, _ in counts) <= budget:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(40):
        r = (lo + hi) / 2
        s = sum(target_tris(t, w, r) for t, w in counts)
        lo, hi = (r, hi) if s < budget else (lo, r)
    return lo


dg = bpy.context.evaluated_depsgraph_get()
removed_bridge = [0]
roles = {}
for o, r, g in parts:
    key = g if r == "Wheel" else r
    roles.setdefault(key, []).append(o)
for key, objs in roles.items():
    budget = ROLE_BUDGET["Wheel" if key.startswith("Wheel_") else key]
    before = sum(tris(o) for o in objs)
    r = ratio_for(objs, budget)
    for o in objs:
        t = tris(o)
        if t == 0:
            continue
        vs = [v.co for v in o.data.vertices]
        lo, hi = bounds(vs)
        rr = target_tris(t, weight(o), r) / t
        if rr < 0.98:
            src_bvh = BVHTree.FromPolygons([v.co.copy() for v in o.data.vertices],
                                           [list(p.vertices) for p in o.data.polygons])
            mod = o.modifiers.new("dec", 'DECIMATE')
            mod.decimate_type = 'COLLAPSE'
            mod.ratio = rr
            mod.use_collapse_triangulate = True
            dg.update()
            new = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
            old = o.data
            o.modifiers.remove(mod)
            o.data = new
            bpy.data.meshes.remove(old)
            m = 0.02
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bad = [v for v in bm.verts if any(not (lo[i] - m <= v.co[i] <= hi[i] + m) for i in range(3))]
            # vertices pulled off the surface, and triangles bridging gaps between separate pieces
            bad = set(bad)
            bad |= {v for v in bm.verts if src_bvh.find_nearest(v.co, 0.02)[0] is None}
            if bad:
                bmesh.ops.delete(bm, geom=list(bad), context='VERTS')
            far = []
            for f in bm.faces:
                c = f.calc_center_median()
                if src_bvh.find_nearest(c, 0.02)[0] is None:
                    far.append(f)
            if far:
                bmesh.ops.delete(bm, geom=far, context='FACES')
            removed_bridge[0] += len(far)
            bm.to_mesh(o.data)
            bm.free()
        o.data.shade_smooth()
        o.data.set_sharp_from_angle(angle=SMOOTH_ANGLE)
    log["roles"][key] = {"before": before, "after": sum(tris(o) for o in objs)}
    print(f"{key}: {before} -> {log['roles'][key]['after']}  (bridging faces removed so far: {removed_bridge[0]})")

# =============================================================== 6. remove faces nobody can see
def fib_sphere(n, radius, center):
    pts = []
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        rad = math.sqrt(1 - y * y)
        pts.append(center + Vector((math.cos(ga * i) * rad, math.sin(ga * i) * rad, y)) * radius)
    return pts


views = fib_sphere(160, 9.0, Vector((0, 0, 0.6)))
views += [Vector(v) for v in [(0.37, 0.15, 1.15), (-0.37, 0.15, 1.15), (0.0, 0.5, 1.1),
                              (0.37, -0.3, 1.05), (-0.37, -0.3, 1.05), (0.0, 1.0, 1.1),
                              (0.35, 0.9, 1.1), (-0.35, 0.9, 1.1)]]
V = np.array([tuple(v) for v in views])


def is_glassy(o):
    return any(m and (m.name in GLASS_MATS) for m in o.data.materials)


fixed = [(o, g) for o, r, g in parts if g not in DETACHABLE and not g.startswith(("Glass_", "Mirror_"))
         and not is_glassy(o)]
ov, op = [], []
for o, g in fixed:
    base = len(ov)
    ov += [v.co.copy() for v in o.data.vertices]
    op += [[base + i for i in p.vertices] for p in o.data.polygons]
occ = BVHTree.FromPolygons(ov, op) if op else None

culled_total = 0
if occ:
    for o, g in fixed:
        me = o.data
        hidden = []
        for p in me.polygons:
            n = p.normal
            c = p.center
            samples = [c] + [me.vertices[i].co * 0.7 + c * 0.3 for i in p.vertices[:3]]
            vis = False
            for s in samples:
                for sign in (1, -1):    # materials are double sided: either side may show
                    nn = n * sign
                    d = V - np.array(tuple(s))
                    dots = d @ np.array(tuple(nn))
                    order = np.argsort(-dots)
                    origin = s + nn * 0.002
                    for k in order:
                        if dots[k] <= 0:
                            break
                        dirv = views[k] - origin
                        dist = dirv.length
                        if occ.ray_cast(origin, dirv / dist, dist)[0] is None:
                            vis = True
                            break
                    if vis:
                        break
                if vis:
                    break
            if not vis:
                hidden.append(p.index)
        if hidden:
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[i] for i in hidden], context='FACES')
            bm.to_mesh(me)
            bm.free()
            culled_total += len(hidden)
log["hidden_faces_removed"] = culled_total
print("hidden faces removed:", culled_total)

# =============================================================== 7. join per group, split per material/size
def safe(s):
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_")


def tri_count(me, ids):
    return sum(len(me.polygons[i].vertices) - 2 for i in ids)


def spatial_chunks(me, fids, maxt):
    if tri_count(me, fids) <= maxt:
        return [fids]
    cs = [(i, me.polygons[i].center) for i in fids]
    ax = max(range(3), key=lambda a: max(c[a] for _, c in cs) - min(c[a] for _, c in cs))
    cs.sort(key=lambda ic: ic[1][ax])
    h = len(cs) // 2
    return spatial_chunks(me, [i for i, _ in cs[:h]], maxt) + spatial_chunks(me, [i for i, _ in cs[h:]], maxt)


def single_mat(o, fids, name, mat):
    nm = o.data.copy()
    keep = set(fids)
    bm = bmesh.new()
    bm.from_mesh(nm)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    for f in bm.faces:
        f.material_index = 0
    bm.to_mesh(nm)
    bm.free()
    nm.materials.clear()
    nm.materials.append(mat)
    nm.name = name
    no = bpy.data.objects.new(name, nm)
    scene.collection.objects.link(no)
    return no


by_group = {}
for o, r, g in parts:
    if len(o.data.polygons):
        by_group.setdefault(g, []).append(o)
    else:
        bpy.data.objects.remove(o, do_unlink=True)


def subdivide_long_edges(me, max_len, rounds=4):
    bm = bmesh.new()
    bm.from_mesh(me)
    for _ in range(rounds):
        long = [e for e in bm.edges if e.calc_length() > max_len]
        if not long:
            break
        bmesh.ops.subdivide_edges(bm, edges=long, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(me)
    bm.free()


def crack_uv_layer(me):
    """Planar map of the whole window into a 'CrackUV' layer, used by the cracked twins."""
    n = sum((p.normal * p.area for p in me.polygons), Vector())
    if n.length < 1e-6:
        n = Vector((0, 0, 1))
    n = n.normalized()
    # double layered glass: normals of both layers may cancel, fall back to the dominant axis
    up = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((0, 1, 0))
    u_ax = up.cross(n).normalized()
    v_ax = n.cross(u_ax).normalized()
    us = [v.co.dot(u_ax) for v in me.vertices]
    vs = [v.co.dot(v_ax) for v in me.vertices]
    u0, v0 = min(us), min(vs)
    su, sv = max(max(us) - u0, 1e-6), max(max(vs) - v0, 1e-6)
    uvl = me.uv_layers.new(name="CrackUV")
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        uvl.data[loop.index].uv = ((co.dot(u_ax) - u0) / su, (co.dot(v_ax) - v0) / sv)


def glass_normal(me):
    """Average outward normal of a window: flip faces that point toward the car centre first."""
    acc = Vector()
    for p in me.polygons:
        nn = p.normal.copy()
        if nn.dot(p.center - Vector((0, 0, 0.7))) < 0:
            nn = -nn
        acc += nn * p.area
    return acc


def freeze_normals(me):
    try:
        cn = [tuple(c.vector) for c in me.corner_normals]
        me.normals_split_custom_set(cn)
    except Exception as ex:
        print("  normals freeze skipped:", ex)


def chunk_faces(me, n_chunks, seed):
    F = len(me.polygons)
    if F == 0 or n_chunks <= 1:
        return np.zeros(F, dtype=int)
    cen = np.empty(F * 3, dtype=np.float64)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(F, 3)
    area = np.empty(F, dtype=np.float64)
    me.polygons.foreach_get("area", area)
    rng = np.random.default_rng(seed)
    k = min(n_chunks, F)
    p = area / area.sum() if area.sum() > 0 else None
    seeds = cen[rng.choice(F, size=k, replace=False, p=p)]
    for _ in range(3):
        d = ((cen[:, None, :] - seeds[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        for i in range(k):
            m = lab == i
            if m.any():
                w = area[m]
                seeds[i] = (cen[m] * w[:, None]).sum(axis=0) / max(w.sum(), 1e-12)
    d = ((cen[:, None, :] - seeds[None, :, :]) ** 2).sum(axis=2)
    lab = d.argmin(axis=1)
    uniq = {v: i for i, v in enumerate(sorted(set(lab.tolist())))}
    return np.array([uniq[v] for v in lab.tolist()], dtype=int)


def crack_uv_layer_n(me, n):
    n = n.normalized() if n.length > 1e-6 else Vector((0, 0, 1))
    up = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((0, 1, 0))
    u_ax = up.cross(n).normalized()
    v_ax = n.cross(u_ax).normalized()
    us = [v.co.dot(u_ax) for v in me.vertices]
    vs = [v.co.dot(v_ax) for v in me.vertices]
    u0, v0 = min(us), min(vs)
    su, sv = max(max(us) - u0, 1e-6), max(max(vs) - v0, 1e-6)
    uvl = me.uv_layers.new(name="CrackUV")
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        uvl.data[loop.index].uv = ((co.dot(u_ax) - u0) / su, (co.dot(v_ax) - v0) / sv)


final = []
for gi, (g, objs) in enumerate(sorted(by_group.items())):
    with bpy.context.temp_override(active_object=objs[0], object=objs[0],
                                   selected_objects=objs, selected_editable_objects=objs):
        bpy.ops.object.join()
    j = objs[0]
    me = j.data
    if g in CRACK_GROUPS:
        subdivide_long_edges(me, GLASS_MAX_EDGE)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=SMOOTH_ANGLE)
        crack_uv_layer_n(me, glass_normal(me))
    if g in CHUNKS:
        freeze_normals(me)
        labels = chunk_faces(me, CHUNKS[g], 1000 + gi)
    else:
        labels = np.zeros(len(me.polygons), dtype=int)
    buckets = {}
    for p in me.polygons:
        buckets.setdefault((int(labels[p.index]), p.material_index), []).append(p.index)
    for (ci, mi), fids in sorted(buckets.items()):
        mat = me.materials[mi] if mi < len(me.materials) else None
        mname = safe(mat.name) if mat else "NoMat"
        chunks = spatial_chunks(me, fids, MAX_TRIS)
        for k, ch in enumerate(chunks):
            mid = f"C{ci + 1:02d}__" if g in CHUNKS else ""
            nm = f"{g}__{mid}{mname}" + (f"_{k + 1}" if len(chunks) > 1 else "")
            no = single_mat(j, ch, nm, mat)
            no["group"] = g
            no["chunk"] = ci + 1 if g in CHUNKS else 0
            no["dmg"] = False
            final.append(no)
    bpy.data.objects.remove(j, do_unlink=True)

# =============================================================== 8. cracked glass twins
def make_crack_image(size=1024, seed=7):
    rng = np.random.default_rng(seed)
    a = np.zeros((size, size, 4), dtype=np.float32)
    a[:, :, :3] = 0.85
    a[:, :, 3] = 0.10

    def stamp(x, y, r, alpha):
        x0, x1 = int(max(0, x - r)), int(min(size, x + r + 1))
        y0, y1 = int(max(0, y - r)), int(min(size, y + r + 1))
        if x0 >= x1 or y0 >= y1:
            return
        a[y0:y1, x0:x1, 3] = np.maximum(a[y0:y1, x0:x1, 3], alpha)
        a[y0:y1, x0:x1, :3] = 0.97

    def line(p, q, r, alpha):
        n = int(max(abs(q[0] - p[0]), abs(q[1] - p[1]))) + 1
        for t in np.linspace(0, 1, n):
            stamp(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, r, alpha)

    def jagged(p, ang, length, r, alpha, depth=0):
        pts = [p]
        steps = int(length / 18) + 2
        for i in range(steps):
            ang += rng.normal(0, 0.06)
            last = pts[-1]
            pts.append((last[0] + np.cos(ang) * length / steps, last[1] + np.sin(ang) * length / steps))
        for u, v in zip(pts, pts[1:]):
            line(u, v, r, alpha)
            if depth < 1 and rng.random() < 0.03:
                jagged(v, ang + rng.choice([-1, 1]) * rng.uniform(0.4, 1.0),
                       length * rng.uniform(0.15, 0.35), max(0, r - 1), alpha * 0.8, depth + 1)
        return pts

    centers = [(size * 0.36, size * 0.45), (size * 0.72, size * 0.60)]
    for ci, c in enumerate(centers):
        n_rad = int(rng.integers(10, 15))
        reach = size * (0.60 if ci == 0 else 0.30)
        spokes = []
        for k in range(n_rad):
            ang = 2 * np.pi * k / n_rad + rng.normal(0, 0.12)
            spokes.append(jagged(c, ang, reach * rng.uniform(0.6, 1.0), 1, 0.9))
        for ring in (1, 2, 4, 7):
            for k in range(n_rad):
                s1, s2 = spokes[k], spokes[(k + 1) % n_rad]
                i1, i2 = min(ring, len(s1) - 1), min(ring, len(s2) - 1)
                if rng.random() < (0.95 if ring < 3 else 0.6):
                    line(s1[i1], s2[i2], 1 if ring < 3 else 0, 0.8)
        for _ in range(40):
            stamp(c[0] + rng.normal(0, 7), c[1] + rng.normal(0, 7), 2, 0.95)
    img = bpy.data.images.new("GlassCracks", size, size, alpha=True)
    img.pixels.foreach_set(a.ravel())
    img.pack()
    img.alpha_mode = 'STRAIGHT'
    return img


crack_img = None


def cracked_material():
    global crack_img
    m = bpy.data.materials.get("GLASS_CRACKED")
    if m:
        return m
    if crack_img is None:
        crack_img = make_crack_image(1024 if VARIANT == "high" else 512)
    m = bpy.data.materials.new("GLASS_CRACKED")
    m.use_nodes = True
    nt = m.node_tree
    b = principled(m)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = crack_img
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.15
    b.inputs["Metallic"].default_value = 0.0
    try:
        m.surface_render_method = 'BLENDED'
    except Exception:
        m.blend_method = 'BLEND'
    return m


for no in list(final):
    g = no["group"]
    if g not in CRACK_GROUPS:
        continue
    me = no.data.copy()
    me.materials.clear()
    for l in [l for l in me.uv_layers if l.name != "CrackUV"]:
        me.uv_layers.remove(l)
    me.uv_layers["CrackUV"].name = "UVMap"
    me.materials.append(cracked_material())
    segs = no.name.split("__")
    name = f"{g}__{segs[1]}__DMG__{'__'.join(segs[2:])}"
    me.name = name
    d = bpy.data.objects.new(name, me)
    scene.collection.objects.link(d)
    d["group"] = g
    d["chunk"] = no["chunk"]
    d["dmg"] = True
    final.append(d)

for no in final:
    if not no["dmg"] and "CrackUV" in no.data.uv_layers:
        no.data.uv_layers.remove(no.data.uv_layers["CrackUV"])

# =============================================================== 9. pivots + hierarchy
for no in final:
    g = no["group"]
    if g in wheel_centers:
        c = wheel_centers[g]
    else:
        lo, hi = bounds([v.co for v in no.data.vertices])
        c = (lo + hi) / 2
    no.data.transform(Matrix.Translation(-c))
    no.location = c

group_empty = {}
for g in sorted({no["group"] for no in final}):
    e = bpy.data.objects.new(g, None)
    scene.collection.objects.link(e)
    e.location = wheel_centers.get(g, Vector((0, 0, 0)))
    group_empty[g] = e
for no in final:
    e = group_empty[no["group"]]
    wl = no.location.copy()
    no.parent = e
    no.matrix_parent_inverse = Matrix.Identity(4)
    no.location = wl - e.location

# =============================================================== 10. textures + export
used = set()
for no in final:
    for m in no.data.materials:
        if m and m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image:
                    used.add(n.image)
for img in used:
    w, h = img.size
    if max(w, h) > TEX_MAX:
        s = TEX_MAX / max(w, h)
        img.scale(max(1, int(w * s)), max(1, int(h * s)))
        img.pack()

for no in sorted(final, key=lambda o: o.name):
    log["parts"].append({"name": no.name, "group": no["group"], "dmg": bool(no["dmg"]), "tris": tris(no),
                         "materials": len(no.data.materials)})
for p in log["parts"]:
    G = log["groups"].setdefault(p["group"], {"tris": 0, "dmg_tris": 0, "parts": 0,
                                              "detachable": p["group"] in DETACHABLE})
    G["dmg_tris" if p["dmg"] else "tris"] += p["tris"]
    G["parts"] += 1
for no in final:
    G = log["groups"][no["group"]]
    G.setdefault("chunk_ids", set()).add(no.get("chunk", 0))
for G in log["groups"].values():
    G["chunks"] = len(G.pop("chunk_ids", {0}) - {0})
log["visible_tris"] = sum(p["tris"] for p in log["parts"] if not p["dmg"])
log["dmg_tris"] = sum(p["tris"] for p in log["parts"] if p["dmg"])
log["part_count"] = len(final)
log["max_part_tris"] = max(p["tris"] for p in log["parts"])
log["names_ok"] = all(all(ch.isalnum() or ch == "_" for ch in p["name"]) for p in log["parts"])
log["single_material"] = all(p["materials"] == 1 for p in log["parts"])
json.dump(log, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1)
print("visible tris:", log["visible_tris"], "dmg tris:", log["dmg_tris"], "parts:", log["part_count"],
      "max part:", log["max_part_tris"], "names ok:", log["names_ok"], "single mat:", log["single_material"])
for g, G in sorted(log["groups"].items()):
    print(f"  {g}: parts {G['parts']} chunks {G['chunks']} tris {G['tris']}")

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, NAME + ".blend"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), export_format='GLB',
                          export_yup=True, export_apply=True)
