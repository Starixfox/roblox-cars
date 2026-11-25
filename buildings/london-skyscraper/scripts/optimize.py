"""Optimize the One Blackfriars FBX for Roblox (real scale).
Writes roblox/LondonSkyscraper.glb, roblox/LondonSkyscraper_optimized.blend, roblox/report.json, roblox/textures/*.
Arg: "nodissolve" to skip the limited-dissolve step."""
import bpy, bmesh, os, sys, json, math
import numpy as np
from mathutils import Vector

ROOT = r"C:\Users\jordan\RobloxCars\buildings\london-skyscraper"
SRC = os.path.join(ROOT, "extracted", "London, One Blackfriars Skyscraper")
FBX = os.path.join(SRC, "SOURCE", "One_Blackfairs_Skyscraper.fbx")
OUT = os.path.join(ROOT, "roblox")
TEX_OUT = os.path.join(OUT, "textures")
os.makedirs(TEX_OUT, exist_ok=True)
DO_DISSOLVE = "nodissolve" not in sys.argv
MAX_TRIS = 19000
MAX_TEX = 1024

MAT_NAMES = {
    "Building_Facade": "FACADE", "Building_Elements_Trim": "TRIM", "Building_Maintenance_Unit": "BMU",
    "Color_Pallete": "PALETTE", "Concrete_Pillar": "CONCRETE", "Flare_Red": "FLARE_RED",
    "Furniture": "FURNITURE", "Glass_Generic": "GLASS", "Glass_Generic_More_Opaque": "GLASS_OPAQUE",
    "Glass_Lobby": "GLASS_LOBBY", "Glass_Railing": "GLASS_RAILING", "Interior_Blinds": "BLINDS",
    "Interior_Top": "INTERIOR", "Lobby_Curtains": "LOBBY_CURTAINS", "Lobby_Floor": "LOBBY_FLOOR",
    "Lobby_Furniture": "LOBBY_FURNITURE", "Lobby_Interior_1": "LOBBY_INTERIOR",
    "Sidewalk_01": "SIDEWALK_01", "Sidewalk_02": "SIDEWALK_02", "Top_Piece": "TOP_PIECE",
}
# glass had only a placeholder purple Kd in the export; use a neutral dark blue-grey tint
GLASS = {"GLASS": 0.35, "GLASS_OPAQUE": 0.6, "GLASS_LOBBY": 0.25, "GLASS_RAILING": 0.3}
GLASS_RGB = (0.10, 0.13, 0.16)

report = {"steps": {}, "textures": {}, "objects": [], "notes": []}


def tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def scene_tris():
    return sum(tri_count(o.data) for o in bpy.context.scene.objects if o.type == 'MESH')


# ---------------------------------------------------------------- import
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX)
report["steps"]["imported_tris"] = scene_tris()
print("imported tris", report["steps"]["imported_tris"])

# relink textures by file name
index = {}
for dp, dn, fn in os.walk(os.path.join(SRC, "TEXTURES")):
    for f in fn:
        index[f.lower()] = os.path.join(dp, f)
missing = []
for im in bpy.data.images:
    base = os.path.basename(im.filepath.replace("\\", "/")).lower()
    cand = index.get(base) or index.get(os.path.splitext(base)[0] + ".jpg") or index.get(os.path.splitext(base)[0] + ".jpeg")
    if cand:
        im.filepath = cand
        im.reload()
    else:
        missing.append(im.filepath)
report["missing_textures"] = missing
print("missing textures:", missing)

# apply transforms
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in bpy.context.scene.objects:
    o.select_set(o.type == 'MESH')
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for o in list(bpy.context.scene.objects):
    if o.type != 'MESH':
        bpy.data.objects.remove(o)


# ---------------------------------------------------------------- textures
def load_px(img, w, h):
    """Return float array (h, w, 4) of img scaled to w x h (raw stored values)."""
    c = img.copy()
    if tuple(c.size) != (w, h):
        c.scale(w, h)
    a = np.empty(w * h * 4, dtype=np.float32)
    c.pixels.foreach_get(a)
    bpy.data.images.remove(c)
    return a.reshape(h, w, 4)


def target_size(*imgs):
    w = max(i.size[0] for i in imgs)
    h = max(i.size[1] for i in imgs)
    s = min(1.0, MAX_TEX / max(w, h))
    return max(1, int(round(w * s))), max(1, int(round(h * s)))


def save_img(name, arr, alpha, noncolor, fmt):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=alpha)
    img.pixels.foreach_set(arr.astype(np.float32).ravel())
    ext = ".png" if fmt == 'PNG' else ".jpg"
    path = os.path.join(TEX_OUT, name + ext)
    img.filepath_raw = path
    img.file_format = fmt
    sc = bpy.context.scene
    sc.render.image_settings.quality = 92
    img.save(filepath=path, quality=92) if fmt == 'JPEG' else img.save()
    img.colorspace_settings.name = 'Non-Color' if noncolor else 'sRGB'
    report["textures"][name + ext] = [w, h]
    return img


def linked_tex(bsdf, sock):
    s = bsdf.inputs[sock]
    if not s.is_linked:
        return None, None
    l = s.links[0]
    n = l.from_node
    if n.type == 'TEX_IMAGE' and n.image:
        return n.image, l.from_socket.name
    if n.type == 'NORMAL_MAP':
        c = n.inputs["Color"]
        if c.is_linked and c.links[0].from_node.type == 'TEX_IMAGE':
            return c.links[0].from_node.image, "Color"
    return None, None


def lum(px):
    return px[..., 0] * 0.2126 + px[..., 1] * 0.7152 + px[..., 2] * 0.0722


def build_material(old):
    key = MAT_NAMES.get(old.name, old.name.upper())
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    outn = nt.nodes["Material Output"]
    info = {"name": key, "source": old.name, "maps": {}, "emissive": None, "alpha": False}

    if key in GLASS:
        a = GLASS[key]
        arr = np.zeros((8, 8, 4), np.float32)
        arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3] = GLASS_RGB[0], GLASS_RGB[1], GLASS_RGB[2], a
        img = save_img(key + "_BaseColor", arr, True, False, 'PNG')
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.location = (-500, 300)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
        bsdf.inputs["Roughness"].default_value = 0.05
        bsdf.inputs["Metallic"].default_value = 0.0
        m.surface_render_method = 'BLENDED'
        info["maps"]["base"] = img.name
        info["alpha"] = True
        return m, info

    obsdf = next(n for n in old.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    dif, _ = linked_tex(obsdf, "Base Color")
    alp, alp_sock = linked_tex(obsdf, "Alpha")
    nor, _ = linked_tex(obsdf, "Normal")
    rou, _ = linked_tex(obsdf, "Roughness")
    met, _ = linked_tex(obsdf, "Metallic")
    emi, _ = linked_tex(obsdf, "Emission Color")
    rough_def = obsdf.inputs["Roughness"].default_value
    met_def = obsdf.inputs["Metallic"].default_value

    # base color (+ alpha)
    w, h = target_size(*(i for i in (dif, alp) if i))
    base = load_px(dif, w, h)
    if alp:
        ap = load_px(alp, w, h)
        a = ap[..., 3] if alp_sock == "Alpha" else lum(ap)
        base[..., 3] = a
        info["alpha"] = True
        img = save_img(key + "_BaseColor", base, True, False, 'PNG')
    else:
        base[..., 3] = 1.0
        img = save_img(key + "_BaseColor", base, False, False, 'JPEG')
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.location = (-600, 400)
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if alp:
        nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
        m.surface_render_method = 'DITHERED'
    info["maps"]["base"] = img.name

    # metallic / roughness packed (G = roughness, B = metallic)
    if rou or met:
        w, h = target_size(*(i for i in (rou, met) if i))
        arr = np.ones((h, w, 4), np.float32)
        arr[..., 0] = 1.0
        arr[..., 1] = lum(load_px(rou, w, h)) if rou else rough_def
        arr[..., 2] = lum(load_px(met, w, h)) if met else met_def
        img = save_img(key + "_MetalRough", arr, False, True, 'PNG')
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.location = (-800, 0)
        sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (-450, 0)
        nt.links.new(t.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        info["maps"]["metalrough"] = img.name
    else:
        bsdf.inputs["Roughness"].default_value = rough_def
        bsdf.inputs["Metallic"].default_value = met_def

    if nor:
        w, h = target_size(nor)
        arr = load_px(nor, w, h); arr[..., 3] = 1.0
        img = save_img(key + "_Normal", arr, False, True, 'PNG')
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.location = (-800, -300)
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.location = (-450, -300)
        nt.links.new(t.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        info["maps"]["normal"] = img.name

    if emi:
        w, h = target_size(emi)
        arr = load_px(emi, w, h); arr[..., 3] = 1.0
        img = save_img(key + "_Emissive", arr, False, False, 'JPEG')
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.location = (-800, -600)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 1.0
        info["maps"]["emissive"] = img.name
        info["emissive"] = img
    return m, info


new_mats = {}
mat_info = {}
for old in list(bpy.data.materials):
    if old.users == 0 or old.name not in MAT_NAMES:
        continue
    m, info = build_material(old)
    new_mats[old.name] = m
    mat_info[m.name] = info
    print("material", old.name, "->", m.name, info["maps"])

# ---------------------------------------------------------------- join by material
groups = {}
for o in [o for o in bpy.context.scene.objects if o.type == 'MESH']:
    mats = [s.material for s in o.material_slots if s.material]
    if len(mats) != 1:
        report["notes"].append(f"object {o.name} has {len(mats)} materials")
    groups.setdefault(mats[0].name, []).append(o)

joined = {}
for oldname, objs in groups.items():
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    key = new_mats[oldname].name
    ob.name = key
    ob.data.name = key
    ob.data.materials.clear()
    ob.data.materials.append(new_mats[oldname])
    for p in ob.data.polygons:
        p.material_index = 0
    joined[key] = ob

for old in list(bpy.data.materials):
    if old.name in MAT_NAMES:
        bpy.data.materials.remove(old)

# ---------------------------------------------------------------- cleanup
clean = {}
for key, ob in joined.items():
    me = ob.data
    t0 = tri_count(me)
    bm = bmesh.new()
    bm.from_mesh(me)
    v0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    merged = v0 - len(bm.verts)
    # zero-area faces / zero-length edges
    bmesh.ops.dissolve_degenerate(bm, dist=0.00001, edges=bm.edges)
    # exact duplicate faces (same verts in the same winding); reversed twins are kept (double sided)
    seen = set(); dup = []
    bm.verts.index_update()
    for f in bm.faces:
        ids = [v.index for v in f.verts]
        k =min(tuple(ids[i:] + ids[:i]) for i in range(len(ids)))
        if k in seen:
            dup.append(f)
        else:
            seen.add(k)
    if dup:
        bmesh.ops.delete(bm, geom=dup, context='FACES_ONLY')
    loose_v = [v for v in bm.verts if not v.link_faces]
    loose_e = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=loose_e, context='EDGES')
    loose_v = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
    t1 = sum(len(f.verts) - 2 for f in bm.faces)
    t2 = t1
    if DO_DISSOLVE and key not in ("PALETTE",):
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), use_dissolve_boundaries=False,
                                 verts=bm.verts, edges=bm.edges,
                                 delimit={'NORMAL', 'MATERIAL', 'SEAM', 'SHARP', 'UV'})
        t2 = sum(len(f.verts) - 2 for f in bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    clean[key] = {"before": t0, "after_cleanup": t1, "after_dissolve": t2, "merged_verts": merged,
                  "dup_faces": len(dup), "loose_verts": len(loose_v), "loose_edges": len(loose_e)}
    print("clean", key, clean[key])
report["steps"]["cleanup"] = clean
report["steps"]["after_cleanup_tris"] = scene_tris()

# ---------------------------------------------------------------- origin: base center to world origin, ground Z=0
allv = []
for ob in joined.values():
    a = np.empty(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", a)
    allv.append(a.reshape(-1, 3))
allv = np.concatenate(allv)
mn, mx = allv.min(0), allv.max(0)
sw = []
for k in ("SIDEWALK_01", "SIDEWALK_02"):
    if k in joined:
        a = np.empty(len(joined[k].data.vertices) * 3, np.float32)
        joined[k].data.vertices.foreach_get("co", a)
        sw.append(a.reshape(-1, 3)[:, 2].max())
ground = max(sw) if sw else mn[2]
shift = Vector((-(mn[0] + mx[0]) / 2, -(mn[1] + mx[1]) / 2, -ground))
for ob in joined.values():
    ob.data.transform(__import__("mathutils").Matrix.Translation(shift))
    ob.data.update()
report["origin_shift_m"] = list(shift)
report["ground_note"] = "Z=0 is the top of the sidewalk; lowest geometry (lobby slab) is %.2f m below it" % (ground - mn[2])
report["size_m"] = [float(mx[0] - mn[0]), float(mx[1] - mn[1]), float(mx[2] - mn[2])]
print("size m", report["size_m"], "shift", list(shift))

# ---------------------------------------------------------------- spatial split
PODIUM_TOP = 12.0
CROWN_BOTTOM = 153.0
BANDS = [PODIUM_TOP, 40.0, 68.0, 96.0, 124.0, CROWN_BOTTOM]


def section_of(z):
    if z < PODIUM_TOP:
        return "Podium"
    if z >= CROWN_BOTTOM:
        return "Crown"
    for i in range(len(BANDS) - 1):
        if BANDS[i] <= z < BANDS[i + 1]:
            return "Tower_Band%02d" % (i + 1)
    return "Tower"


def extract(src_me, face_ids, name, mat):
    bm = bmesh.new()
    bm.from_mesh(src_me)
    bm.faces.ensure_lookup_table()
    keep = set(face_ids)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context='FACES')
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    for p in me.polygons:
        p.material_index = 0
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def split_faces(fids, zs, tris):
    """Split a face list into chunks <= MAX_TRIS by median Z."""
    if sum(tris[i] for i in fids) <= MAX_TRIS:
        return [fids]
    order = sorted(fids, key=lambda i: zs[i])
    acc, half, tot = 0, None, sum(tris[i] for i in fids)
    for n, i in enumerate(order):
        acc += tris[i]
        if acc >= tot / 2:
            half = n + 1
            break
    return split_faces(order[:half], zs, tris) + split_faces(order[half:], zs, tris)


parts = []
for key, ob in list(joined.items()):
    me = ob.data
    mat = me.materials[0]
    n = len(me.polygons)
    zs = np.empty(n * 3, np.float32); me.polygons.foreach_get("center", zs); zs = zs.reshape(-1, 3)[:, 2]
    tris = [len(p.vertices) - 2 for p in me.polygons]
    total = sum(tris)
    if total <= 4000:
        zmin = min(v.co.z for v in me.vertices); zmax = max(v.co.z for v in me.vertices)
        if zmax < PODIUM_TOP + 1:
            sec = "Podium"
        elif zmin >= CROWN_BOTTOM - 5:
            sec = "Crown"
        else:
            sec = "Tower"
        buckets = {sec: list(range(n))}
    else:
        buckets = {}
        for i in range(n):
            buckets.setdefault(section_of(float(zs[i])), []).append(i)
    for sec, fids in sorted(buckets.items()):
        chunks = split_faces(fids, zs, tris)
        for ci, ch in enumerate(chunks):
            name = f"{sec}__{key}" + (f"_{ci + 1}" if len(chunks) > 1 else "")
            p = extract(me, ch, name, mat)
            parts.append(p)
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)

# ---------------------------------------------------------------- night windows set
night_mats = {}
for key, info in mat_info.items():
    if info["emissive"] is None:
        continue
    m = bpy.data.materials.new(key + "_NIGHT")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = info["emissive"]
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(t.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 1.0
    if info["alpha"]:
        bt = nt.nodes.new("ShaderNodeTexImage"); bt.image = bpy.data.images[info["maps"]["base"]]
        nt.links.new(bt.outputs["Alpha"], bsdf.inputs["Alpha"])
        m.surface_render_method = 'DITHERED'
    night_mats[key] = m

night_parts = []
for p in list(parts):
    key = p.data.materials[0].name
    if key in night_mats:
        me = p.data.copy()
        me.materials.clear(); me.materials.append(night_mats[key])
        name = "NightWindows_" + p.name.replace("__", "__", 1) + "_NIGHT"
        no = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(no)
        night_parts.append(no)

# ---------------------------------------------------------------- hierarchy and origins
root = bpy.data.objects.new("LondonSkyscraper", None)
bpy.context.scene.collection.objects.link(root)
day = bpy.data.objects.new("Building", None); day.parent = root
night = bpy.data.objects.new("NightWindows", None); night.parent = root
bpy.context.scene.collection.objects.link(day)
bpy.context.scene.collection.objects.link(night)
for p in parts + night_parts:
    me = p.data
    a = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", a); a = a.reshape(-1, 3)
    c = Vector(((a.min(0) + a.max(0)) / 2).tolist())
    me.transform(__import__("mathutils").Matrix.Translation(-c))
    p.location = c
    p.parent = night if p in night_parts else day
    # make tags easy to read in report
    rec = {"name": p.name, "tris": tri_count(me), "material": me.materials[0].name,
           "set": "night" if p in night_parts else "day",
           "textures": {k: report["textures"].get(v + (".png" if (os.path.exists(os.path.join(TEX_OUT, v + ".png"))) else ".jpg"))
                        for k, v in mat_info.get(me.materials[0].name.replace("_NIGHT", ""), {"maps": {}})["maps"].items()}}
    report["objects"].append(rec)

day_tris = sum(r["tris"] for r in report["objects"] if r["set"] == "day")
night_tris = sum(r["tris"] for r in report["objects"] if r["set"] == "night")
report["totals"] = {
    "source_tris": report["steps"]["imported_tris"],
    "day_tris": day_tris, "night_tris": night_tris, "all_tris": day_tris + night_tris,
    "day_parts": sum(1 for r in report["objects"] if r["set"] == "day"),
    "night_parts": sum(1 for r in report["objects"] if r["set"] == "night"),
    "max_part_tris": max(r["tris"] for r in report["objects"]),
    "materials": len(mat_info), "night_materials": len(night_mats), "texture_files": len(report["textures"]),
}
print("TOTALS", report["totals"])

# ---------------------------------------------------------------- export
glb = os.path.join(OUT, "LondonSkyscraper.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', export_yup=True, export_apply=True,
                          export_image_format='AUTO', export_materials='EXPORT', export_texcoords=True,
                          export_normals=True, export_tangents=False, export_extras=False,
                          export_cameras=False, export_lights=False, export_animations=False)
report["glb_bytes"] = os.path.getsize(glb)
for im in list(bpy.data.images):
    if im.users == 0:
        bpy.data.images.remove(im)
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "LondonSkyscraper_optimized.blend"), compress=True)
with open(os.path.join(OUT, "report.json"), "w") as f:
    json.dump(report, f, indent=1)
print("glb MB", report["glb_bytes"] / 1e6)
