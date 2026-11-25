"""Find which original meshes have faces where the rear PORSCHE lettering sits."""
import bpy
from mathutils import Vector

GLB = r"C:\Users\jordan\RobloxCars\porsche-gt3rs\source\source\Porsche_GT3RS_MOD.glb"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

# rear light bar band: centered, very back of the car, light-bar height
for o in bpy.context.scene.objects:
    if o.type != 'MESH':
        continue
    mw = o.matrix_world
    hits = {}
    for p in o.data.polygons:
        c = mw @ p.center
        if o.name != "EXT_CHROME_0" and abs(c.x) < 0.28 and 2.13 < c.y < 2.20 and 0.680 < c.z < 0.712:
            m = o.data.materials[p.material_index].name if o.data.materials else None
            hits.setdefault(m, []).append(c)
    for m, cs in hits.items():
        zs = [c.z for c in cs]; ys = [c.y for c in cs]; xs = [c.x for c in cs]
        print(f"{o.name:28} mat={m:24} faces={len(cs):5} x[{min(xs):.3f}..{max(xs):.3f}] "
              f"y[{min(ys):.3f}..{max(ys):.3f}] z[{min(zs):.3f}..{max(zs):.3f}] total_faces={len(o.data.polygons)}")
