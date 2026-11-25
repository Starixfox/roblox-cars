"""Render preview shots. Args: <model.glb> <out_prefix> [normal|dmg|explode] [shots,comma,separated]"""
import bpy, sys, math
from mathutils import Vector

model, prefix = sys.argv[1], sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else "normal"
only = sys.argv[4].split(",") if len(sys.argv) > 4 else None

DETACH = ("Hood", "Trunk", "Door_L", "Door_R", "Door_RL", "Door_RR", "FrontBumper", "RearBumper", "Wing",
          "Mirror_L", "Mirror_R", "Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR", "Glass_Door_L", "Glass_Door_R",
          "Glass_Door_RL", "Glass_Door_RR")
# ride-along groups follow their parent's offset
PARENT = {"Mirror_L": "Door_L", "Mirror_R": "Door_R", "Glass_Door_L": "Door_L", "Glass_Door_R": "Door_R",
          "Glass_Door_RL": "Door_RL", "Glass_Door_RR": "Door_RR"}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=model)
scene = bpy.context.scene

if mode == "orig":
    # raw Sketchfab file: bring it to real size, centred, wheels on the ground
    from mathutils import Matrix
    M = Matrix.Scale(0.25, 4) @ Matrix.Translation((0.12, -0.075, 0.484))
    for o in [o for o in scene.objects if o.parent is None]:
        o.matrix_world = M @ o.matrix_world

is_split = any("__" in o.name for o in scene.objects)
if is_split:
    centers = {}
    for o in scene.objects:
        if o.type == 'MESH' and "__" in o.name:
            g = o.name.split("__")[0]
            dmg = "__DMG__" in o.name
            show = dmg if mode == "dmg" else not dmg
            # in dmg mode keep groups that have no DMG version visible
            if mode == "dmg" and not dmg:
                has_dmg = any(x.name.startswith(g + "__DMG__") for x in scene.objects)
                show = not has_dmg
            o.hide_render = not show
            if show:
                centers.setdefault(g, []).append(o.matrix_world @ (sum((Vector(c) for c in o.bound_box), Vector()) / 8))
    def chunk_key(o):
        s = o.name.split("__")
        return (s[0], s[1]) if len(s) >= 3 and s[1].startswith("C") and s[1][1:].isdigit() else None

    def world_center(o):
        return o.matrix_world @ (sum((Vector(c) for c in o.bound_box), Vector()) / 8)

    if mode == "chunkcolors":
        import random
        rnd = random.Random(3)
        mats = {}
        for o in scene.objects:
            if o.type == 'MESH' and not o.hide_render:
                k = chunk_key(o)
                if not k:
                    continue
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
        crash, crash_r = Vector((0.75, -2.3, 0.6)), 0.75
        glass_hit = Vector((0.25, -0.85, 1.1))
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
                    top = o
                    while top.parent:
                        top = top.parent
                    o.matrix_world.translation += off
                    # glTF import parents objects under group empties: move the object itself
                    o.location = o.parent.matrix_world.inverted() @ (o.matrix_world.translation) if o.parent else o.matrix_world.translation

scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
try:
    scene.eevee.taa_render_samples = 32
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
shoot("front34", (4.9 * far, -6.6 * far, 1.7 * far), (0, -0.2, 0.6), 45)
shoot("rear34", (-5.1 * far, 6.4 * far, 2.1 * far), (0, 0.3, 0.65), 45)
shoot("front", (0.0, -7.5, 1.0), (0, 0, 0.7), 45)
shoot("rear", (0.0, 7.5, 1.1), (0, 0, 0.75), 45)
shoot("wheel", (2.6, -2.9, 0.55), (0.85, -1.5, 0.34), 60)
shoot("tyre", (2.2, -1.5, 0.4), (0.85, -1.5, 0.34), 60)
shoot("interior", (0.3, 0.45, 1.15), (0.3, -0.7, 0.85), 24)
shoot("dash", (-0.1, 0.25, 1.2), (0.2, -0.6, 0.9), 30)
shoot("rearbadge", (0.6, 4.0, 1.0), (0, 2.45, 0.85), 60)
shoot("frontbadge", (0.6, -4.0, 0.8), (0, -2.45, 0.6), 60)
shoot("side", (7.0 * far, 0.0, 0.9), (0, 0, 0.65), 50)
shoot("top", (0.01, 0.0, 9.5 * far), (0, 0, 0), 40)
shoot("windshield", (0.9, -3.8, 2.0), (0, -0.8, 1.05), 50)
shoot("sideglass", (3.4, 0.2, 1.3), (0.7, 0.0, 1.0), 45)
