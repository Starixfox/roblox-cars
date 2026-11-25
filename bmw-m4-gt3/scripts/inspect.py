"""Inspect the BMW FBX: objects, triangles, materials, textures, world bounds."""
import bpy, json
from mathutils import Vector

FBX = r"C:\Users\jordan\RobloxCars\bmw-m4-gt3\source\inner\FINAL_MODEL_GT325.fbx"
OUT = r"C:\Users\jordan\RobloxCars\bmw-m4-gt3\scripts\inspect.json"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX)
bpy.context.view_layer.update()

objs = []
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    me = o.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = [min(v[i] for v in bb) for i in range(3)]
    mx = [max(v[i] for v in bb) for i in range(3)]
    mats = {}
    for p in me.polygons:
        m = me.materials[p.material_index].name if p.material_index < len(me.materials) and me.materials[p.material_index] else None
        mats[m] = mats.get(m, 0) + len(p.vertices) - 2
    objs.append({"name": o.name, "parent": o.parent.name if o.parent else None, "tris": tris,
                 "mats": mats, "min": [round(x, 3) for x in mn], "max": [round(x, 3) for x in mx],
                 "scale": [round(x, 4) for x in o.matrix_world.to_scale()]})
objs.sort(key=lambda d: -d["tris"])
mats = {}
for m in bpy.data.materials:
    imgs = []
    if m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                links = [l.to_socket.name for l in n.outputs[0].links]
                imgs.append(f"{n.image.name} {tuple(n.image.size)} -> {links}")
    mats[m.name] = imgs
json.dump({"total_tris": sum(d["tris"] for d in objs), "objects": objs, "materials": mats,
           "empties": [o.name for o in bpy.data.objects if o.type == 'EMPTY'],
           "missing_images": [i.name for i in bpy.data.images if i.size[0] == 0]},
          open(OUT, "w"), indent=1)
