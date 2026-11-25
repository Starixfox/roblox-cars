"""Prepare the Porsche 911 GT3 RS Weissach (Sketchfab, VTDAT23, CC BY) for Roblox.

Steps: remove brand logos/decals, simplify the car by part group,
split into single-material pieces under Roblox's per-mesh triangle limit,
put each wheel's pivot at its center, shrink textures to 1024 and
export GLB + FBX + a .blend for later tweaks.
"""
import bpy, bmesh, os, json, math
from mathutils import Vector, Matrix

ROOT = r"C:\Users\jordan\RobloxCars\porsche-gt3rs"
GLB = os.path.join(ROOT, "source", "source", "Porsche_GT3RS_MOD.glb")
OUT = os.path.join(ROOT, "roblox")
NAME = "GT3RS_Roblox"
MAX_TRIS = 19000          # Roblox limit is ~20k per MeshPart; keep margin
TEX_MAX = 1024            # Roblox shrinks textures to 1024 anyway
SMOOTH_ANGLE = math.radians(35)

# Triangle budget per group (whole car ~89k)
BUDGET = {
    "Body": 42000,
    "Interior": 18000,
    "SteeringWheel": 2500,
    "Glass": 6000,
    "Lights": 4000,
    "Brakes": 3000,
    "Wheel_LF": 7000, "Wheel_RF": 7000, "Wheel_LR": 7000, "Wheel_RR": 7000,
}

# Brand logos / lettering to remove (by material) plus the front badge surround
DELETE_MATS = {
    "EXT_BADGE_PORSCHE",   # hood crest + steering wheel crest
    "EXT_DECAL_REAR",      # GT3 RS rear lettering
    "EXT_Logo_Weissach",   # Weissach wing logo
    "int_Decal_Paint",     # Weissach interior logo
    "EXT_DECAL_2",         # PORSCHE decals
    "ext_Decal_Paint",     # side decals
    "INT_DECALS",          # interior Porsche decals
    "INT_GPS",             # Porsche screen
}
DELETE_OBJS = {"EXT_PLASTIC_GLOSS_2"}  # badge surround on the nose
# Logos modelled into bigger meshes: (object, world-space box) -> delete faces inside
DELETE_REGIONS = [
    ("EXT_CHROME_0", (-0.30, 0.30), (2.13, 2.20), (0.68, 0.712)),         # rear PORSCHE letters
    ("EXT_PLASTIC_GLOSS_0", (-0.275, 0.275), (2.13, 2.20), (0.68, 0.712)),  # their black base
]

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
scene = bpy.context.scene


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def meshes():
    return [o for o in scene.objects if o.type == 'MESH']


def override(o):
    return bpy.context.temp_override(object=o, active_object=o,
                                     selected_objects=[o], selected_editable_objects=[o])


def world_center(o):
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return sum(bb, Vector()) / 8


log = {"removed": [], "groups": {}, "parts": []}
print("start tris:", sum(tris(o) for o in meshes()))

# ---------------------------------------------------------------- 1. logos
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
    kill = [f for f in bm.faces
            if x0 < (mw @ f.calc_center_median()).x < x1
            and y0 < (mw @ f.calc_center_median()).y < y1
            and z0 < (mw @ f.calc_center_median()).z < z1]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data)
    bm.free()
    log["removed"].append(f"{name}: {len(kill)} faces (region)")

# Wheel center caps carry the Porsche crest: make them plain dark metal
cap = bpy.data.materials.get("EXT_RIM_CAP")
if cap and cap.node_tree:
    nt = cap.node_tree
    for n in [n for n in nt.nodes if n.type in ('TEX_IMAGE', 'NORMAL_MAP')]:
        nt.nodes.remove(n)
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.03, 0.03, 0.03, 1)
        bsdf.inputs["Metallic"].default_value = 0.9
        bsdf.inputs["Roughness"].default_value = 0.3

# Car paint uses a tiny tiled 4k flake normal map Roblox can't tile: drop it
paint = bpy.data.materials.get("CarPaint_flake")
if paint and paint.node_tree:
    nt = paint.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        for l in list(bsdf.inputs["Normal"].links):
            nt.links.remove(l)
    for n in [n for n in nt.nodes if n.type in ('TEX_IMAGE', 'NORMAL_MAP')]:
        if not n.outputs[0].links or n.type == 'NORMAL_MAP':
            nt.nodes.remove(n)
    for n in [n for n in nt.nodes if n.type == 'TEX_IMAGE' and not n.outputs[0].links]:
        nt.nodes.remove(n)

# ---------------------------------------------------------------- 2. groups
def classify(o):
    n = o.name
    mats = " ".join(m.name for m in o.data.materials if m)
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
            return "Wheel_" + ("L" if c.x > 0 else "R") + ("F" if c.y < 0 else "R")
        if pn.startswith("SUSP_"):
            return "Brakes"
        if pn.startswith(("COCKPIT_HR", "ARROW_")):
            return "Body" if n.startswith("EXT_") else "Interior"
        p = p.parent
    return "Body"


groups = {}
for o in meshes():
    groups.setdefault(classify(o), []).append(o)

# Wheel pivots: center of each wheel (taken from the tyre/rim bounds)
wheel_centers = {}
for g, objs in groups.items():
    if g.startswith("Wheel_"):
        pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
        mn = Vector([min(p[i] for p in pts) for i in range(3)])
        mx = Vector([max(p[i] for p in pts) for i in range(3)])
        wheel_centers[g] = (mn + mx) / 2

# ---------------------------------------------------------------- 3. bake transforms, clean
# Record every world matrix first: some meshes are parents of other meshes,
# so resetting one before reading its children would move the children.
world = {o.name: o.matrix_world.copy() for o in meshes()}
hi_src = {}   # untouched high-poly copy per object: source for smooth normals
for o in list(meshes()):
    mw = world[o.name]
    o.parent = None
    o.data = o.data.copy()          # break instancing so edits are per object
    o.data.transform(mw)
    o.matrix_world = Matrix.Identity(4)
    me = o.data
    hi = bpy.data.objects.new("HI_" + o.name, me.copy())
    scene.collection.objects.link(hi)
    hi.hide_render = True
    hi_src[o.name] = hi
    vs = [v.co for v in me.vertices]
    o["lo"] = [min(v[i] for v in vs) for i in range(3)] if vs else [0, 0, 0]
    o["hi"] = [max(v[i] for v in vs) for i in range(3)] if vs else [0, 0, 0]
    if me.has_custom_normals:
        with override(o):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00005)
    bm.to_mesh(me)
    bm.free()

for o in [o for o in scene.objects if o.type == 'EMPTY']:
    bpy.data.objects.remove(o, do_unlink=True)

# ---------------------------------------------------------------- 4. simplify per group
# Visible surfaces keep more detail: paint panels most, then glass/lights/chrome
def weight(o):
    mats = " ".join(m.name for m in o.data.materials if m)
    if "CarPaint" in mats or "Body_Paint" in mats:
        return 6.0
    if any(k in mats for k in ("GLASS", "WINDOW", "CHROME", "Headlight", "HL_")):
        return 2.0
    return 1.0


def target_tris(t, w, r, floor=150):
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
for g, objs in groups.items():
    before = sum(tris(o) for o in objs)
    r = ratio_for(objs, BUDGET[g])
    for o in objs:
        t = tris(o)
        target = target_tris(t, weight(o), r)
        rr = target / t if t else 1
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
            # Drop faces with vertices flung outside the original part bounds
            m = 0.02
            lo, hi_ = Vector(o["lo"]) - Vector((m,) * 3), Vector(o["hi"]) + Vector((m,) * 3)
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bad = [v for v in bm.verts if any(not (lo[i] <= v.co[i] <= hi_[i]) for i in range(3))]
            if bad:
                print(f"  {o.name}: removed {len(bad)} stray vertices")
                bmesh.ops.delete(bm, geom=bad, context='VERTS')
                bm.to_mesh(o.data)
            bm.free()
        o.data.shade_smooth()
        o.data.set_sharp_from_angle(angle=SMOOTH_ANGLE)
    after = sum(tris(o) for o in objs)
    log["groups"][g] = {"before": before, "after": after, "objects": len(objs)}
    print(f"{g}: {before} -> {after}")

for hi in hi_src.values():
    me = hi.data
    bpy.data.objects.remove(hi, do_unlink=True)
    if me.users == 0:
        bpy.data.meshes.remove(me)

# ---------------------------------------------------------------- 5. join, split by material and size
def faces_subset(o, face_ids, name, mat):
    nm = o.data.copy()
    keep = set(face_ids)
    bm = bmesh.new()
    bm.from_mesh(nm)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context='FACES')
    for f in bm.faces:
        f.material_index = 0
    bm.to_mesh(nm)
    bm.free()
    nm.materials.clear()
    nm.materials.append(mat)
    no = bpy.data.objects.new(name, nm)
    nm.name = name
    scene.collection.objects.link(no)
    return no


def spatial_chunks(me, fids, maxt):
    """Recursively halve a face set along its longest axis until each part fits."""
    t = sum(len(me.polygons[i].vertices) - 2 for i in fids)
    if t <= maxt:
        return [fids]
    cs = [(i, me.polygons[i].center) for i in fids]
    ax = max(range(3), key=lambda a: max(c[a] for _, c in cs) - min(c[a] for _, c in cs))
    cs.sort(key=lambda ic: ic[1][ax])
    h = len(cs) // 2
    return (spatial_chunks(me, [i for i, _ in cs[:h]], maxt) +
            spatial_chunks(me, [i for i, _ in cs[h:]], maxt))


def islands(me, fids):
    fset = set(fids)
    edge_faces = {}
    for i in fids:
        for ek in me.polygons[i].edge_keys:
            edge_faces.setdefault(ek, []).append(i)
    seen, out = set(), []
    for i in fids:
        if i in seen:
            continue
        stack, isl = [i], []
        seen.add(i)
        while stack:
            f = stack.pop()
            isl.append(f)
            for ek in me.polygons[f].edge_keys:
                for h in edge_faces[ek]:
                    if h not in seen and h in fset:
                        seen.add(h)
                        stack.append(h)
        out.append(isl)
    return out


def pack(me, fids, maxt):
    """Group whole connected pieces into bins under maxt; oversized pieces are cut."""
    tri = lambda ids: sum(len(me.polygons[i].vertices) - 2 for i in ids)
    pieces = []
    for isl in islands(me, fids):
        pieces += spatial_chunks(me, isl, maxt) if tri(isl) > maxt else [isl]
    pieces.sort(key=lambda p: -tri(p))
    bins = []
    for p in pieces:
        tp = tri(p)
        for b in bins:
            if b[0] + tp <= maxt:
                b[0] += tp
                b[1].extend(p)
                break
        else:
            bins.append([tp, list(p)])
    return [b[1] for b in bins]


def safe(s):
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_")


final = []
for g, objs in groups.items():
    objs = [o for o in objs if o.name in scene.objects]
    if not objs:
        continue
    with bpy.context.temp_override(active_object=objs[0], object=objs[0],
                                   selected_objects=objs, selected_editable_objects=objs):
        bpy.ops.object.join()
    j = objs[0]
    me = j.data
    by_mat = {}
    for p in me.polygons:
        by_mat.setdefault(p.material_index, []).append(p.index)
    for mi, fids in by_mat.items():
        mat = me.materials[mi] if mi < len(me.materials) else None
        chunks = pack(me, fids, MAX_TRIS)
        for k, ch in enumerate(chunks):
            nm = f"{g}_{safe(mat.name) if mat else 'NoMat'}" + (f"_{k + 1}" if len(chunks) > 1 else "")
            no = faces_subset(j, ch, nm, mat)
            no["group"] = g
            final.append(no)
    bpy.data.objects.remove(j, do_unlink=True)

# ---------------------------------------------------------------- 6. pivots + hierarchy
for no in final:
    g = no["group"]
    if g in wheel_centers:
        c = wheel_centers[g]
    else:
        # bound_box can be stale on freshly created objects: use vertices
        vs = [v.co for v in no.data.vertices]
        lo = Vector([min(v[i] for v in vs) for i in range(3)])
        hi = Vector([max(v[i] for v in vs) for i in range(3)])
        c = (lo + hi) / 2
    no.data.transform(Matrix.Translation(-c))
    no.location = c

bpy.context.view_layer.update()   # refresh matrix_world before parenting

for g in groups:
    e = bpy.data.objects.new(g, None)
    scene.collection.objects.link(e)
    if g in wheel_centers:
        e.location = wheel_centers[g]
    for no in final:
        if no["group"] == g:
            # no rotation/scale anywhere, so local = world location - parent location
            world_loc = no.location.copy()
            no.parent = e
            no.matrix_parent_inverse = Matrix.Identity(4)
            no.location = world_loc - e.location

# ---------------------------------------------------------------- 7. textures
used_imgs = set()
for no in final:
    for m in no.data.materials:
        if m and m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image:
                    used_imgs.add(n.image)
for img in used_imgs:
    w, h = img.size
    if max(w, h) > TEX_MAX:
        s = TEX_MAX / max(w, h)
        img.scale(max(1, int(w * s)), max(1, int(h * s)))
for img in list(bpy.data.images):
    if img.users == 0:
        bpy.data.images.remove(img)

# ---------------------------------------------------------------- 8. report + export
for no in sorted(final, key=lambda o: o.name):
    log["parts"].append({"name": no.name, "group": no["group"], "tris": tris(no),
                         "material": no.data.materials[0].name if no.data.materials[0] else None})
log["total_tris"] = sum(p["tris"] for p in log["parts"])
log["part_count"] = len(final)
log["parts_with_custom_normals"] = sum(1 for o in final if o.data.has_custom_normals)
log["max_part_tris"] = max(p["tris"] for p in log["parts"])
log["textures"] = sorted(f"{i.name} {i.size[0]}x{i.size[1]}" for i in used_imgs)
json.dump(log, open(os.path.join(OUT, NAME + "_report.json"), "w"), indent=1)
print("total tris:", log["total_tris"], "parts:", log["part_count"], "max part:", log["max_part_tris"])

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, NAME + ".blend"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, NAME + ".glb"), export_format='GLB',
                          export_yup=True, export_apply=True)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, NAME + ".fbx"), path_mode='COPY',
                         embed_textures=True, apply_scale_options='FBX_SCALE_UNITS',
                         axis_forward='-Z', axis_up='Y', bake_space_transform=True)
