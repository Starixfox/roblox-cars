"""GAC Empow (Sketchfab, ParticleAccelerator5000 / Tvclap, listed CC BY 4.0) -> Roblox, with damage parts.
Adapted from the Porsche GT3 RS pipeline (prep2.py).

Usage (via run.ps1 / wrap.py):  prep.py high   or   prep.py lite

Output part names:  <Group>__<Material>[_n]                  unchunked part
                    <Group>__C<nn>__<Material>[_n]           chunk part
                    <Group>__C<nn>__DMG__<Material>[_n]      cracked glass twin
Detachable: Hood, Trunk, Door_L, Door_R, Door_RL, Door_RR, FrontBumper, RearBumper,
            Mirror_L, Mirror_R, Wheel_LF, Wheel_RF, Wheel_LR, Wheel_RR
Fixed: Body_Front, Body_Mid, Body_Rear, Interior, SteeringWheel, Brakes, HeadLight_L/R, TailLight_L/R,
       Glass_Windshield, Glass_Roof, Glass_Rear, Glass_Door_L/R/RL/RR (ride on their doors)
The source is a material-merged OBJ: objects are material chunks, so everything is classified per
mesh island by material + position.  Car faces -Y, Z up, +X is the driver's left.
"""
import bpy, bmesh, os, sys, json, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

VARIANT = (sys.argv[1] if len(sys.argv) > 1 else "high").lower()
ROOT = r"C:\Users\jordan\RobloxCars\gac-empow"
GLB = os.path.join(ROOT, "source", "source", "gac_empow.glb")
OUT = os.path.join(ROOT, "roblox")
NAME = "GAC_Empow_" + VARIANT.capitalize()
MAX_TRIS = 19000
TEX_MAX = 1024 if VARIANT == "high" else 512
SMOOTH_ANGLE = math.radians(35)

# source units -> metres, car centred on the origin, wheels on z = 0 (front already toward -Y)
S = 4.70 / 58.061
NORM = Matrix.Diagonal((S, S, S, 1)) @ Matrix.Translation((-13.097, -29.044, 0))

ROLE_BUDGET = {
    "high": {"Body": 44000, "Interior": 17000, "SteeringWheel": 2500, "Glass": 5000,
             "Lights": 5000, "Brakes": 3000, "Wheel": 6500},
    "lite": {"Body": 20000, "Interior": 5000, "SteeringWheel": 800, "Glass": 2000,
             "Lights": 1800, "Brakes": 1000, "Wheel": 2400},
}[VARIANT]

DETACHABLE = {"Hood", "Trunk", "Door_L", "Door_R", "Door_RL", "Door_RR", "FrontBumper", "RearBumper",
              "Mirror_L", "Mirror_R", "Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR"}
CRACK_GROUPS = {"Glass_Windshield", "Glass_Roof", "Glass_Rear", "Glass_Door_L", "Glass_Door_R",
                "Glass_Door_RL", "Glass_Door_RR"}
CHUNKS = {
    "high": {"Hood": 14, "Trunk": 12, "Door_L": 10, "Door_R": 10, "Door_RL": 9, "Door_RR": 9,
             "FrontBumper": 18, "RearBumper": 18, "Body_Front": 14, "Body_Mid": 16, "Body_Rear": 16,
             "Glass_Windshield": 36, "Glass_Roof": 20, "Glass_Rear": 30, "Glass_Door_L": 16, "Glass_Door_R": 16,
             "Glass_Door_RL": 14, "Glass_Door_RR": 14},
    "lite": {"Hood": 9, "Trunk": 8, "Door_L": 8, "Door_R": 8, "Door_RL": 7, "Door_RR": 7,
             "FrontBumper": 12, "RearBumper": 12, "Body_Front": 9, "Body_Mid": 10, "Body_Rear": 10,
             "Glass_Windshield": 22, "Glass_Roof": 12, "Glass_Rear": 16, "Glass_Door_L": 10, "Glass_Door_R": 10,
             "Glass_Door_RL": 9, "Glass_Door_RR": 9},
}[VARIANT]
GLASS_MAX_EDGE = 0.10 if VARIANT == "high" else 0.16

WHEEL_MATS = {"Tires", "Rims1", "Rims2", "BrakeRotors"}
LIGHT_MATS = {"HeadLightsGlass", "DRLs", "SilverChrome", "BrakeLightsGlass1", "BrakeLightsGlass2",
              "DarkRedChrome", "RedMain", "SignalLens", "Reflectors"}
GLASS_MATS = {"Windows"}
PAINT = "Matte_Green"
DELETE_MATS = {"Decals"}           # badges, EMPOW lettering, white side stickers
STEER_HUB = Vector((0.365, -0.45, 0.90))

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


def drop_loose(bm):
    """face deletion leaves loose edges/verts behind: they would skew bounds and pivots"""
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    loose_e = [e for e in bm.edges if not e.link_faces]
    if loose_e:
        bmesh.ops.delete(bm, geom=loose_e, context='EDGES')


def principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat and mat.node_tree else None


# =============================================================== 0. materials: no brand in names, carbon colour
for m in bpy.data.materials:
    m.name = m.name.replace("2022_GAC_Empow_", "")
for mn in ("Carbon_Fiber", "CarbonFiber"):
    m = bpy.data.materials.get(mn)
    b = principled(m)
    if b:    # carbon texture is not in the download: plain dark carbon grey instead of white
        b.inputs["Base Color"].default_value = (0.03, 0.03, 0.033, 1)
        b.inputs["Roughness"].default_value = 0.35

# =============================================================== 1. bake transforms
world = {o.name: o.matrix_world.copy() for o in meshes()}
for o in list(meshes()):
    o.parent = None
    o.data = o.data.copy()
    o.data.transform(NORM @ world[o.name])
    o.matrix_world = Matrix.Identity(4)
    if o.data.has_custom_normals:
        with override(o):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    bm.to_mesh(o.data)
    bm.free()
for o in [o for o in scene.objects if o.type == 'EMPTY']:
    bpy.data.objects.remove(o, do_unlink=True)


def mat_of(o):
    return o.data.materials[0].name if o.data.materials and o.data.materials[0] else "None"


for o in list(meshes()):
    if mat_of(o) in DELETE_MATS:
        log["removed"].append(f"{o.name} ({mat_of(o)}): {tris(o)} tris")
        bpy.data.objects.remove(o, do_unlink=True)


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


def isl_info(me, isl):
    pts = [me.vertices[v].co for f in isl for v in me.polygons[f].vertices]
    lo, hi = bounds(pts)
    return lo, hi, (lo + hi) / 2, max(hi - lo)


def delete_faces(o, fids):
    if not fids:
        return
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in fids], context='FACES')
    drop_loose(bm)
    bm.to_mesh(o.data)
    bm.free()


# wheel hubs from the four tyre islands
hubs = {}
for o in meshes():
    if mat_of(o) == "Tires":
        for isl in islands(o.data):
            lo, hi, c, s = isl_info(o.data, isl)
            if s > 0.4:
                hubs["Wheel_" + side(c.x) + ("F" if c.y < 0 else "R")] = c
print("hubs:", {k: tuple(round(x, 3) for x in v) for k, v in hubs.items()})


def logo_island(mat, lo, hi, c, s):
    ax = abs(c.x)
    if mat in ("ChromeTrims", "BlackChrome") and ax < 0.1 and c.y < -2.32 and 0.53 < c.z < 0.70 and s < 0.2:
        return "front grille logo"
    if mat == "YellowTrims" and 0.30 < c.x < 0.38 and c.y < -2.29 and 0.60 < c.z < 0.66 and s < 0.05:
        return "grille S badge"
    if mat == "ChromeTrims" and ax < 0.06 and c.y > 2.27 and 0.99 < c.z < 1.08 and s < 0.12:
        return "rear logo"
    if mat in ("ChromeTrims", "BlackChrome") and 0.32 < ax < 0.55 and c.y > 2.24 and 0.765 < c.z < 0.81 and s < 0.07:
        return "rear model lettering"
    if mat == "BlackChrome" and 0.80 < ax < 0.87 and hi.x - lo.x < 0.003 and s < 0.03:
        for h in hubs.values():
            if abs(c.y - h.y) < 0.25 and abs(c.z - h.z) < 0.25 and (c.x > 0) == (h.x > 0):
                return "caliper lettering"
    if mat == "ChromeTrims" and ax > 0.85 and s > 0.04 and s < 0.09:
        for h in hubs.values():
            if abs(c.y - h.y) < 0.02 and abs(c.z - h.z) < 0.02:
                return "wheel centre cap logo"
    if mat == "Interior" and 0.35 < c.x < 0.38 and -0.41 < c.y < -0.40 and 0.885 < c.z < 0.90 and s < 0.02:
        return "steering wheel logo"
    if mat == "Interior" and 0.35 < c.x < 0.38 and -0.43 < c.y < -0.41 and 0.915 < c.z < 0.935 and 0.04 < s < 0.06:
        return "steering wheel logo ring"
    return None


# =============================================================== 2. duplicate islands + logos
# The source has many islands twice (interior layers, calipers in two materials): z-fighting copies.
order = sorted(meshes(), key=lambda o: (mat_of(o) == "Interior", o.name))
seen_sig = set()
dupe_tris = 0
logo_counts = {}
for o in order:
    me = o.data
    mat = mat_of(o)
    kill = []
    for isl in islands(me):
        lo, hi, c, s = isl_info(me, isl)
        why = logo_island(mat, lo, hi, c, s)
        if why:
            kill += isl
            logo_counts[why] = logo_counts.get(why, 0) + 1
            continue
        sig = (sum(len(me.polygons[f].vertices) - 2 for f in isl),) + \
              tuple(int(round(v * 500)) for v in tuple(lo) + tuple(hi))
        if sig in seen_sig:
            kill += isl
            dupe_tris += sig[0]
        else:
            seen_sig.add(sig)
    delete_faces(o, kill)
log["removed"] += [f"{k}: {v} island(s)" for k, v in logo_counts.items()]
log["duplicate_tris_removed"] = dupe_tris
print("logos:", logo_counts, "duplicate tris removed:", dupe_tris)

# =============================================================== 3. damage groups
def zone(y):
    return "Body_Front" if y < -0.95 else ("Body_Rear" if y > 1.30 else "Body_Mid")


def door(c):
    return ("Door_" if c.y < 0.165 else "Door_R") + side(c.x)


def paint_island_group(lo, hi, c, s):
    ax = abs(c.x)
    if s < 0.35 and ax > 0.8 and 0.85 < c.z < 1.0 and -1.0 < c.y < 1.3:
        return door(c)                             # flush door handles
    if lo.y > -2.25 and hi.y < -1.1 and lo.z > 0.78 and ax < 0.2:
        return "Hood"
    if hi.y < -1.6:
        return "FrontBumper"
    if ax > 0.6 and hi.y < -0.85 and lo.y < -1.5:
        return "Body_Front"                        # front fenders
    if ax > 0.7 and lo.y > -1.0 and hi.y < 0.2:
        return door(c)
    if ax > 0.7 and lo.y > 0.1 and hi.y < 1.35:
        return door(c)
    if hi.z < 0.35:
        return "Body_Mid"                          # side skirts
    if lo.y > 1.8 and lo.z > 0.6 and hi.x - lo.x < 1.25:
        return "Trunk"
    if lo.y > 1.4:
        return "RearBumper"
    return None                                    # body sides: per face by zone


def region_group(c):
    """Areas where trim belongs to a panel even when not touching its paint."""
    ax = abs(c.x)
    if c.y < -1.95 and c.z < 0.70 and not (ax > 0.45 and c.z > 0.62):
        return "FrontBumper"                       # grille, intakes, lip
    if (c.y > 1.95 and c.z < 0.66) or (c.y > 1.75 and c.z < 0.45) or (c.y > 1.7 and c.z < 0.75 and ax < 0.7):
        return "RearBumper"                        # diffuser, exhausts, lower frame
    if c.y < -1.85 and c.z < 0.42:
        return "FrontBumper"                       # lower front frame
    if -2.2 < c.y < -1.17 and ax < 0.78 and c.z > 0.84:
        return "Hood"
    if c.y > 1.85 and ax < 0.58 and 0.66 < c.z < 1.16:
        return "Trunk"
    return None


def in_mirror(c, s):
    return abs(c.x) > 0.80 and -0.80 < c.y < -0.42 and 0.95 < c.z < 1.32 and s < 0.4


def glass_group(c):
    if abs(c.x) < 0.5:
        if c.y < -0.3 and c.z < 1.42:
            return "Glass_Windshield"
        return "Glass_Roof" if c.y < 0.542 else "Glass_Rear"
    if c.y < 0.2:
        return "Glass_Door_" + side(c.x)
    if c.y < 1.3:
        return "Glass_Door_R" + side(c.x)
    return "Glass_Quarter_" + side(c.x)


def light_group(c):
    ax = abs(c.x)
    if ax < 0.2 and c.y > 1.7 and c.z > 1.1:
        return "Body_Rear"                         # third brake light
    if c.y < -1.95 and c.z < 0.62:
        return "FrontBumper"
    if c.y > 1.7 and c.z < 0.72:
        return "RearBumper"                        # bumper reflectors
    if c.y < 0:
        return "HeadLight_" + side(c.x)
    if c.y > 2.0 and ax < 0.59:
        return "Trunk"                             # inner tail-light segments sit in the boot lid
    return "TailLight_" + side(c.x)


def wheel_of(c, s):
    for w, h in hubs.items():
        if abs(c.y - h.y) < 0.40 and abs(c.z - h.z) < 0.40 and abs(c.x) > 0.55 and (c.x > 0) == (h.x > 0) and s < 0.8:
            return w, math.hypot(c.y - h.y, c.z - h.z)
    return None, 9


def in_cabin(c):
    return -1.32 < c.y < 1.9 and c.z > 0.28 and abs(c.x) < 0.9


# BVH over all paint panels; remember the group of each paint face
pv, pp, pgroup = [], [], []
paint_assign = {}
for o in meshes():
    if mat_of(o) != PAINT:
        continue
    me = o.data
    asg = {}
    for isl in islands(me):
        lo, hi, c, s = isl_info(me, isl)
        g = paint_island_group(lo, hi, c, s)
        for f in isl:
            asg[f] = g or zone(me.polygons[f].center.y)
    paint_assign[o.name] = asg
    base = len(pv)
    pv += [v.co.copy() for v in me.vertices]
    for p in me.polygons:
        pp.append([base + i for i in p.vertices])
        pgroup.append(asg[p.index])
paint_bvh = BVHTree.FromPolygons(pv, pp)


def nearest_panel(co, maxd=0.03):
    hit = paint_bvh.find_nearest(co, maxd)
    return pgroup[hit[2]] if hit and hit[0] is not None else None


def body_island(me, isl, c, s):
    """returns a group for the whole island, or None = decide per face"""
    if s <= 0.6:
        step = max(1, len(isl) // 60)
        reg = [region_group(me.polygons[f].center) for f in isl[::step]]
        for g in ("Hood", "Trunk", "FrontBumper", "RearBumper"):
            if reg.count(g) >= 0.6 * len(reg):
                return g
    if in_mirror(c, s):
        return "Mirror_" + side(c.x)
    if s > 0.6:
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
            return g
    return zone(c.y)


def classify(o, me, isl):
    """-> (role, group or None)"""
    mat = mat_of(o)
    lo, hi, c, s = isl_info(me, isl)
    if mat == PAINT:
        return "Body", "PAINT"
    w, d = wheel_of(c, s)
    if w:
        if mat in WHEEL_MATS or (mat == "ChromeTrims" and s < 0.1) or (d < 0.03 and abs(c.x) > 0.84):
            return "Wheel", w
        if mat in ("BrakePads", "YellowTrims") or (s < 0.45 and d < 0.30):
            return "Brakes", "Brakes"
    if in_mirror(c, s):
        return ("Lights" if mat in LIGHT_MATS else "Body"), "Mirror_" + side(c.x)
    if mat == "Mirrors":
        return "Interior", "Interior"              # rear-view mirror glass
    if mat in GLASS_MATS:
        return "Glass", glass_group(c)
    if mat in LIGHT_MATS:
        return "Lights", light_group(c)
    if mat == "Interior" and in_cabin(c):
        if (c - STEER_HUB).length < 0.22 and s < 0.42:
            return "SteeringWheel", "SteeringWheel"
        minabs = min(abs(lo.x), abs(hi.x)) if lo.x * hi.x > 0 else 0
        if abs(c.x) > 0.64 and minabs > 0.5 and s < 1.25 and -0.97 < c.y < 1.31 and 0.3 < c.z < 1.25:
            return "Interior", door(c)             # door cards ride with the door
        return "Interior", "Interior"
    return "Body", body_island(me, isl, c, s)


def extract(o, fids, name):
    nm = o.data.copy()
    keep = set(fids)
    bm = bmesh.new()
    bm.from_mesh(nm)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context='FACES')
    drop_loose(bm)
    bm.to_mesh(nm)
    bm.free()
    no = bpy.data.objects.new(name, nm)
    scene.collection.objects.link(no)
    return no


parts = []   # (object, role, group)
for o in list(meshes()):
    me = o.data
    assign = {}   # face -> (role, group)
    for isl in islands(me):
        r, g = classify(o, me, isl)
        if g == "PAINT":
            for f in isl:
                assign[f] = (r, paint_assign[o.name][f])
        elif g is None:
            for f in isl:
                c = me.polygons[f].center
                gg = region_group(c) or nearest_panel(c)
                if gg == "Hood" and c.y > -1.17:
                    gg = None                      # cowl under the windshield stays on the body
                assign[f] = (r, gg if gg and not gg.startswith("Body_") else zone(c.y))
        else:
            for f in isl:
                assign[f] = (r, g)
    by_g = {}
    for f, rg in assign.items():
        by_g.setdefault(rg, []).append(f)
    if len(by_g) == 1:
        (r, g), = by_g.keys()
        parts.append((o, r, g))
        continue
    for (r, g), fids in by_g.items():
        no = extract(o, fids, f"{o.name}@{g}@{r}")
        parts.append((no, r, g))
    bpy.data.objects.remove(o, do_unlink=True)

# Bay floors: when the hood / boot lid falls off you see a dark bay, not a hole
liner_mat = bpy.data.materials.new("BayLiner")
liner_mat.use_nodes = True
lb = principled(liner_mat)
lb.inputs["Base Color"].default_value = (0.025, 0.025, 0.028, 1)
lb.inputs["Roughness"].default_value = 0.85


def add_liner(name, group, xh, y0, y1, z):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    nx, ny = 6, 8
    vs = [[bm.verts.new((-xh + 2 * xh * i / nx, y0 + (y1 - y0) * j / ny, z)) for j in range(ny + 1)]
          for i in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    for f in bm.faces:
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(liner_mat)
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    parts.append((o, "Body", group))


def paint_bounds(g):
    pts = []
    for o, r, gg in parts:
        if gg == g and o.data.materials and o.data.materials[0] and o.data.materials[0].name == PAINT:
            pts += [v.co for v in o.data.vertices]
    return bounds(pts) if pts else (None, None)


for o, r, g in parts:     # debug: panel parts reaching far outside their panel area
    if g in ("Hood", "Trunk") and len(o.data.vertices):
        lo, hi = bounds([v.co for v in o.data.vertices])
        if (g == "Hood" and hi.y > -1.0) or (g == "Trunk" and lo.y < 1.6):
            print("  far", g, o.name, tris(o), tuple(round(x, 2) for x in lo), tuple(round(x, 2) for x in hi))
            bad = [p.center for p in o.data.polygons if (g == "Hood" and p.center.y > -1.15) or (g == "Trunk" and p.center.y < 1.7)]
            print("     faces outside:", len(bad), [tuple(round(x, 2) for x in c) for c in bad[:6]])

if len(sys.argv) > 2 and sys.argv[2] == "debug":
    raise RuntimeError("debug stop after classification")

lo, hi = paint_bounds("Hood")
if lo:
    print("hood paint bounds", tuple(lo), tuple(hi))
    add_liner("FrunkFloor", "Body_Front", 0.60, lo.y + 0.22, hi.y - 0.06, lo.z - 0.04)
lo, hi = paint_bounds("Trunk")
if lo:
    print("trunk paint bounds", tuple(lo), tuple(hi))
    add_liner("BootFloor", "Body_Rear", 0.55, max(1.80, lo.y - 0.05), hi.y - 0.10, 0.70)

grp_before = {}
for o, r, g in parts:
    grp_before[g] = grp_before.get(g, 0) + tris(o)
print("groups:", json.dumps(grp_before, indent=0))
log["groups_before_simplify"] = grp_before

# =============================================================== 4. simplify per role
def weight(o):
    mats = " ".join(m.name for m in o.data.materials if m)
    if PAINT in mats:
        return 6.0
    if any(k in mats for k in ("Windows", "Chrome", "Light", "DRL", "Rims", "Tires")):
        return 2.0
    return 1.0


def target_tris(t, w, r, floor=120):
    return max(min(t, floor), t * min(1.0, r * w))


def ratio_for(objs, budget):
    counts = [(tris(o), weight(o)) for o in objs]
    if sum(t for t, _ in counts) <= budget:
        return 1.0
    lo_, hi_ = 0.0, 1.0
    for _ in range(40):
        r = (lo_ + hi_) / 2
        s = sum(target_tris(t, w, r) for t, w in counts)
        lo_, hi_ = (r, hi_) if s < budget else (lo_, r)
    return lo_


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

# =============================================================== 5. remove faces nobody can see
# Occluders: only fixed, non-glass parts. Faces of detachable parts are never removed.
def fib_sphere(n, radius, center):
    pts = []
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        rad = math.sqrt(1 - y * y)
        pts.append(center + Vector((math.cos(ga * i) * rad, math.sin(ga * i) * rad, y)) * radius)
    return pts


views = fib_sphere(160, 9.0, Vector((0, 0, 0.6)))
views += [Vector(v) for v in [(0.37, 0.10, 1.12), (-0.37, 0.10, 1.12), (0.0, 0.2, 1.1),
                              (0.37, 0.95, 1.10), (-0.37, 0.95, 1.10), (0.0, 0.95, 1.1)]]
V = np.array([tuple(v) for v in views])


def is_glassy(o):
    return any(m and (m.name in GLASS_MATS or "Glass" in m.name) for m in o.data.materials)


fixed = [(o, g) for o, r, g in parts if g not in DETACHABLE and not g.startswith("Glass_") and not is_glassy(o)]
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
            for s_ in samples:
                d = V - np.array(tuple(s_))
                dots = d @ np.array(tuple(n))
                order_ = np.argsort(-dots)
                origin = s_ + n * 0.002
                for k in order_:
                    if dots[k] <= 0:
                        break
                    dirv = views[k] - origin
                    dist = dirv.length
                    hit = occ.ray_cast(origin, dirv / dist, dist)
                    if hit[0] is None:
                        seen = True
                        break
                if seen:
                    break
            if not seen:
                hidden.append(p.index)
        delete_faces(o, hidden)
        culled_total += len(hidden)
log["hidden_faces_removed"] = culled_total
print("hidden faces removed:", culled_total)

# =============================================================== 6. join per group, chunk, split per material/size
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
    drop_loose(bm)
    for f in bm.faces:
        f.material_index = 0
    bm.to_mesh(nm)
    bm.free()
    nm.materials.clear()
    nm.materials.append(mat)
    nm.validate(clean_customdata=False)
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


def planar_axes(me):
    n = sum((p.normal * p.area for p in me.polygons), Vector())
    n = n.normalized() if n.length > 1e-6 else Vector((0, 0, 1))
    up = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((0, 1, 0))
    u_ax = up.cross(n).normalized()
    v_ax = n.cross(u_ax).normalized()
    return u_ax, v_ax


def crack_uv_layer(me):
    """Planar map of the whole window into a 'CrackUV' layer, used by the cracked twins."""
    u_ax, v_ax = planar_axes(me)
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
    """Voronoi chunks on the surface: area-weighted seeds, Lloyd relaxation, nearest seed."""
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

# =============================================================== 7. cracked glass twins
def make_crack_image(size=1024, seed=7):
    """Spiderweb cracks: white jagged lines on a faint transparent tint (RGBA, alpha = crack)."""
    rng = np.random.default_rng(seed)
    a = np.zeros((size, size, 4), dtype=np.float32)
    a[:, :, :3] = 0.85
    a[:, :, 3] = 0.10
    sc = size / 1024

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
        steps = int(length / (18 * sc)) + 2
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
            stamp(c[0] + rng.normal(0, 7 * sc), c[1] + rng.normal(0, 7 * sc), 2, 0.95)
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

# =============================================================== 8. pivots + hierarchy
for no in final:
    g = no["group"]
    if g in hubs:
        c = hubs[g]
    else:
        lo, hi = bounds([v.co for v in no.data.vertices])
        c = (lo + hi) / 2
    no.data.transform(Matrix.Translation(-c))
    no.location = c

group_empty = {}
for g in sorted({no["group"] for no in final}):
    e = bpy.data.objects.new(g, None)
    scene.collection.objects.link(e)
    e.location = hubs.get(g, Vector((0, 0, 0)))
    group_empty[g] = e
for no in final:
    e = group_empty[no["group"]]
    wl = no.location.copy()
    no.parent = e
    no.matrix_parent_inverse = Matrix.Identity(4)
    no.location = wl - e.location

# =============================================================== 9. textures + export + report
for img in list(bpy.data.images):
    if img.users == 0:
        bpy.data.images.remove(img)
for img in bpy.data.images:
    w, h = img.size
    if max(w, h) > TEX_MAX:
        s = TEX_MAX / max(w, h)
        img.scale(max(1, int(w * s)), max(1, int(h * s)))

for no in sorted(final, key=lambda o: o.name):
    log["parts"].append({"name": no.name, "group": no["group"], "chunk": int(no["chunk"]),
                         "dmg": bool(no["dmg"]), "tris": tris(no)})
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
log["materials_per_part_ok"] = all(len(no.data.materials) == 1 for no in final)
json.dump(log, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1)
print("visible tris:", log["visible_tris"], "dmg tris:", log["dmg_tris"], "parts:", log["part_count"],
      "max part:", log["max_part_tris"])
for g, G in sorted(log["groups"].items()):
    print(f"  {g}: tris {G['tris']} parts {G['parts']} chunks {G['chunks']}")

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, NAME + ".blend"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), export_format='GLB',
                          export_yup=True, export_apply=True)
