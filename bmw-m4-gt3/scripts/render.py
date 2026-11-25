"""Render preview shots. Args: <model.glb|.fbx> <out_prefix> [normal|dmg|explode|chunkcolors|impact|remove:A+B] [shots,comma,separated]
A .fbx is the original source: it is imported at 1/100 scale and scaled x100 here."""
import bpy, sys, math
from mathutils import Vector

model, prefix = sys.argv[1], sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else "normal"
only = sys.argv[4].split(",") if len(sys.argv) > 4 else None

DETACH = ("Hood", "Trunk", "Door_L", "Door_R", "FrontBumper", "RearBumper", "Wing",
          "Mirror_L", "Mirror_R", "Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR", "Glass_Door_L", "Glass_Door_R")
# ride-along groups follow their parent's offset
PARENT = {"Mirror_L": "Door_L", "Mirror_R": "Door_R", "Glass_Door_L": "Door_L", "Glass_Door_R": "Door_R"}
ALL_DETACH = "Hood+Trunk+Door_L+Door_R+FrontBumper+RearBumper+Wing+Mirror_L+Mirror_R+Wheel_LF+Wheel_RF+Wheel_LR+Wheel_RR"
if mode == "remove:ALL":
    mode = "remove:" + ALL_DETACH

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
if model.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=model)
    root = bpy.data.objects.new("SCALE", None)
    scene.collection.objects.link(root)
    for o in list(scene.objects):
        if o.parent is None and o is not root:
            o.parent = root
    root.scale = (100, 100, 100)
    bpy.context.view_layer.update()
else:
    bpy.ops.import_scene.gltf(filepath=model)

if mode.startswith("only:") or mode.startswith("hide:"):
    # debug: show only / hide objects whose name contains any of the given substrings
    keys = mode.split(":", 1)[1].split("+")
    for o in scene.objects:
        if o.type == 'MESH':
            hit = any(k in o.name for k in keys)
            o.hide_render = (not hit) if mode.startswith("only:") else hit

is_split = any("__" in o.name for o in scene.objects)


def world_center(o):
    vs = o.data.vertices
    if not len(vs):
        return o.matrix_world.translation.copy()
    return o.matrix_world @ (sum((v.co for v in vs), Vector()) / len(vs))


if is_split:
    centers = {}
    for o in scene.objects:
        if o.type == 'MESH' and "__" in o.name:
            g = o.name.split("__")[0]
            dmg = "__DMG__" in o.name
            show = dmg if mode == "dmg" else not dmg
            if mode == "dmg" and not dmg:
                has_dmg = any(x.name.startswith(g + "__") and "__DMG__" in x.name for x in scene.objects)
                show = not has_dmg
            o.hide_render = not show
            if show:
                centers.setdefault(g, []).append(world_center(o))

    def chunk_key(o):
        s = o.name.split("__")
        return (s[0], s[1]) if len(s) >= 3 and s[1].startswith("C") and s[1][1:].isdigit() else None

    if mode in ("chunkcolors", "groupcolors"):
        import random
        rnd = random.Random(3)
        mats = {}
        for o in scene.objects:
            if o.type == 'MESH' and not o.hide_render:
                if mode == "groupcolors":
                    k = (o.name.split("__")[0], "")
                else:
                    k = chunk_key(o) or (o.name.split("__")[0], "")
                if k not in mats:
                    m = bpy.data.materials.new("chunk")
                    m.use_nodes = True
                    b = m.node_tree.nodes["Principled BSDF"]
                    b.inputs["Base Color"].default_value = (rnd.random(), rnd.random(), rnd.random(), 1)
                    mats[k] = m
                o.data.materials.clear()
                o.data.materials.append(mats[k])
    if mode == "impact":
        # simulated front-left crash + a hit on the windshield
        crash, crash_r = Vector((0.8, -2.25, 0.55)), 0.8
        glass_hit = Vector((0.25, -0.62, 1.03))
        chunk_cent = {}
        for o in scene.objects:
            if o.type == 'MESH' and "__DMG__" not in o.name and chunk_key(o):
                chunk_cent.setdefault(chunk_key(o), []).append(world_center(o))
        chunk_cent = {k: sum(v, Vector()) / len(v) for k, v in chunk_cent.items()}
        gone, cracked = set(), set()
        for k, c in chunk_cent.items():
            if k[0].startswith("Glass_Windshield"):
                d = (c - glass_hit).length
                if d < 0.22:
                    gone.add(k)
                elif d < 0.75:
                    cracked.add(k)
            elif not k[0].startswith("Glass_") and (c - crash).length < crash_r:
                gone.add(k)
        for o in scene.objects:
            if o.type != 'MESH' or "__" not in o.name:
                continue
            k = chunk_key(o)
            dmg = "__DMG__" in o.name
            if k is None:
                continue
            if k in gone:
                o.hide_render = True
            elif k in cracked:
                o.hide_render = not dmg
            else:
                o.hide_render = dmg
        print("impact: removed", len(gone), "chunks, cracked", len(cracked))
    if mode.startswith("remove:"):
        gone = set(mode.split(":", 1)[1].split("+"))
        gone |= {k for k, v in PARENT.items() if v in gone}
        for o in scene.objects:
            if o.type == 'MESH' and "__" in o.name and o.name.split("__")[0] in gone:
                o.hide_render = True
    if mode == "explode":
        gc = {g: sum(v, Vector()) / len(v) for g, v in centers.items()}
        for o in scene.objects:
            if o.type == 'MESH' and "__" in o.name and not o.hide_render:
                g = o.name.split("__")[0]
                base = PARENT.get(g, g)
                if base in DETACH and base in gc:
                    d = gc[base].copy()
                    d.z = 0
                    off = d.normalized() * 0.9 + Vector((0, 0, 0.35))
                    wt = o.matrix_world.translation + off
                    o.location = o.parent.matrix_world.inverted() @ wt if o.parent else wt

scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
try:
    scene.eevee.taa_render_samples = 16
except Exception:
    pass
scene.view_settings.view_transform = 'AgX'

world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.55, 0.6, 0.68, 1)
bg.inputs[1].default_value = 0.9

bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
floor = bpy.context.active_object
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.25, 0.25, 0.27, 1)
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6
floor.data.materials.append(fm)

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
scene.collection.objects.link(sun)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam


def shoot(name, loc, target, lens=50):
    if only and name not in only:
        return
    cam.location = Vector(loc)
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    scene.render.filepath = f"{prefix}_{name}.png"
    bpy.ops.render.render(write_still=True)


far = 1.6 if mode == "explode" else 1.0
shoot("front34", (4.9 * far, -6.6 * far, 1.7 * far), (0, -0.2, 0.55), 45)
shoot("rear34", (-5.0 * far, 6.4 * far, 2.1 * far), (0, 0.3, 0.6), 45)
shoot("front", (0.0, -7.5, 1.0), (0, 0, 0.6), 45)
shoot("rear", (0.0, 7.5, 1.2), (0, 0, 0.6), 45)
shoot("wheel", (2.7, -3.0, 0.55), (0.85, -1.6, 0.35), 60)
shoot("tyre", (3.0, -1.57, 0.4), (0.85, -1.57, 0.35), 50)
shoot("tyreR", (3.0, 1.34, 0.4), (0.85, 1.34, 0.36), 50)
shoot("interior", (0.35, 0.45, 1.1), (0.3, -0.6, 0.8), 24)
shoot("steer", (0.31, 0.32, 0.92), (0.31, -0.05, 0.77), 40)
shoot("dash", (0.0, 0.3, 1.0), (0.0, -0.6, 0.75), 30)
shoot("rearbadge", (0.6, 4.2, 1.0), (0, 2.3, 0.75), 60)
shoot("frontbadge", (0.6, -4.4, 1.0), (0, -2.3, 0.6), 60)
shoot("side", (7.0 * far, 0.0, 0.9), (0, 0, 0.6), 50)
shoot("sideR", (-7.0 * far, 0.0, 0.9), (0, 0, 0.6), 50)
shoot("top", (0.01, 0.0, 10.0 * far), (0, 0, 0), 40)
shoot("windshield", (0.9, -3.8, 2.1), (0, -0.6, 1.0), 50)
shoot("sideglass", (3.4, 0.2, 1.3), (0.6, -0.1, 1.0), 45)
shoot("under", (3.5, -1.0, 0.15), (0, 0, 0.3), 35)
