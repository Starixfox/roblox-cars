"""Island analysis on the normalized model: per object, list islands (tris, bounds)."""
import bpy, bmesh, json, sys
WORK = r"C:\Users\jordan\RobloxCars\gac-empow\scripts\work"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=WORK + r"\orig_norm.glb")
out = {}
for o in bpy.context.scene.objects:
    if o.type != 'MESH':
        continue
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0002)
    bm.faces.ensure_lookup_table()
    seen = set()
    isl = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        seen.add(f.index)
        fs = []
        while stack:
            g = stack.pop()
            fs.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        vs = [v.co for g in fs for v in g.verts]
        lo = [round(min(v[i] for v in vs), 3) for i in range(3)]
        hi = [round(max(v[i] for v in vs), 3) for i in range(3)]
        isl.append({"tris": sum(len(g.verts) - 2 for g in fs), "lo": lo, "hi": hi})
    isl.sort(key=lambda d: -d["tris"])
    out[o.name] = {"mat": o.data.materials[0].name, "n": len(isl), "islands": isl}
    bm.free()
json.dump(out, open(WORK + r"\islands.json", "w"), indent=0)
print("ok")
