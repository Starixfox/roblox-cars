"""2025 BMW M4 GT3 EVO G82 (Sketchfab, Ddiaz Design, CC BY-NC-SA) -> Roblox, with damage parts.
Adapted from porsche-gt3rs/scripts/prep2.py.

Usage (via run.ps1 / wrap.py):  prep.py high   or   prep.py lite

Output part names:  <Group>__<Material>[_k]                 unchunked part
                    <Group>__C<nn>__<Material>[_k]          chunk part
                    <Group>__C<nn>__DMG__<Material>[_k]     cracked glass twin, hidden in game
"""
import bpy, bmesh, os, sys, json, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

VARIANT = (sys.argv[1] if len(sys.argv) > 1 else "high").lower()
ROOT = r"C:\Users\jordan\RobloxCars\bmw-m4-gt3"
FBX = os.path.join(ROOT, "source", "inner", "FINAL_MODEL_GT325.fbx")
OUT = os.path.join(ROOT, "roblox")
NAME = "BMW_M4GT3_" + VARIANT.capitalize()
MAX_TRIS = 19000
TEX_MAX = 1024 if VARIANT == "high" else 512
SMOOTH_ANGLE = math.radians(35)

ROLE_BUDGET = {
    "high": {"Body": 56000, "Interior": 10000, "SteeringWheel": 2000, "Glass": 4000,
             "Lights": 7000, "Brakes": 2000, "Wheel": 4600},
    "lite": {"Body": 22000, "Interior": 3500, "SteeringWheel": 600, "Glass": 1800,
             "Lights": 2500, "Brakes": 800, "Wheel": 2100},
}[VARIANT]

DETACHABLE = {"Hood", "Trunk", "Door_L", "Door_R", "FrontBumper", "RearBumper", "Wing",
              "Mirror_L", "Mirror_R", "Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR"}
CRACK_GROUPS = {"Glass_Windshield", "Glass_Rear", "Glass_Door_L", "Glass_Door_R",
                "Glass_Quarter_L", "Glass_Quarter_R"}
CHUNKS = {
    "high": {"Hood": 10, "Trunk": 6, "Door_L": 9, "Door_R": 9, "FrontBumper": 12, "RearBumper": 10,
             "Wing": 4, "Body_Front": 10, "Body_Mid": 10, "Body_Rear": 12,
             "Glass_Windshield": 30, "Glass_Rear": 16, "Glass_Door_L": 12, "Glass_Door_R": 12,
             "Glass_Quarter_L": 5, "Glass_Quarter_R": 5},
    "lite": {"Hood": 6, "Trunk": 4, "Door_L": 6, "Door_R": 6, "FrontBumper": 7, "RearBumper": 6,
             "Wing": 3, "Body_Front": 6, "Body_Mid": 6, "Body_Rear": 7,
             "Glass_Windshield": 16, "Glass_Rear": 10, "Glass_Door_L": 7, "Glass_Door_R": 7,
             "Glass_Quarter_L": 3, "Glass_Quarter_R": 3},
}[VARIANT]
GLASS_MAX_EDGE = 0.10 if VARIANT == "high" else 0.16

# Material renames: strip namespaces and brand words from names
MAT_RENAME = {
    "MAT_GT3_EVO_car_paint1": "CarPaint", "BMW_M4_GT3_EVO_Carbon1": "Carbon",
    "BMW_M4GT3_2022_Wheel1A_3D_3DWheel1A_Material1": "Tyre", "MAT_Glass_002": "Glass_Tint",
    "MAT_Glass1": "Glass_Frit", "MAT_Lights1": "Lights", "MAT_Tire_Hub1": "Rim",
    "MAT_Tire_Disk1": "BrakeDisc", "MAT_Tire_Brake1": "Caliper", "MAT_Details_EXT1": "Details_EXT",
    "MAT_Details_INT1": "Details_INT", "MAT_Details_MAT1": "Details_Trim", "MAT_Details_Chassis1": "Chassis",
    "MAT_Details_Engine1": "Details_Engine", "MAT_Details_Grid_01_002": "Grille",
    "MAT_Details_Add_02": "Seat", "MAT_Details_Add_04": "Dash", "MAT_Details_Add_06": "DoorCard",
    "MAT_Alpha_01_002": "Decals", "MAT_Glass_004": "SunStrip",
}

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX)
scene = bpy.context.scene
# the FBX comes in at 1/100 scale: scale everything x100 around the origin
root = bpy.data.objects.new("SCALE", None)
scene.collection.objects.link(root)
for o in list(scene.objects):
    if o.parent is None and o is not root:
        o.parent = root
root.scale = (100, 100, 100)
bpy.context.view_layer.update()

log = {"variant": VARIANT, "removed": [], "roles": {}, "groups": {}, "parts": []}

for m in bpy.data.materials:
    short = m.name.split(":")[-1]
    m.name = MAT_RENAME.get(short, short)


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


def mats_of(o):
    return {m.name for m in o.data.materials if m}


def principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat and mat.node_tree else None


# =============================================================== 0. record world matrices + roles BEFORE baking
world = {o.name: o.matrix_world.copy() for o in meshes()}
parent_chain = {}
for o in meshes():
    names, p = [], o.parent
    while p:
        names.append(p.name)
        p = p.parent
    parent_chain[o.name] = names

# =============================================================== 1. logos + textures
DELETE_MATS = {"Decals", "SunStrip"}       # decal sheet (M4 / GT3 / BMW / M / Motorsport) and windshield banner
for o in list(meshes()):
    if mats_of(o) & DELETE_MATS:
        log["removed"].append(f"{o.name} ({tris(o)} tris, decal mesh)")
        bpy.data.objects.remove(o, do_unlink=True)

# BMW roundel on the Details_EXT atlas (top-left 180x180 of 512): delete every face mapped there
ROUNDEL_UV = (0.0, 1.0 - 182 / 512, 182 / 512, 1.0)    # u0, v0, u1, v1 (Blender UV, bottom-left origin)
# Steering wheel maker lettering is modelled geometry, coloured by the small white square of
# the interior atlas (px 58..78, 258..280 of 512): delete those faces on the steering wheel only
LETTER_UV = (58 / 512, 1.0 - 280 / 512, 78 / 512, 1.0 - 258 / 512)
UV_KILL = [("Details_EXT", ROUNDEL_UV, ""), ("Details_INT", LETTER_UV, "ANC_SteeringWheel")]
for o in meshes():
  for mat_name, ROUNDEL_UV, name_part in UV_KILL:
    me = o.data
    if name_part not in o.name:
        continue
    idx = [i for i, m in enumerate(me.materials) if m and m.name == mat_name]
    if not idx or not me.uv_layers:
        continue
    uvl = me.uv_layers.active.data
    kill = []
    for p in me.polygons:
        if p.material_index not in idx:
            continue
        uv = sum((uvl[li].uv for li in p.loop_indices), Vector((0, 0))) / p.loop_total
        u, v = uv.x % 1.0, uv.y % 1.0
        if ROUNDEL_UV[0] <= u <= ROUNDEL_UV[2] and ROUNDEL_UV[1] <= v <= ROUNDEL_UV[3]:
            kill.append(p.index)
    if kill:
        o.data = me.copy()
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in kill], context='FACES')
        bm.to_mesh(o.data)
        bm.free()
        log["removed"].append(f"{o.name}: {len(kill)} {mat_name} logo/lettering faces")


def img_px(img):
    w, h = img.size
    a = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, img.channels)


def img_set(img, a):
    img.pixels.foreach_set(a.ravel())
    img.update()
    img.pack()


def img_by_file(fname):
    for img in bpy.data.images:
        if os.path.basename(img.filepath).lower() == fname.lower() and "." not in img.name[-4:]:
            return img
    return None


def fill_rects(fname, rects_top_left, color=None, ref=None):
    """rects in pixel coords (origin top-left, as seen in a viewer) of a ref-size image.
    color None = median colour of a 3 px ring around the rect (surrounding colour)."""
    img = img_by_file(fname)
    if not img:
        print("missing image", fname)
        return
    a = img_px(img)
    h, w = a.shape[:2]
    rw, rh = ref or (w, h)
    sx, sy = w / rw, h / rh
    for x0, y0, x1, y1 in rects_top_left:
        X0, X1 = max(0, int(x0 * sx)), min(w, int(x1 * sx))
        Y0, Y1 = max(0, h - int(y1 * sy)), min(h, h - int(y0 * sy))   # flip: Blender rows start at the bottom
        c = color
        if c is None:
            ring = np.concatenate([a[max(0, Y0 - 3):Y0, X0:X1].reshape(-1, a.shape[2]),
                                   a[Y1:Y1 + 3, X0:X1].reshape(-1, a.shape[2]),
                                   a[Y0:Y1, max(0, X0 - 3):X0].reshape(-1, a.shape[2]),
                                   a[Y0:Y1, X1:X1 + 3].reshape(-1, a.shape[2])])
            c = np.median(ring, axis=0)[:3]
        a[Y0:Y1, X0:X1, :len(c)] = c
    img_set(img, a)
    log["removed"].append(f"texture {fname}: {len(rects_top_left)} areas blanked")


FLAT = (0.5, 0.5, 1.0)
# Details_EXT: roundel (faces already deleted, paint it too) + KRONTEC extinguisher lettering
fill_rects("TEX_Details_EXT_D.png", [(0, 0, 182, 182)], (0.25, 0.25, 0.25))
fill_rects("TEX_Details_EXT_D.png", [(222, 312, 334, 416)], None)
fill_rects("TEX_Details_EXT_N.png", [(0, 0, 182, 182), (222, 312, 334, 416)], FLAT)
# Interior atlas: alcon, COSWORTH, RACELOGIC, display maker mark
INT_RECTS = [(172, 52, 270, 102), (88, 387, 157, 407), (424, 394, 448, 488)]
fill_rects("TEX_Details_INT_D.png", INT_RECTS, None)
fill_rects("TEX_Details_INT_D.png", [(20, 98, 152, 110)], (0.0, 0.0, 0.0))
fill_rects("TEX_Details_INT_N.png", INT_RECTS + [(20, 98, 152, 110)], FLAT)
# Brake caliper: AP RACING lettering
fill_rects("TEX_Tire_Brake_D.png", [(22, 165, 230, 225)], None)
fill_rects("TEX_Tire_Brake_N.png", [(22, 165, 230, 225)], FLAT)
# Seat atlas: M4 GT3 logo outline
fill_rects("TEX_Details_Add_01_D.png", [(40, 0, 160, 28)], None)
fill_rects("TEX_Details_Add_01_N.png", [(40, 0, 160, 28)], FLAT)


def blank_tyre():
    """Tyre sidewall ring (PS 15, FL/FR/RR, small print): plain rubber. Normal map: flat except the wheel nut."""
    img = img_by_file("Wheel1A_DiffuseAOSO.png")
    if img:
        a = img_px(img)
        h, w = a.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.sqrt((xx - w / 2) ** 2 + (yy - h / 2) ** 2) * (800 / w)
        ring = (r >= 203) & (r <= 322)
        a[ring] = np.median(a[ring], axis=0)
        img_set(img, a)
        log["removed"].append("texture Wheel1A_DiffuseAOSO: sidewall lettering blanked")
    img = img_by_file("BMW_M4GT3_2022_Wheel1A_Normal.png")
    if img:
        a = img_px(img)
        h, w = a.shape[:2]
        keep = a.copy()
        a[:, :, :3] = FLAT
        # wheel nut normal detail: top-left (0,340)-(90,425) in a 512 image
        X0, X1, Y0, Y1 = 0, int(90 * w / 512), h - int(425 * h / 512), h - int(340 * h / 512)
        a[Y0:Y1, X0:X1] = keep[Y0:Y1, X0:X1]
        img_set(img, a)
        log["removed"].append("texture Wheel1A_Normal: RIMSTOCK / M stripes / FRONT / REAR flattened")


blank_tyre()

# Sane PBR values (the FBX importer sets metallic 0.5 / roughness 0 on everything)
PBR = {"CarPaint": (0.35, 0.32), "Carbon": (0.0, 0.38), "Tyre": (0.0, 0.85), "Glass_Tint": (0.0, 0.05),
       "Glass_Frit": (0.0, 0.4), "Lights": (0.1, 0.2), "Rim": (0.6, 0.35), "BrakeDisc": (0.7, 0.45),
       "Caliper": (0.2, 0.4)}
for m in bpy.data.materials:
    b = principled(m)
    if not b:
        continue
    met, rough = PBR.get(m.name, (0.0, 0.55))
    if m.name not in ("Glass_Frit", "Glass_Tint"):
        # every texture here is fully opaque: drop the alpha links so parts export as OPAQUE
        for l in list(b.inputs["Alpha"].links):
            m.node_tree.links.remove(l)
        b.inputs["Alpha"].default_value = 1.0
        try:
            m.surface_render_method = 'DITHERED'
            m.blend_method = 'OPAQUE'
        except Exception:
            pass
    else:
        try:
            m.surface_render_method = 'BLENDED'
        except Exception:
            pass
    b.inputs["Metallic"].default_value = met
    b.inputs["Roughness"].default_value = rough
    if m.name == "Carbon":
        nm = next((n for n in m.node_tree.nodes if n.type == 'NORMAL_MAP'), None)
        if nm:
            nm.inputs["Strength"].default_value = 0.25

# Door glass is two frit layers (transparent middle): make one layer the tinted glass
for nm in ("BMW:ANC_Door_L_15", "BMW:SM_Base_0000_001_SM_Base_0000_MAT_GT3_EVO_car_paint2"):
    o = bpy.data.objects.get(nm)
    if o:
        o.data = o.data.copy()
        o.data.materials.clear()
        o.data.materials.append(bpy.data.materials["Glass_Tint"])

# =============================================================== 2. roles
wheel_parent_names = {"3DWheel Front L", "3DWheel Front R", "3DWheel Rear L", "3DWheel Rear R"}


def wcenter(o):
    vs = o.data.vertices
    if not len(vs):
        return world[o.name].translation.copy()
    return world[o.name] @ (sum((v.co for v in vs), Vector()) / len(vs))


def role_of(o):
    n = o.name.split(":")[-1]
    ms = mats_of(o)
    chain = parent_chain[o.name]
    if o.name in wheel_parent_names:
        return "DELETE"
    if any(p in wheel_parent_names for p in chain):
        if n.startswith("SM_Brake"):
            return "Brakes"
        c = wcenter(o)
        return "Wheel_" + side(c.x) + ("F" if c.y < 0 else "R")
    if n.startswith("ANC_SteeringWheel"):
        return "SteeringWheel"
    if "Lights" in ms:
        return "Lights"
    if ms & {"Glass_Tint", "Glass_Frit"}:
        return "Glass"
    if n.startswith("SM_Interior") or n.startswith("D_Body"):
        return "Body" if "CarPaint" in ms else "Interior"
    return "Body"


role = {o.name: role_of(o) for o in meshes()}
for o in list(meshes()):
    if role[o.name] == "DELETE" or not len(o.data.polygons):
        bpy.data.objects.remove(o, do_unlink=True)

# wheel spin centre = centre of the tyre bounds
wheel_centers = {}
for o in meshes():
    r = role[o.name]
    if r.startswith("Wheel_") and "Tyre" in mats_of(o):
        pts = [world[o.name] @ v.co for v in o.data.vertices]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        wheel_centers[r] = (lo + hi) / 2
print("wheel centres:", {k: tuple(round(x, 3) for x in v) for k, v in wheel_centers.items()})

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
    # loose edges / verts (no faces) would spoil bounds and pivots
    loose_e = [e for e in bm.edges if not e.link_faces]
    if loose_e:
        bmesh.ops.delete(bm, geom=loose_e, context='EDGES')
    loose_v = [v for v in bm.verts if not v.link_faces]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
    bm.to_mesh(o.data)
    bm.free()
for o in [o for o in scene.objects if o.type != 'MESH']:
    bpy.data.objects.remove(o, do_unlink=True)
bpy.context.view_layer.update()

# =============================================================== 4. damage groups
def zone(y):
    return "Body_Front" if y < -0.80 else ("Body_Rear" if y > 0.60 else "Body_Mid")


def in_mirror_box(c):
    return abs(c.x) > 0.76 and -0.68 < c.y < -0.28 and c.z > 0.86


def short(o):
    return o.name.split(":")[-1].split("@")[0]


def paint_kind(o):
    """Which paint panel object this is (only real exterior panels go in the paint BVH)."""
    n = short(o)
    if "CarPaint" not in mats_of(o):
        return None
    if n.startswith("SM_Hood"):
        return "HOOD"
    if n.startswith("SM_FrontKit"):
        return "FRONT"
    if n.startswith("SM_RearKit"):
        return "REAR"
    if n.startswith("ANC_Door_") or n.startswith("SM_Base"):
        return "DOOR"
    return None


def rear_paint(c):
    if c.y > 1.88 and c.z > 1.13:
        return "Wing"
    if abs(c.x) < 0.62 and 1.48 < c.y < 2.42 and c.z > 0.86:
        return "Trunk"
    if abs(c.x) < 0.50 and c.y > 2.12 and c.z > 0.655:
        return "Trunk"                     # lid rear face between the tail lights
    if c.y > 1.74 and c.z < 0.64:
        return "RearBumper"
    return zone(c.y)


def front_paint(c):
    if c.y < -1.90 and c.z < 0.64:
        return "FrontBumper"
    return zone(c.y)


def paint_group(kind, c):
    if kind == "HOOD":
        return "Hood"
    if kind == "FRONT":
        return front_paint(c)
    if kind == "REAR":
        return rear_paint(c)
    if kind == "DOOR":
        return ("Mirror_" if in_mirror_box(c) else "Door_") + side(c.x)
    return zone(c.y)


pv, pp, pgroup = [], [], []
for o in meshes():
    k = paint_kind(o)
    if k:
        base = len(pv)
        pv += [v.co.copy() for v in o.data.vertices]
        for p in o.data.polygons:
            pp.append([base + i for i in p.vertices])
            pgroup.append(paint_group(k, p.center))
paint_bvh = BVHTree.FromPolygons(pv, pp)


def nearest_panel(co, maxd=0.03):
    hit = paint_bvh.find_nearest(co, maxd)
    return pgroup[hit[2]] if hit and hit[0] is not None else None


def islands(me):
    edge_faces = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            edge_faces.setdefault(ek, []).append(p.index)
    seen, out = set(), []
    for p in me.polygons:
        if p.index in seen:
            continue
        stack, isl = [p.index], []
        seen.add(p.index)
        while stack:
            f = stack.pop()
            isl.append(f)
            for ek in me.polygons[f].edge_keys:
                for h in edge_faces[ek]:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
        out.append(isl)
    return out


def bounds(pts):
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def region_group(c):
    """Areas where carbon/black trim belongs to a panel even when not touching its paint."""
    if c.y > 1.85 and 0.38 < abs(c.x) < 0.80 and c.z > 0.98:
        return "Wing"                      # swan-neck wing posts
    if c.y > 1.88 and c.z > 1.13:
        return "Wing"                      # wing plane + end plates
    if -2.30 < c.y < -0.95 and abs(c.x) < 0.70 and c.z > 0.64:
        return "Hood"                      # hood vents / louvres
    if 1.48 < c.y < 2.42 and abs(c.x) < 0.60 and 0.86 < c.z < 1.13:
        return "Trunk"
    if (c.y < -1.95 and c.z < 0.50) or (c.y < -2.02 and c.z < 0.66):
        return "FrontBumper"               # splitter / lower intakes / parts behind the grille
    if (c.y > 2.0 and c.z < 0.64) or (c.y > 1.72 and c.z < 0.45):
        return "RearBumper"                # diffuser and its fins
    return None


def body_island_group(me, isl):
    pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
    lo, hi = bounds(pts)
    c = (lo + hi) / 2
    size = hi - lo
    step = max(1, len(isl) // 60)
    if max(size) <= 1.0:
        reg = [region_group(me.polygons[f].center) for f in isl[::step]]
        for g in ("Wing", "Hood", "Trunk", "FrontBumper", "RearBumper"):
            if reg.count(g) >= 0.6 * len(reg):
                return g
    if max(size) > 1.0:
        return None                        # spans several panels: decide per face
    votes = {}
    for f in isl[::step]:
        g = nearest_panel(me.polygons[f].center)
        if g:
            votes[g] = votes.get(g, 0) + 1
    total = len(isl[::step])
    if votes:
        g, n = max(votes.items(), key=lambda kv: kv[1])
        if n >= 0.3 * total and not g.startswith("Body_"):
            return g
    return zone(c.y)


def glass_island_group(me, isl):
    pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
    lo, hi = bounds(pts)
    c = (lo + hi) / 2
    if c.y > 1.75 and c.z < 0.9:
        return "TailLight_" + side(c.x)
    if c.y < -1.7:
        return "HeadLight_" + side(c.x)
    if c.y < -0.15 and abs(c.x) < 0.62:
        return "Glass_Windshield"
    if c.y > 0.70 and abs(c.x) < 0.50:
        return "Glass_Rear"
    if -0.6 < c.y < 0.58:
        return "Glass_Door_" + side(c.x)
    return "Glass_Quarter_" + side(c.x)


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
    n = short(o)
    assign = {}
    door_obj = n.startswith("ANC_Door_") or n.startswith("SM_Base")
    if r == "Body":
        k = paint_kind(o)
        if k:
            for p in me.polygons:
                assign[p.index] = paint_group(k, p.center)
        elif door_obj:
            for p in me.polygons:
                c = p.center
                assign[p.index] = ("Mirror_" if in_mirror_box(c) else "Door_") + side(c.x)
        elif n.startswith("SM_Hood"):
            for p in me.polygons:
                assign[p.index] = "Hood"
        elif "CarPaint" in mats_of(o):
            # inner body shell (cockpit tub, sills, cage tubes in body colour): fixed, by zone
            for p in me.polygons:
                assign[p.index] = zone(p.center.y)
        else:
            for isl in islands(me):
                res = body_island_group(me, isl)
                if res is None:
                    for f in isl:
                        c = me.polygons[f].center
                        g = region_group(c) or nearest_panel(c)
                        assign[f] = g if g and not g.startswith("Body_") else zone(c.y)
                else:
                    for f in isl:
                        assign[f] = res
    elif r == "Glass":
        if door_obj:
            for p in me.polygons:
                assign[p.index] = "Glass_Door_" + side(p.center.x)
        elif n.startswith("SM_FrontKit"):
            for p in me.polygons:
                assign[p.index] = "HeadLight_" + side(p.center.x)
        else:
            for isl in islands(me):
                g = glass_island_group(me, isl)
                for f in isl:
                    assign[f] = g
    elif r == "Lights":
        for p in me.polygons:
            c = p.center
            assign[p.index] = ("HeadLight_" if c.y < 0 else "TailLight_") + side(c.x)
    elif r == "Interior":
        for isl in islands(me):
            pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
            lo, hi = bounds(pts)
            c = (lo + hi) / 2
            g = "Interior"
            if abs(c.x) > 0.62 and -0.86 < c.y < 0.56 and max(hi - lo) < 1.3 and n.startswith("SM_Interior"):
                g = "Door_" + side(c.x)      # door card goes with the door
            for f in isl:
                assign[f] = g
    else:
        for p in me.polygons:
            assign[p.index] = r
    by_g = {}
    for f, g in assign.items():
        by_g.setdefault(g, []).append(f)
    rr = "Wheel" if r.startswith("Wheel_") else r
    if r == "Body" and "Lights" in mats_of(o):
        rr = "Lights"
    if len(by_g) == 1:
        parts.append((o, rr, next(iter(by_g))))
        continue
    for g, fids in by_g.items():
        no = extract(o, fids, f"{o.name}@{g}")
        parts.append((no, rr, g))
    bpy.data.objects.remove(o, do_unlink=True)

# The fixed windows only have the frit layer (black border, fully transparent middle):
# add a tinted glass layer on the same faces, so there is visible glass that can crack.
for o, r, g in list(parts):
    if g in ("Glass_Windshield", "Glass_Rear", "Glass_Quarter_L", "Glass_Quarter_R") and \
            {o.data.materials[p.material_index].name for p in o.data.polygons} == {"Glass_Frit"}:
        me = o.data.copy()
        me.materials.clear()
        me.materials.append(bpy.data.materials["Glass_Tint"])
        for p in me.polygons:
            p.material_index = 0
        t = bpy.data.objects.new(o.name + "_tint", me)
        scene.collection.objects.link(t)
        parts.append((t, "Glass", g))

# Bay floors: a dark floor under hood and trunk lid, so a missing panel shows a bay, not a hole
liner_mat = bpy.data.materials.new("BayLiner")
liner_mat.use_nodes = True
lb = principled(liner_mat)
lb.inputs["Base Color"].default_value = (0.025, 0.025, 0.028, 1)
lb.inputs["Roughness"].default_value = 0.85
lb.inputs["Metallic"].default_value = 0.0


def add_liner(panel, group, z, inset, name):
    pts = [o.data.vertices[i].co for o, r, g in parts if g == panel and "CarPaint" in mats_of(o)
           for p in o.data.polygons for i in p.vertices]
    if not pts:
        return
    lo, hi = bounds(pts)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    nx, ny = 6, 8
    vs = [[bm.verts.new((lo.x + inset + (hi.x - lo.x - 2 * inset) * i / nx,
                         lo.y + inset + (hi.y - lo.y - 2 * inset) * j / ny, z))
           for j in range(ny + 1)] for i in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    for f in bm.faces:
        if f.normal.z < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(liner_mat)
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    parts.append((o, "Body", group))
    log[name] = {"z": z, "lo": list(lo), "hi": list(hi)}


add_liner("Hood", "Body_Front", 0.56, 0.10, "FrontBayFloor")
add_liner("Trunk", "Body_Rear", 0.84, 0.12, "TrunkFloor")

grp_before = {}
for o, r, g in parts:
    grp_before[g] = grp_before.get(g, 0) + tris(o)
print("groups:", json.dumps(grp_before, indent=0))
log["groups_before"] = grp_before

# =============================================================== 5. simplify per role
def weight(o):
    ms = mats_of(o)
    if "CarPaint" in ms:
        return 6.0
    if ms & {"Glass_Tint", "Glass_Frit", "Rim", "Tyre", "Lights"}:
        return 2.0
    return 1.0


def target_tris(t, w, r, floor=120):
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
        lo, hi = bounds([v.co for v in o.data.vertices])
        rr = target_tris(t, weight(o), r) / t
        if rr < 0.98:
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
            if bad:
                bmesh.ops.delete(bm, geom=bad, context='VERTS')
                bm.to_mesh(o.data)
            bm.free()
        o.data.shade_smooth()
        o.data.set_sharp_from_angle(angle=SMOOTH_ANGLE)
    log["roles"][key] = {"before": before, "after": sum(tris(o) for o in objs)}
    print(f"{key}: {before} -> {log['roles'][key]['after']}")

# =============================================================== 6. remove faces nobody can see
# Occluders: only fixed, non-glass parts. Faces of detachable groups are never removed.
def fib_sphere(n, radius, center):
    pts = []
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        rad = math.sqrt(1 - y * y)
        pts.append(center + Vector((math.cos(ga * i) * rad, math.sin(ga * i) * rad, y)) * radius)
    return pts


views = fib_sphere(160, 9.0, Vector((0, 0, 0.6)))
# cockpit viewpoints (a grid through the cabin) so dash, displays and seats survive
views += [Vector((x, y, z)) for x in (-0.45, -0.15, 0.15, 0.45) for y in (-0.55, -0.2, 0.15, 0.5, 0.9)
          for z in (0.75, 1.0)]
V = np.array([tuple(v) for v in views])
GLASSY = {"Glass_Tint", "Glass_Frit", "Lights", "Grille"}

fixed = [(o, g) for o, r, g in parts if g not in DETACHABLE and not g.startswith("Glass_")
         and g != "SteeringWheel" and not (mats_of(o) & GLASSY)]
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
            seen = False
            for s in samples:
                for sign in (1, -1):          # thin shells can be seen from both sides
                    nn = n * sign
                    d = V - np.array(tuple(s))
                    dots = d @ np.array(tuple(nn))
                    order = np.argsort(-dots)
                    origin = s + nn * 0.002
                    for kk in order[:60]:
                        if dots[kk] <= 0:
                            break
                        dirv = views[kk] - origin
                        dist = dirv.length
                        if occ.ray_cast(origin, dirv / dist, dist)[0] is None:
                            seen = True
                            break
                    if seen or not me.materials or (me.materials[0] and me.materials[0].use_backface_culling):
                        break
                if seen:
                    break
            if not seen:
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

# =============================================================== 7. join per group, chunks, split per material/size
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


def freeze_normals(me):
    try:
        cn = [tuple(c.vector) for c in me.corner_normals]
        me.normals_split_custom_set(cn)
    except Exception as ex:
        print("  normals freeze skipped:", ex)


def chunk_faces(me, n_chunks, seed):
    """Voronoi chunks on the surface: area-weighted seeds, Lloyd relaxation, nearest seed per face."""
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
        crack_uv_layer(me)
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
    """Spiderweb cracks: white jagged lines on a faint transparent tint (RGBA, alpha = crack)."""
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
    if g not in CRACK_GROUPS or no.data.materials[0].name != "Glass_Tint":
        continue                         # only the tinted glass layer gets a cracked twin (frit stays)
    me = no.data.copy()
    me.materials.clear()
    if "CrackUV" in me.uv_layers:
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
bpy.context.view_layer.update()

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

for no in sorted(final, key=lambda o: o.name):
    log["parts"].append({"name": no.name, "group": no["group"], "dmg": bool(no["dmg"]), "tris": tris(no),
                         "chunk": int(no.get("chunk", 0))})
for p in log["parts"]:
    G = log["groups"].setdefault(p["group"], {"tris": 0, "dmg_tris": 0, "parts": 0, "chunk_ids": set(),
                                              "detachable": p["group"] in DETACHABLE})
    G["dmg_tris" if p["dmg"] else "tris"] += p["tris"]
    G["parts"] += 1
    if p["chunk"]:
        G["chunk_ids"].add(p["chunk"])
for G in log["groups"].values():
    G["chunks"] = len(G.pop("chunk_ids"))
log["visible_tris"] = sum(p["tris"] for p in log["parts"] if not p["dmg"])
log["dmg_tris"] = sum(p["tris"] for p in log["parts"] if p["dmg"])
log["part_count"] = len(final)
log["max_part_tris"] = max(p["tris"] for p in log["parts"])
log["multi_material_parts"] = [no.name for no in final if len(no.data.materials) != 1]
json.dump(log, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1)
print("visible tris:", log["visible_tris"], "dmg tris:", log["dmg_tris"], "parts:", log["part_count"],
      "max part:", log["max_part_tris"])

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, NAME + ".blend"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), export_format='GLB',
                          export_yup=True, export_apply=True)
