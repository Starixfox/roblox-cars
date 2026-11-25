"""List faces of fixed groups in the wing-post area of the exported High model."""
import bpy
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r"C:\Users\jordan\RobloxCars\porsche-gt3rs\roblox\GT3RS_High.glb")
for o in bpy.context.scene.objects:
    if o.type != 'MESH' or "__" not in o.name:
        continue
    g = o.name.split("__")[0]
    if g in ("Wing", "Trunk"):
        continue
    mw = o.matrix_world
    cs = [mw @ p.center for p in o.data.polygons]
    hit = [c for c in cs if c.y > 1.5 and abs(c.x) < 0.5 and c.z > 0.9]
    if len(hit) > 10:
        xs = [abs(c.x) for c in hit]; ys = [c.y for c in hit]; zs = [c.z for c in hit]
        print(f"{o.name:40} faces={len(hit):5} |x|[{min(xs):.2f}..{max(xs):.2f}] y[{min(ys):.2f}..{max(ys):.2f}] z[{min(zs):.2f}..{max(zs):.2f}]")
