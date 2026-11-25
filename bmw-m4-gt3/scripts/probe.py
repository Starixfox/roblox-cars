"""Probe the BMW FBX at real scale: image sources, texture dump, per-object world bounds, decal hints."""
import bpy, json, os
from mathutils import Vector, Matrix

FBX = r"C:\Users\jordan\RobloxCars\bmw-m4-gt3\source\inner\FINAL_MODEL_GT325.fbx"
DUMP = r"C:\Users\jordan\RobloxCars\bmw-m4-gt3\scripts\tex"
OUT = r"C:\Users\jordan\RobloxCars\bmw-m4-gt3\scripts\probe.json"
os.makedirs(DUMP, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX)
root = bpy.data.objects.new("SCALE", None)
bpy.context.scene.collection.objects.link(root)
for o in list(bpy.context.scene.objects):
    if o.parent is None and o is not root:
        o.parent = root
root.scale = (100, 100, 100)
bpy.context.view_layer.update()

imgs = {}
for img in list(bpy.data.images):
    imgs[img.name] = {"file": img.filepath, "packed": bool(img.packed_file), "size": list(img.size),
                      "channels": img.channels}
    if img.size[0] > 0 and "." not in img.name[-4:]:
        try:
            w, h = img.size
            t = bpy.data.images.new("__dump", w, h, alpha=True)
            px = list(img.pixels[:])
            if img.channels != 4:
                c = img.channels
                px = [px[i * c + min(k, c - 1)] if k < 3 else 1.0 for i in range(w * h) for k in range(4)]
            t.pixels[:] = px
            t.filepath_raw = os.path.join(DUMP, "".join(ch if ch.isalnum() else "_" for ch in img.name) + ".png")
            t.file_format = 'PNG'
            t.save()
            bpy.data.images.remove(t)
        except Exception as ex:
            imgs[img.name]["err"] = str(ex)

mats = {}
for m in bpy.data.materials:
    d = {"nodes": []}
    if m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE':
                d["nodes"].append([n.name, n.image.name if n.image else None,
                                   [(l.to_node.type, l.to_socket.name) for l in n.outputs[0].links],
                                   [(l.to_node.type, l.to_socket.name) for l in n.outputs[1].links]])
            if n.type == 'BSDF_PRINCIPLED':
                d["base"] = list(n.inputs["Base Color"].default_value)
                d["alpha"] = n.inputs["Alpha"].default_value
                d["metal"] = n.inputs["Metallic"].default_value
                d["rough"] = n.inputs["Roughness"].default_value
    d["blend"] = getattr(m, "blend_method", "")
    mats[m.name] = d

objs = []
for o in bpy.context.scene.objects:
    if o.type != 'MESH':
        continue
    mw = o.matrix_world
    vs = [mw @ v.co for v in o.data.vertices]
    if not vs:
        objs.append({"name": o.name, "parent": o.parent.name if o.parent else None,
                     "loc": [round(x, 3) for x in mw.translation]})
        continue
    lo = [round(min(v[i] for v in vs), 3) for i in range(3)]
    hi = [round(max(v[i] for v in vs), 3) for i in range(3)]
    objs.append({"name": o.name, "parent": o.parent.name if o.parent else None, "lo": lo, "hi": hi,
                 "tris": sum(len(p.vertices) - 2 for p in o.data.polygons),
                 "mats": sorted({o.data.materials[p.material_index].name for p in o.data.polygons
                                 if p.material_index < len(o.data.materials) and o.data.materials[p.material_index]}),
                 "uvs": [l.name for l in o.data.uv_layers], "loc": [round(x, 3) for x in mw.translation]})
json.dump({"images": imgs, "materials": mats, "objects": objs}, open(OUT, "w"), indent=1)
bpy.ops.wm.save_as_mainfile(filepath=r"C:\Users\jordan\RobloxCars\bmw-m4-gt3\scripts\probe.blend")
