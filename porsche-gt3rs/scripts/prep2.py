"""Porsche 911 GT3 RS Weissach (Sketchfab, VTDAT23, CC BY 4.0) -> Roblox, with damage parts.

Usage (via run.ps1 / wrap.py):  prep2.py high   or   prep2.py lite

Output part names:  <Group>__<Material>[_n]          normal part
                    <Group>__DMG__<Material>[_n]      cracked glass version, hidden in game
Groups that can fall off: Hood, Trunk, Door_L, Door_R, FrontBumper, RearBumper, Wing,
                          Mirror_L, Mirror_R, Wheel_LF, Wheel_RF, Wheel_LR, Wheel_RR
Fixed groups: Body_Front, Body_Mid, Body_Rear, Interior, SteeringWheel, Brakes,
              HeadLight_L/R, TailLight_L/R, Glass_Windshield, Glass_Rear,
              Glass_Door_L/R (ride on the doors), Glass_Quarter_L/R
"""
import bpy, bmesh, os, sys, json, math
import numpy as np
from mathutils import Vector, Matrix, noise
from mathutils.bvhtree import BVHTree

VARIANT = (sys.argv[1] if len(sys.argv) > 1 else "high").lower()
ROOT = r"C:\Users\jordan\RobloxCars\porsche-gt3rs"
GLB = os.path.join(ROOT, "source", "source", "Porsche_GT3RS_MOD.glb")
OUT = os.path.join(ROOT, "roblox")
NAME = "GT3RS_" + VARIANT.capitalize()
MAX_TRIS = 19000
TEX_MAX = 1024 if VARIANT == "high" else 512
SMOOTH_ANGLE = math.radians(35)

ROLE_BUDGET = {
    "high": {"Body": 42000, "Interior": 18000, "SteeringWheel": 2500, "Glass": 6000,
             "Lights": 4000, "Brakes": 3000, "Wheel": 7000},
    "lite": {"Body": 20000, "Interior": 5000, "SteeringWheel": 800, "Glass": 2500,
             "Lights": 1500, "Brakes": 1000, "Wheel": 2500},
}[VARIANT]

DETACHABLE = {"Hood", "Trunk", "Door_L", "Door_R", "FrontBumper", "RearBumper", "Wing",
              "Mirror_L", "Mirror_R", "Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR"}
DENT_GROUPS = set()   # user choice: no dents, damage = parts falling off + glass
CRACK_GROUPS = {"Glass_Windshield", "Glass_Rear", "Glass_Door_L", "Glass_Door_R",
                "Glass_Quarter_L", "Glass_Quarter_R"}

# Pre-fractured groups: number of chunks (pieces with their own health in Roblox)
CHUNKS = {
    "high": {"Hood": 10, "Trunk": 8, "Door_L": 10, "Door_R": 10, "FrontBumper": 12, "RearBumper": 12,
             "Wing": 4, "Body_Front": 12, "Body_Mid": 10, "Body_Rear": 12,
             "Glass_Windshield": 30, "Glass_Rear": 20, "Glass_Door_L": 14, "Glass_Door_R": 14,
             "Glass_Quarter_L": 8, "Glass_Quarter_R": 8},
    "lite": {"Hood": 6, "Trunk": 5, "Door_L": 6, "Door_R": 6, "FrontBumper": 7, "RearBumper": 7,
             "Wing": 3, "Body_Front": 7, "Body_Mid": 6, "Body_Rear": 7,
             "Glass_Windshield": 16, "Glass_Rear": 12, "Glass_Door_L": 8, "Glass_Door_R": 8,
             "Glass_Quarter_L": 5, "Glass_Quarter_R": 5},
}[VARIANT]
GLASS_MAX_EDGE = 0.10 if VARIANT == "high" else 0.16   # subdivide glass so shards are even

DELETE_MATS = {"EXT_BADGE_PORSCHE", "EXT_DECAL_REAR", "EXT_Logo_Weissach", "int_Decal_Paint",
               "EXT_DECAL_2", "ext_Decal_Paint", "INT_DECALS", "INT_GPS"}
DELETE_OBJS = {"EXT_PLASTIC_GLOSS_2"}
DELETE_REGIONS = [
    ("EXT_CHROME_0", (-0.30, 0.30), (2.13, 2.20), (0.68, 0.712)),
    ("EXT_PLASTIC_GLOSS_0", (-0.275, 0.275), (2.13, 2.20), (0.68, 0.712)),
]

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
scene = bpy.context.scene
log = {"variant": VARIANT, "removed": [], "roles": {}, "groups": {}, "parts": []}


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


# =============================================================== 1. logos + textures
for o in list(meshes()):
    mats = {m.name for m in o.data.materials if m}
    if o.name in DELETE_OBJS or mats & DELETE_MATS:
        log["removed"].append(o.name)
        bpy.data.objects.remove(o, do_unlink=True)

for name, (x0, x1), (y0, y1), (z0, z1) in DELETE_REGIONS:
    o = bpy.data.objects.get(name)
    if not o:
        continue
    o.data = o.data.copy()
    mw = o.matrix_world
    bm = bmesh.new()
    bm.from_mesh(o.data)
    kill = []
    for f in bm.faces:
        c = mw @ f.calc_center_median()
        if x0 < c.x < x1 and y0 < c.y < y1 and z0 < c.z < z1:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data)
    bm.free()
    log["removed"].append(f"{name}: {len(kill)} faces")


def principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat and mat.node_tree else None


cap = bpy.data.materials.get("EXT_RIM_CAP")
if cap and cap.node_tree:
    for n in [n for n in cap.node_tree.nodes if n.type in ('TEX_IMAGE', 'NORMAL_MAP')]:
        cap.node_tree.nodes.remove(n)
    b = principled(cap)
    b.inputs["Base Color"].default_value = (0.03, 0.03, 0.03, 1)
    b.inputs["Metallic"].default_value = 0.9
    b.inputs["Roughness"].default_value = 0.3

paint = bpy.data.materials.get("CarPaint_flake")
if paint and paint.node_tree:
    nt = paint.node_tree
    b = principled(paint)
    for l in list(b.inputs["Normal"].links):
        nt.links.remove(l)
    for n in [n for n in nt.nodes if n.type == 'NORMAL_MAP']:
        nt.nodes.remove(n)
    for n in [n for n in nt.nodes if n.type == 'TEX_IMAGE' and not n.outputs[0].links]:
        nt.nodes.remove(n)


def img_px(img):
    w, h = img.size
    a = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, img.channels)


def img_set(img, a):
    img.pixels.foreach_set(a.ravel())
    img.update()
    img.pack()


def fill_rects(img_name, rects_top_left, color, ref=(2048, 2048)):
    """rects in pixel coords of a ref-size image, origin top-left (as seen in a viewer)."""
    img = bpy.data.images.get(img_name)
    if not img:
        return
    a = img_px(img)
    h, w = a.shape[:2]
    sx, sy = w / ref[0], h / ref[1]
    for x0, y0, x1, y1 in rects_top_left:
        X0, X1 = int(x0 * sx), int(x1 * sx)
        Y0, Y1 = h - int(y1 * sy), h - int(y0 * sy)   # flip: Blender rows start at the bottom
        a[max(0, Y0):min(h, Y1), max(0, X0):min(w, X1), :len(color)] = color
    img_set(img, a)
    log["removed"].append(f"texture {img_name}: {len(rects_top_left)} areas blanked")


# Gauge atlas: RS logo, GT3RS in the dial, the two big GT3RS words
ATLAS_RECTS = [(318, 482, 710, 583), (1341, 620, 1696, 673), (694, 1182, 2040, 1336), (694, 1457, 2040, 1611)]
fill_rects("911 GT3 RS", ATLAS_RECTS, (0, 0, 0))
fill_rects("911 GT3 RS_N", ATLAS_RECTS, (0.5, 0.5, 1.0))
# Side screen: photo of a real Porsche
fill_rects("GT3RS Side Decals", [(927, 578, 1150, 1028)], (0, 0, 0))

# Brake caliper: SHOCKWORKS lettering (fill with the caliper's own white)
fill_rects("EXT_CALIPER_AO_SHOCKWORKS", [(470, 830, 750, 880)], (0.93, 0.93, 0.94), ref=(1024, 1024))

# License plate: completely blank
lp = bpy.data.images.get("License_plate")
if lp:
    a = img_px(lp)
    a[:, :, :3] = 0.02
    img_set(lp, a)
    log["removed"].append("texture License_plate: blanked")


def blank_tyre(img_name, flat_from_ring):
    """Replace the sidewall ring (where MICHELIN / Pilot Sport text sits) with a plain fill."""
    img = bpy.data.images.get(img_name)
    if not img:
        return
    a = img_px(img)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = w / 2, h / 2
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (w / 1024)
    tread = (xx >= 235 * w / 1024) & (xx <= 790 * w / 1024) & (yy >= h - 810 * h / 1024) & (yy <= h - 210 * h / 1024)
    ring = (r >= 405) & (r <= 515) & ~tread
    if flat_from_ring:
        fill = np.median(a[ring], axis=0)       # typical sidewall rubber colour
    else:
        fill = np.array([0.5, 0.5, 1.0, 1.0][:a.shape[2]], dtype=np.float32)
    a[ring] = fill
    img_set(img, a)
    log["removed"].append(f"texture {img_name}: sidewall lettering blanked")


blank_tyre("Tyre_D", True)
blank_tyre("Tyre_NM", False)

# =============================================================== 2. roles
def world_center(o):
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return sum(bb, Vector()) / 8


def role_of(o):
    n = o.name
    if n.startswith(("EXT_GLASS", "EXT_WINDOW", "INT_WINDOW")):
        return "Glass"
    if n.startswith(("EXT_HL_", "EXT_TL_", "EXT_PLATE_LIGHT")) and n != "EXT_HL_HOUSE":
        return "Lights"
    p = o.parent
    while p:
        pn = p.name
        if pn.startswith("STEER_HR"):
            return "SteeringWheel"
        if pn.startswith(("WHEEL_", "RIM", "DISC_")):
            c = world_center(o)
            return "Wheel_" + side(c.x) + ("F" if c.y < 0 else "R")
        if pn.startswith("SUSP_"):
            return "Brakes"
        if pn.startswith(("COCKPIT_HR", "ARROW_")):
            return "Body" if n.startswith("EXT_") else "Interior"
        p = p.parent
    return "Body"


role = {o.name: role_of(o) for o in meshes()}

wheel_centers = {}
for o in meshes():
    r = role[o.name]
    if r.startswith("Wheel_"):
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        lo, hi = wheel_centers.get(r, (Vector((9e9,) * 3), Vector((-9e9,) * 3)))
        for p in pts:
            lo = Vector(map(min, lo, p)); hi = Vector(map(max, hi, p))
        wheel_centers[r] = (lo, hi)
wheel_centers = {k: (lo + hi) / 2 for k, (lo, hi) in wheel_centers.items()}

# =============================================================== 3. bake transforms
world = {o.name: o.matrix_world.copy() for o in meshes()}
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

# =============================================================== 4. damage groups
def zone(y):
    return "Body_Front" if y < -0.80 else ("Body_Rear" if y > 0.62 else "Body_Mid")


PAINT_OBJ = {"ext_Body_hood": "Hood", "ext_Body_trunk": "Trunk", "ext_Body_frontBumper": "FrontBumper",
             "ext_Body_rearBumper": "RearBumper", "ext_Body_spoiler": "Wing",
             "ext_Body_doors": "DOOR", "ext_Body_fenders": "ZONE"}


def paint_group(objname, c):
    g = PAINT_OBJ[objname]
    if g == "DOOR":
        return "Door_" + side(c.x)
    if g == "ZONE":
        return zone(c.y)
    return g


# BVH over all paint panels; remember the group of each paint face
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


def in_box(c, xa, ya, za):
    return xa[0] <= abs(c.x) <= xa[1] and ya[0] <= c.y <= ya[1] and za[0] <= c.z <= za[1]


def region_group(c, objname=""):
    """Areas where carbon/black trim belongs to a panel even when not touching its paint."""
    if objname.startswith("EXT_EXHAUST"):
        return None
    if (c.y > 1.80 and abs(c.x) < 0.45 and c.z > 0.98) or \
       (c.y > 1.60 and 0.25 < abs(c.x) < 0.40 and c.z > 0.88):
        return "Wing"                      # swan-neck wing posts
    if -2.05 < c.y < -0.95 and abs(c.x) < 0.62 and c.z > 0.55:
        return "Hood"                      # carbon hood centre + vents
    if 1.45 < c.y < 2.12 and abs(c.x) < 0.62 and 0.78 < c.z < 1.06:
        return "Trunk"                     # engine cover + grille
    if c.y < -1.95 and c.z < 0.50:
        return "FrontBumper"               # lower front splitter / intakes
    if c.y > 2.05 and c.z < 0.62:
        return "RearBumper"                # diffuser
    return None


def body_island_group(me, isl, objname=""):
    pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
    lo, hi = bounds(pts)
    c = (lo + hi) / 2
    size = hi - lo
    if max(size) <= 1.0:
        step = max(1, len(isl) // 60)
        reg = [region_group(me.polygons[f].center, objname) for f in isl[::step]]
        for g in ("Wing", "Hood", "Trunk", "FrontBumper", "RearBumper"):
            if reg.count(g) >= 0.6 * len(reg):
                return {"*": g}
    if in_box(c, (0.82, 1.2), (-0.50, -0.12), (0.78, 1.02)) and max(size) < 0.4:
        return {"*": "Mirror_" + side(c.x)}
    if c.y > 1.70 and c.z > 1.06 and max(size) < 1.9:
        return {"*": "Wing"}
    if max(size) > 1.0:
        # big piece spanning several panels: decide per face
        return None
    votes = {}
    step = max(1, len(isl) // 60)
    for f in isl[::step]:
        g = nearest_panel(me.polygons[f].center)
        if g:
            votes[g] = votes.get(g, 0) + 1
    total = len(isl[::step])
    if votes:
        g, n = max(votes.items(), key=lambda kv: kv[1])
        if n >= 0.3 * total and not g.startswith("Body_"):
            return {"*": g}
    return {"*": zone(c.y)}


def glass_island_group(objname, me, isl):
    pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
    lo, hi = bounds(pts)
    c = (lo + hi) / 2
    if objname.startswith("EXT_GLASS_HDL"):
        return "HeadLight_" + side(c.x)
    if objname.startswith("EXT_GLASS_RED"):
        return None                       # spans both sides: per face
    if objname.startswith("EXT_GLASS_NM"):
        return "Body_Rear"
    if abs(c.x) < 0.45 and c.y < -0.2:
        return "Glass_Windshield"
    if abs(c.x) < 0.45 and c.y > 0.6:
        return "Glass_Rear"
    if c.y < 0.56:
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
    assign = {}   # face index -> group
    if r == "Body":
        if o.name in PAINT_OBJ:
            for p in me.polygons:
                assign[p.index] = paint_group(o.name, p.center)
        else:
            for isl in islands(me):
                res = body_island_group(me, isl, o.name)
                if res is None:
                    for f in isl:
                        c = me.polygons[f].center
                        g = region_group(c, o.name) or nearest_panel(c)
                        assign[f] = g if g and not g.startswith("Body_") else zone(c.y)
                else:
                    for f in isl:
                        assign[f] = res["*"]
    elif r == "Glass":
        for isl in islands(me):
            g = glass_island_group(o.name, me, isl)
            for f in isl:
                c = me.polygons[f].center
                assign[f] = g if g else "TailLight_" + side(c.x)
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
            if abs(c.x) > 0.60 and -0.78 < c.y < 0.55 and max(hi - lo) < 1.2:
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
    if len(by_g) == 1:
        g = next(iter(by_g))
        parts.append((o, rr, g))
        continue
    for g, fids in by_g.items():
        no = extract(o, fids, f"{o.name}@{g}")
        parts.append((no, rr, g))
    bpy.data.objects.remove(o, do_unlink=True)

# Bay floors: when the hood / engine cover falls off you see a dark bay, not a hole
liner_mat = bpy.data.materials.new("BayLiner")
liner_mat.use_nodes = True
lb = principled(liner_mat)
lb.inputs["Base Color"].default_value = (0.025, 0.025, 0.028, 1)
lb.inputs["Roughness"].default_value = 0.85


def add_liner(panel, group, drop, name):
    pts = [v.co for o, r, g in parts if g == panel for v in o.data.vertices]
    if not pts:
        return
    lo, hi = bounds(pts)
    inset = 0.04
    z = lo.z + drop
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    nx, ny = 6, 8
    vs = [[bm.verts.new((lo.x + inset + (hi.x - lo.x - 2 * inset) * i / nx,
                         lo.y + inset + (hi.y - lo.y - 2 * inset) * j / ny, z))
           for j in range(ny + 1)] for i in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        if f.normal.z < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(liner_mat)
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    parts.append((o, "Body", group))


add_liner("Hood", "Body_Front", 0.02, "FrunkFloor")
add_liner("Trunk", "Body_Rear", 0.03, "EngineBayFloor")

grp_before = {}
for o, r, g in parts:
    grp_before[g] = grp_before.get(g, 0) + tris(o)
print("groups:", json.dumps(grp_before, indent=0))

# =============================================================== 5. simplify per role
def weight(o):
    mats = " ".join(m.name for m in o.data.materials if m)
    if "CarPaint" in mats or "Body_Paint" in mats:
        return 6.0
    if any(k in mats for k in ("GLASS", "WINDOW", "CHROME", "Headlight", "HL_")):
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
    key = g if r == "Wheel" else r       # each wheel gets its own wheel budget
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
            m = Vector((0.02,) * 3)
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bad = [v for v in bm.verts if any(not (lo[i] - m[i] <= v.co[i] <= hi[i] + m[i]) for i in range(3))]
            if bad:
                bmesh.ops.delete(bm, geom=bad, context='VERTS')
                bm.to_mesh(o.data)
            bm.free()
        o.data.shade_smooth()
        o.data.set_sharp_from_angle(angle=SMOOTH_ANGLE)
    log["roles"][key] = {"before": before, "after": sum(tris(o) for o in objs)}
    print(f"{key}: {before} -> {log['roles'][key]['after']}")

# =============================================================== 6. remove faces nobody can see
# Occluders: only parts that never fall off and are not see-through. Faces of parts that
# can fall off are never removed (they can be seen from every side once loose), and a face
# only counts as hidden if it stays hidden with every loose part already gone.
def fib_sphere(n, radius, center):
    pts = []
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        rad = math.sqrt(1 - y * y)
        pts.append(center + Vector((math.cos(ga * i) * rad, math.sin(ga * i) * rad, y)) * radius)
    return pts


views = fib_sphere(160, 9.0, Vector((0, 0, 0.6)))
views += [Vector(v) for v in [(0.34, 0.12, 1.02), (-0.34, 0.12, 1.02), (0.0, 0.3, 0.95),
                              (0.34, -0.2, 0.95), (-0.34, -0.2, 0.95), (0.0, 0.9, 0.9)]]
V = np.array([tuple(v) for v in views])

fixed = [(o, g) for o, r, g in parts if g not in DETACHABLE and not g.startswith("Glass_")
         and not any("GLASS" in (m.name if m else "") or "WINDOW" in (m.name if m else "")
                     for m in o.data.materials)]
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
                d = V - np.array(tuple(s))
                dots = d @ np.array(tuple(n))
                order = np.argsort(-dots)
                origin = s + n * 0.002
                for k in order:
                    if dots[k] <= 0:
                        break
                    vp = views[k]
                    dirv = (vp - origin)
                    dist = dirv.length
                    hit = occ.ray_cast(origin, dirv / dist, dist)
                    if hit[0] is None:
                        seen = True
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


def pack(me, fids, maxt):
    if tri_count(me, fids) <= maxt:
        return [fids]
    return spatial_chunks(me, fids, maxt)


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
    """Store current shading as custom normals so splitting into chunks leaves no seams."""
    try:
        cn = [tuple(c.vector) for c in me.corner_normals]
        me.normals_split_custom_set(cn)
    except Exception as ex:
        print("  normals freeze skipped:", ex)


def chunk_faces(me, n_chunks, seed):
    """Voronoi-style chunks on the surface: area-weighted random seeds, 2 Lloyd relaxation
    steps, every face goes to its nearest seed."""
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
    # renumber to 0..n-1 without gaps
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
        chunks = pack(me, fids, MAX_TRIS)
        for k, ch in enumerate(chunks):
            mid = f"C{ci + 1:02d}__" if g in CHUNKS else ""
            nm = f"{g}__{mid}{mname}" + (f"_{k + 1}" if len(chunks) > 1 else "")
            no = single_mat(j, ch, nm, mat)
            no["group"] = g
            no["chunk"] = ci + 1 if g in CHUNKS else 0
            no["dmg"] = False
            final.append(no)
    bpy.data.objects.remove(j, do_unlink=True)

# =============================================================== 8. damaged versions
def make_crack_image(size=1024, seed=7):
    """Spiderweb cracks: white jagged lines on a faint transparent tint (RGBA, alpha = crack)."""
    rng = np.random.default_rng(seed)
    a = np.zeros((size, size, 4), dtype=np.float32)
    a[:, :, :3] = 0.85
    a[:, :, 3] = 0.10                        # slight frosting everywhere

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
            ang += rng.normal(0, 0.06)        # mostly straight, like real glass cracks
            last = pts[-1]
            pts.append((last[0] + np.cos(ang) * length / steps, last[1] + np.sin(ang) * length / steps))
        for u, v in zip(pts, pts[1:]):
            line(u, v, r, alpha)
            if depth < 1 and rng.random() < 0.03:   # occasional side branch
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
        # concentric rings joining neighbouring spokes
        for ring in (1, 2, 4, 7):
            for k in range(n_rad):
                s1, s2 = spokes[k], spokes[(k + 1) % n_rad]
                i1, i2 = min(ring, len(s1) - 1), min(ring, len(s2) - 1)
                if rng.random() < (0.95 if ring < 3 else 0.6):
                    line(s1[i1], s2[i2], 1 if ring < 3 else 0, 0.8)
        # crushed centre
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


def planar_uvs(me):
    """One crack pattern per window: project along the part's average normal, fit to 0..1."""
    if not me.polygons:
        return
    n = sum((p.normal * p.area for p in me.polygons), Vector())
    n = n.normalized() if n.length > 1e-6 else Vector((0, 0, 1))
    up = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((0, 1, 0))
    u_ax = up.cross(n).normalized()
    v_ax = n.cross(u_ax).normalized()
    us = [v.co.dot(u_ax) for v in me.vertices]
    vs = [v.co.dot(v_ax) for v in me.vertices]
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    su, sv = max(u1 - u0, 1e-6), max(v1 - v0, 1e-6)
    while len(me.uv_layers) > 1:
        me.uv_layers.remove(me.uv_layers[-1])
    uvl = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        uvl.data[loop.index].uv = ((co.dot(u_ax) - u0) / su, (co.dot(v_ax) - v0) / sv)


dmg_mats = {}


def dmg_material(mat, cracked):
    key = (mat.name if mat else "None", cracked)
    if key in dmg_mats:
        return dmg_mats[key]
    m = mat.copy() if mat else bpy.data.materials.new("NoMat")
    m.name = (mat.name if mat else "NoMat") + ("_CRACKED" if cracked else "_DMG")
    b = principled(m)
    if b:
        bc = b.inputs["Base Color"]
        rough = b.inputs["Roughness"]
        if cracked:
            if not bc.is_linked:
                c = bc.default_value
                bc.default_value = (min(1, c[0] * 0.6 + 0.35), min(1, c[1] * 0.6 + 0.35), min(1, c[2] * 0.6 + 0.35), 1)
            if not rough.is_linked:
                rough.default_value = 0.55
            a = b.inputs["Alpha"]
            if not a.is_linked:
                a.default_value = min(1.0, a.default_value + 0.35)
        else:
            if not bc.is_linked:
                c = bc.default_value
                bc.default_value = (c[0] * 0.72, c[1] * 0.72, c[2] * 0.72, 1)
            if not rough.is_linked:
                rough.default_value = min(1.0, rough.default_value + 0.35)
    dmg_mats[key] = m
    return m


def dent(me):
    """Push vertices inward along their normals using world-space noise, so neighbouring
    panels deform the same way at their seams."""
    for v in me.vertices:
        p = v.co
        big = noise.noise(p * 2.2)
        d = max(0.0, big - 0.12) * 0.09
        crumple = noise.noise(p * 9.0 + Vector((7.3, 1.1, 4.2))) * 0.006
        v.co = p - v.normal * d + v.normal * crumple


for no in list(final):
    g = no["group"]
    if g not in DENT_GROUPS and g not in CRACK_GROUPS:
        continue
    cracked = g in CRACK_GROUPS
    me = no.data.copy()
    mat = no.data.materials[0]
    me.materials.clear()
    if cracked:
        # cracked twin reads the whole-window crack map: make CrackUV its only UV layer
        if "CrackUV" in me.uv_layers:
            for l in [l for l in me.uv_layers if l.name != "CrackUV"]:
                me.uv_layers.remove(l)
            me.uv_layers["CrackUV"].name = "UVMap"
        else:
            planar_uvs(me)
        me.materials.append(cracked_material())
    else:
        dent(me)
        me.materials.append(dmg_material(mat, cracked))
    segs = no.name.split("__")
    if len(segs) >= 3 and segs[1].startswith("C") and segs[1][1:].isdigit():
        name = f"{g}__{segs[1]}__DMG__{'__'.join(segs[2:])}"
    else:
        name = f"{g}__DMG__{'__'.join(segs[1:])}"
    me.name = name
    d = bpy.data.objects.new(name, me)
    scene.collection.objects.link(d)
    d["group"] = g
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
        vs = [v.co for v in no.data.vertices]
        lo, hi = bounds(vs)
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

for no in sorted(final, key=lambda o: o.name):
    log["parts"].append({"name": no.name, "group": no["group"], "dmg": bool(no["dmg"]), "tris": tris(no)})
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
json.dump(log, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1)
print("visible tris:", log["visible_tris"], "dmg tris:", log["dmg_tris"], "parts:", log["part_count"],
      "max part:", log["max_part_tris"])

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, NAME + ".blend"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), export_format='GLB',
                          export_yup=True, export_apply=True)
