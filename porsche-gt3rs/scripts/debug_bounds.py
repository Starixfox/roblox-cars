"""Compare world bounds per group: saved .blend vs re-imported GLB."""
import bpy
from mathutils import Vector

ROOT = r"C:\Users\jordan\RobloxCars\porsche-gt3rs\roblox"


def bounds(prefixes):
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for o in bpy.context.scene.objects:
        if o.type != 'MESH':
            continue
        g = next((p for p in prefixes if o.name.startswith(p)), None)
        if not g:
            continue
        ev = o.evaluated_get(dg)
        pts = [ev.matrix_world @ v.co for v in ev.data.vertices]
        if not pts:
            continue
        lo, hi = out.get(g, (Vector((9e9,) * 3), Vector((-9e9,) * 3)))
        for p in pts:
            lo = Vector(map(min, lo, p)); hi = Vector(map(max, hi, p))
        out[g] = (lo, hi)
    return out


G = ["Body", "Interior", "Glass", "Lights", "Brakes", "SteeringWheel",
     "Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR"]


def show(tag, b):
    print("==", tag)
    for g in G:
        if g in b:
            lo, hi = b[g]
            print(f"{g:14} x[{lo.x:.2f}..{hi.x:.2f}] y[{lo.y:.2f}..{hi.y:.2f}] z[{lo.z:.2f}..{hi.z:.2f}]")


bpy.ops.wm.open_mainfile(filepath=ROOT + r"\GT3RS_Roblox.blend")
show("blend", bounds(G))
# a few individual objects
for o in bpy.context.scene.objects:
    if o.type == 'MESH' and o.name.startswith("Interior") and max((o.matrix_world @ Vector(c)).z for c in o.bound_box) > 1.3:
        print(o.name, "loc", tuple(round(x, 3) for x in o.location),
              "parent", o.parent.name if o.parent else None,
              "parent loc", tuple(round(x, 3) for x in o.parent.location) if o.parent else None,
              "rot", tuple(round(x, 3) for x in o.rotation_euler), "scale", tuple(round(x, 3) for x in o.scale))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=ROOT + r"\GT3RS_Roblox.glb")
show("glb", bounds(G))
