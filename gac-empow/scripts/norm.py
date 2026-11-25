"""Import the source, bake transforms, scale to ~4.70 m, centre on origin, export a normalized GLB
plus per-object bounds (normalized space) for classification work."""
import bpy, json, os
from mathutils import Vector, Matrix

GLB = r"C:\Users\jordan\RobloxCars\gac-empow\source\source\gac_empow.glb"
WORK = r"C:\Users\jordan\RobloxCars\gac-empow\scripts\work"
os.makedirs(WORK, exist_ok=True)
S = 4.70 / 58.061
CX, CY = 13.097, 29.044
NORM = Matrix.Diagonal((S, S, S, 1)) @ Matrix.Translation((-CX, -CY, 0))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
scene = bpy.context.scene
world = {o.name: o.matrix_world.copy() for o in scene.objects if o.type == 'MESH'}
info = {}
for o in [o for o in scene.objects if o.type == 'MESH']:
    o.parent = None
    o.data.transform(NORM @ world[o.name])
    o.matrix_world = Matrix.Identity(4)
    vs = [v.co for v in o.data.vertices]
    lo = [round(min(v[i] for v in vs), 3) for i in range(3)]
    hi = [round(max(v[i] for v in vs), 3) for i in range(3)]
    info[o.name] = {"mat": o.data.materials[0].name, "tris": sum(len(p.vertices) - 2 for p in o.data.polygons),
                    "lo": lo, "hi": hi}
for o in [o for o in scene.objects if o.type == 'EMPTY']:
    bpy.data.objects.remove(o, do_unlink=True)
json.dump(info, open(os.path.join(WORK, "norm_bounds.json"), "w"), indent=1)
bpy.ops.export_scene.gltf(filepath=os.path.join(WORK, "orig_norm.glb"), export_format='GLB')
print("ok")
