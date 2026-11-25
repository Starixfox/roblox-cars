"""Import the FBX and dump objects, tris, bounds, materials, image nodes to inspect.json."""
import bpy, json, os
from mathutils import Vector

ROOT = r"C:\Users\jordan\RobloxCars\buildings\london-skyscraper"
FBX = os.path.join(ROOT, "extracted", "London, One Blackfriars Skyscraper", "SOURCE", "One_Blackfairs_Skyscraper.fbx")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX)

out = {"objects": [], "materials": {}, "images": {}}
total = 0
gmin = Vector((1e9,) * 3); gmax = Vector((-1e9,) * 3)
for o in bpy.context.scene.objects:
    rec = {"name": o.name, "type": o.type, "parent": o.parent.name if o.parent else None,
           "loc": list(o.location), "rot": list(o.rotation_euler), "scale": list(o.scale)}
    if o.type == 'MESH':
        me = o.data
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        total += tris
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        mn = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
        mx = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
        for i in range(3):
            gmin[i] = min(gmin[i], mn[i]); gmax[i] = max(gmax[i], mx[i])
        counts = {}
        for p in me.polygons:
            m = me.materials[p.material_index].name if me.materials and p.material_index < len(me.materials) and me.materials[p.material_index] else "None"
            counts[m] = counts.get(m, 0) + len(p.vertices) - 2
        rec.update({"tris": tris, "verts": len(me.vertices), "uv_layers": [u.name for u in me.uv_layers],
                    "min": list(mn), "max": list(mx), "mat_tris": counts})
    out["objects"].append(rec)

for m in bpy.data.materials:
    info = {"nodes": []}
    if m.node_tree:
        for n in m.node_tree.nodes:
            d = {"type": n.type, "name": n.name}
            if n.type == 'TEX_IMAGE' and n.image:
                d["image"] = n.image.name
                d["links_to"] = [(l.to_node.name, l.to_socket.name) for l in n.outputs[0].links]
            if n.type == 'BSDF_PRINCIPLED':
                d["base"] = list(n.inputs["Base Color"].default_value)
                d["alpha"] = n.inputs["Alpha"].default_value
            info["nodes"].append(d)
    out["materials"][m.name] = info

for im in bpy.data.images:
    out["images"][im.name] = {"path": im.filepath, "size": list(im.size), "has_data": im.has_data,
                              "exists": os.path.exists(bpy.path.abspath(im.filepath)) if im.filepath else False}

out["total_tris"] = total
out["bounds"] = [list(gmin), list(gmax)]
with open(os.path.join(ROOT, "scripts", "inspect.json"), "w") as f:
    json.dump(out, f, indent=1)
print("total tris", total, "bounds", list(gmin), list(gmax))
print("objects", len(out["objects"]), "materials", len(out["materials"]), "images", len(out["images"]))
