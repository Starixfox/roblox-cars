import bpy, json, sys
from mathutils import Vector

GLB = r"C:\Users\jordan\RobloxCars\porsche-gt3rs\source\source\Porsche_GT3RS_MOD.glb"
OUT = r"C:\Users\jordan\RobloxCars\porsche-gt3rs\scripts\inspect.json"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

objs = []
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    me = o.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = [min(v[i] for v in bb) for i in range(3)]
    mx = [max(v[i] for v in bb) for i in range(3)]
    objs.append({
        "name": o.name,
        "parent": o.parent.name if o.parent else None,
        "tris": tris,
        "mats": [m.name for m in me.materials if m],
        "min": [round(x, 3) for x in mn],
        "max": [round(x, 3) for x in mx],
    })

objs.sort(key=lambda d: -d["tris"])
mats = {}
for m in bpy.data.materials:
    imgs = []
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                imgs.append(n.image.name)
    mats[m.name] = imgs

json.dump({
    "total_tris": sum(d["tris"] for d in objs),
    "mesh_count": len(objs),
    "objects": objs,
    "materials": mats,
    "empties": [o.name for o in bpy.data.objects if o.type == 'EMPTY'],
}, open(OUT, "w"), indent=1)
