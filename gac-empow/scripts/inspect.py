import bpy, json
from mathutils import Vector

GLB = r"C:\Users\jordan\RobloxCars\gac-empow\source\source\gac_empow.glb"
OUT = r"C:\Users\jordan\RobloxCars\gac-empow\scripts\inspect.json"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)


def chain(o):
    out = []
    p = o.parent
    while p:
        out.append(p.name)
        p = p.parent
    return out


objs = []
allmn, allmx = [9e9] * 3, [-9e9] * 3
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    me = o.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    mw = o.matrix_world
    vs = [mw @ v.co for v in me.vertices]
    if not vs:
        continue
    mn = [min(v[i] for v in vs) for i in range(3)]
    mx = [max(v[i] for v in vs) for i in range(3)]
    allmn = [min(a, b) for a, b in zip(allmn, mn)]
    allmx = [max(a, b) for a, b in zip(allmx, mx)]
    matcount = {}
    for p in me.polygons:
        m = me.materials[p.material_index].name if p.material_index < len(me.materials) and me.materials[p.material_index] else "None"
        matcount[m] = matcount.get(m, 0) + len(p.vertices) - 2
    objs.append({"name": o.name, "parents": chain(o), "tris": tris, "mats": matcount,
                 "min": [round(x, 3) for x in mn], "max": [round(x, 3) for x in mx]})

objs.sort(key=lambda d: -d["tris"])
mats = {}
for m in bpy.data.materials:
    info = {}
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                info.setdefault("images", []).append(n.image.name)
            if n.type == 'BSDF_PRINCIPLED':
                info["base"] = [round(x, 3) for x in n.inputs["Base Color"].default_value]
                info["metal"] = round(n.inputs["Metallic"].default_value, 2)
                info["rough"] = round(n.inputs["Roughness"].default_value, 2)
                info["alpha"] = round(n.inputs["Alpha"].default_value, 2)
                info["base_linked"] = n.inputs["Base Color"].is_linked
                info["alpha_linked"] = n.inputs["Alpha"].is_linked
    info["blend"] = getattr(m, "surface_render_method", "")
    mats[m.name] = info

json.dump({
    "total_tris": sum(d["tris"] for d in objs),
    "mesh_count": len(objs),
    "bounds": [allmn, allmx],
    "objects": objs,
    "materials": mats,
    "images": {i.name: list(i.size) for i in bpy.data.images},
    "empties": [(o.name, o.parent.name if o.parent else None) for o in bpy.data.objects if o.type == 'EMPTY'],
}, open(OUT, "w"), indent=1)
print("ok")
