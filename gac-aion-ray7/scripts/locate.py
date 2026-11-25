"""List source objects with geometry near given real-size points (to find logo meshes),
and dump chosen images of the processed blend for checking."""
import bpy, os
from mathutils import Vector, Matrix

GLB = r"C:\Users\jordan\RobloxCars\gac-aion-ray7\source\source\GAC AION RAY7.glb"
POINTS = {
    "rear_logo": (0.0, 2.47, 0.89, 0.12),
    "trunk_script": (-0.5, 2.45, 0.75, 0.15),
    "front_logo": (0.0, -2.40, 0.64, 0.10),
    "steer_logo": (0.37, -0.44, 0.86, 0.06),
    "cap_LF": (0.86, -1.50, 0.335, 0.05),
    "screen": (0.06, -0.58, 0.83, 0.15),
}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
M = Matrix.Scale(0.25, 4) @ Matrix.Translation((0.12, -0.075, 0.484))
for o in [o for o in bpy.context.scene.objects if o.parent is None]:
    o.matrix_world = M @ o.matrix_world
bpy.context.view_layer.update()
data = []
for o in bpy.context.scene.objects:
    if o.type == 'MESH':
        mw = o.matrix_world
        data.append((o, [mw @ v.co for v in o.data.vertices]))
print("== wide verts at the front")
for o, vs in data:
    w = [v for v in vs if abs(v.x) > 0.70 and v.y < -2.22 and 0.5 < v.z < 0.75]
    if w:
        print("  ", o.name, len(w), "of", len(vs), [m.name for m in o.data.materials if m],
              "maxx", round(max(abs(v.x) for v in w), 3), "y", round(min(v.y for v in w), 3), round(max(v.y for v in w), 3),
              "z", round(min(v.z for v in w), 3), round(max(v.z for v in w), 3))
POINTS = {"teeth_in": (0.70, -0.40, 0.95, 0.08), "teeth_mid": (0.78, -0.40, 0.95, 0.06),
          "teeth_out": (0.85, -0.40, 0.96, 0.06), "rear_bits": (0.9, 1.95, 0.2, 0.15)}
for key, (x, y, z, r) in POINTS.items():
    p = Vector((x, y, z))
    rows = []
    for o, vs in data:
        n = sum(1 for v in vs if (v - p).length < r)
        if n:
            d = min((v - p).length for v in vs)
            lo = Vector([min(v[i] for v in vs) for i in range(3)])
            hi = Vector([max(v[i] for v in vs) for i in range(3)])
            rows.append((d, o.name, n, len(vs), [m.name for m in o.data.materials if m],
                         tuple(round(c, 3) for c in lo), tuple(round(c, 3) for c in hi)))
    print("==", key)
    for row in sorted(rows)[:14]:
        print("  ", round(row[0], 3), row[1], "near", row[2], "of", row[3], row[4], row[5], row[6])
