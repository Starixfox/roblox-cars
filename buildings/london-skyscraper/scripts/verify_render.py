"""Re-import the exported GLB in a fresh scene, check it, and render previews.
Arg: optional comma list of shots (full,street,facade,lobby,office,night)."""
import bpy, os, sys, json, math, struct
from mathutils import Vector

ROOT = r"C:\Users\jordan\RobloxCars\buildings\london-skyscraper"
GLB = os.path.join(ROOT, "roblox", "LondonSkyscraper.glb")
PREV = os.path.join(ROOT, "previews")
os.makedirs(PREV, exist_ok=True)
only = sys.argv[1].split(",") if len(sys.argv) > 1 else None

# ------------------------------------------------ raw glTF JSON check
with open(GLB, "rb") as f:
    f.read(12)
    ln, typ = struct.unpack("<II", f.read(8))
    gj = json.loads(f.read(ln))
alpha_modes = {m["name"]: m.get("alphaMode", "OPAQUE") for m in gj["materials"]}
img_count = len(gj.get("images", []))

# ------------------------------------------------ import + stats
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
scene = bpy.context.scene
meshes = [o for o in scene.objects if o.type == 'MESH']
stats = {"objects": len(meshes), "parts": {}, "materials": {}, "problems": []}
for o in meshes:
    o.data.calc_loop_triangles()
    t = len(o.data.loop_triangles)
    stats["parts"][o.name] = t
    if len(o.data.materials) != 1:
        stats["problems"].append(f"{o.name}: {len(o.data.materials)} materials")
    if "__" not in o.name:
        stats["problems"].append(f"{o.name}: bad name")
for m in bpy.data.materials:
    imgs = [n.image for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image] if m.node_tree else []
    ok = bool(imgs) and all(i.has_data or i.size[0] > 0 for i in imgs)
    stats["materials"][m.name] = {"images": [f"{i.name} {i.size[0]}x{i.size[1]}" for i in imgs],
                                  "ok": ok, "alphaMode": alpha_modes.get(m.name)}
    if not ok:
        stats["problems"].append(f"material {m.name} has no loaded texture")
    for i in imgs:
        if max(i.size) > 1024:
            stats["problems"].append(f"image {i.name} > 1024")
stats["max_tris"] = max(stats["parts"].values())
stats["total_tris"] = sum(stats["parts"].values())
stats["gltf_images"] = img_count
mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
for o in meshes:
    for c in o.bound_box:
        v = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], v[i]); mx[i] = max(mx[i], v[i])
stats["bounds"] = [list(mn), list(mx)]
with open(os.path.join(PREV, "verify.json"), "w") as f:
    json.dump(stats, f, indent=1)
print("VERIFY objects", stats["objects"], "max", stats["max_tris"], "total", stats["total_tris"],
      "bounds", [round(x, 2) for x in mn], [round(x, 2) for x in mx], "problems", stats["problems"])
print("alpha modes", alpha_modes)

night_objs = [o for o in meshes if o.name.startswith("NightWindows_")]
day_objs = [o for o in meshes if not o.name.startswith("NightWindows_")]
night_counterpart = {o.name.replace("NightWindows_", "").replace("_NIGHT", "") for o in night_objs}

# ------------------------------------------------ scene setup
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
try:
    scene.eevee.taa_render_samples = 32
except Exception:
    pass
scene.view_settings.view_transform = 'AgX'
world = bpy.data.worlds.new("w"); scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")

bpy.ops.mesh.primitive_plane_add(size=3000, location=(0, 0, -0.03))
floor = bpy.context.active_object
fm = bpy.data.materials.new("ground"); fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.2, 0.2, 0.21, 1)
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
floor.data.materials.append(fm)

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
sun.rotation_euler = (math.radians(55), math.radians(10), math.radians(-35))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.clip_start = 0.05; cam.data.clip_end = 5000
scene.collection.objects.link(cam); scene.camera = cam

emit_nodes = [n for m in bpy.data.materials if m.node_tree for n in m.node_tree.nodes
              if n.type == 'BSDF_PRINCIPLED' and n.inputs["Emission Color"].is_linked]
temp_lights = []


def set_mode(mode):
    global temp_lights
    for l in temp_lights:
        bpy.data.objects.remove(l)
    temp_lights = []
    night = mode == "night"
    for o in night_objs:
        o.hide_render = not night
    for o in day_objs:
        o.hide_render = night and o.name in night_counterpart
    if night:
        bg.inputs[0].default_value = (0.02, 0.03, 0.06, 1); bg.inputs[1].default_value = 0.4
        sun.data.energy = 0.05
        es = 6.0
    elif mode == "interior":
        bg.inputs[0].default_value = (0.55, 0.6, 0.68, 1); bg.inputs[1].default_value = 1.2
        sun.data.energy = 3.0
        es = 2.0
    else:
        bg.inputs[0].default_value = (0.55, 0.6, 0.68, 1); bg.inputs[1].default_value = 1.0
        sun.data.energy = 3.5
        es = 1.0
    for n in emit_nodes:
        n.inputs["Emission Strength"].default_value = es


def add_light(loc, energy=800, size=3.0):
    l = bpy.data.objects.new("pl", bpy.data.lights.new("pl", 'POINT'))
    l.data.energy = energy; l.data.shadow_soft_size = size
    l.location = loc
    scene.collection.objects.link(l)
    temp_lights.append(l)


def shoot(name, loc, target, lens=50, portrait=False):
    if only and name not in only:
        return
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    scene.render.resolution_x, scene.render.resolution_y = (810, 1440) if portrait else (1280, 720)
    scene.render.filepath = os.path.join(PREV, f"tower_{name}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", name, tuple(round(x, 2) for x in loc), "->", tuple(round(x, 2) for x in target))


def cast(origin, direction, dist=1000):
    dg = bpy.context.evaluated_depsgraph_get()
    hit, loc, nor, idx, obj, _ = scene.ray_cast(dg, Vector(origin), Vector(direction).normalized(), distance=dist)
    return (loc, obj.name if obj else None) if hit else (None, None)


def best_view(pos, enclosed=False):
    best = None
    for k in range(24):
        a = 2 * math.pi * k / 24
        d = Vector((math.cos(a), math.sin(a), 0))
        loc, _ = cast(pos, d, 200)
        if loc is None and enclosed:
            return 0, d
        dist = (loc - Vector(pos)).length if loc else 200
        if best is None or dist > best[0]:
            best = (dist, d)
    return best


def obj_bounds(prefix):
    mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
    for o in meshes:
        if o.name.startswith(prefix):
            for c in o.bound_box:
                v = o.matrix_world @ Vector(c)
                for i in range(3):
                    mn[i] = min(mn[i], v[i]); mx[i] = max(mx[i], v[i])
    return mn, mx


H = mx.z
set_mode("day")
shoot("full", (210, -210, 80), (0, 0, H * 0.47), 50, portrait=True)
shoot("street", (30, -55, 1.7), (0, 0, 55), 18)
hit, hobj = cast((0, -200, 60), (0, 1, 0), 400)
print("facade hit", hit, hobj)
if hit:
    shoot("facade", (hit.x - 9, hit.y - 16, hit.z - 4), (hit.x, hit.y, hit.z + 1), 35)

# lobby: search inside the lobby furniture area for a free spot
set_mode("interior")
lmn, lmx = obj_bounds("Podium__LOBBY_FURNITURE")
print("lobby furniture bounds", list(lmn), list(lmx))
cand = None
fmn, fmx = obj_bounds("Podium__LOBBY_FLOOR")
print("lobby floor bounds", list(fmn), list(fmx))
lmn = Vector((min(lmn.x, fmn.x), min(lmn.y, fmn.y), 0)); lmx = Vector((max(lmx.x, fmx.x), max(lmx.y, fmx.y), 0))
for fx in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
    for fy in (0.5, 0.4, 0.6, 0.3, 0.7, 0.15, 0.85):
        x = lmn.x + (lmx.x - lmn.x) * fx; y = lmn.y + (lmx.y - lmn.y) * fy
        down, dobj = cast((x, y, 3.0), (0, 0, -1), 10)
        if down is None or not dobj.startswith("Podium__LOBBY"):
            continue
        p = Vector((x, y, down.z + 1.7))
        up, uobj = cast(p, (0, 0, 1), 30)
        if up is None or (up.z - p.z) < 0.5:
            continue
        dist, d = best_view(p, enclosed=True)
        if dist == 0:
            continue
        if cand is None or dist > cand[0]:
            cand = (dist, p, d, dobj, uobj)
print("lobby cand", cand)
if cand:
    dist, p, d, dobj, uobj = cand
    add_light(p + Vector((0, 0, 1.5)), 1500, 4)
    add_light(p + d * min(dist * 0.5, 10) + Vector((0, 0, 1.5)), 1500, 4)
    shoot("lobby", p - d * 0.5, p + d * 10 + Vector((0, 0, -0.3)), 18)

# office: find a floor inside the tower around 80 m
imn, imx = obj_bounds("Tower_Band03__INTERIOR")
c = (imn + imx) / 2
print("band03 interior bounds", list(imn), list(imx))
cand = None
for dx in (0, 0.25, -0.25):
    for dy in (0, 0.25, -0.25, 0.4, -0.4):
        x = c.x + (imx.x - imn.x) * dx; y = c.y + (imx.y - imn.y) * dy
        down, dobj = cast((x, y, 82.0), (0, 0, -1), 6)
        if down is None:
            continue
        p = Vector((x, y, down.z + 1.6))
        up, uobj = cast(p, (0, 0, 1), 6)
        if up is None or (up.z - p.z) < 0.4:
            continue
        dist, d = best_view(p)
        if cand is None or dist > cand[0]:
            cand = (dist, p, d, dobj, uobj, up.z - down.z)
print("office cand", cand)
if cand:
    dist, p, d, dobj, uobj, hgt = cand
    add_light(p + Vector((0, 0, 0.8)), 1500, 2)
    add_light(p + d * min(dist * 0.5, 8) + Vector((0, 0, 0.8)), 2500, 2)
    for n in emit_nodes:
        n.inputs["Emission Strength"].default_value = 5.0
    scene.view_settings.exposure = 1.3
    # stand near the far window and look back across the floor plate
    far = p + d * max(dist - 2.5, 0)
    shoot("office", far, p + Vector((0, 0, -0.2)), 16)
    scene.view_settings.exposure = 0.0

set_mode("night")
shoot("night", (210, -210, 80), (0, 0, H * 0.47), 50, portrait=True)
