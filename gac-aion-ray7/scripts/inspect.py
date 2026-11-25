"""Inspect the GAC AION RAY7 glb: objects, hierarchy, tris, materials, textures, bounds."""
import bpy, os, json
from mathutils import Vector

GLB = r"C:\Users\jordan\RobloxCars\gac-aion-ray7\source\source\GAC AION RAY7.glb"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
scene = bpy.context.scene


def wbounds(o):
    pts = [o.matrix_world @ v.co for v in o.data.vertices]
    if not pts:
        return None
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def path(o):
    s = []
    p = o.parent
    while p:
        s.append(p.name)
        p = p.parent
    return "/".join(reversed(s))


tot = 0
glo, ghi = Vector((9e9,) * 3), Vector((-9e9,) * 3)
rows = []
for o in scene.objects:
    if o.type != 'MESH':
        continue
    t = sum(len(p.vertices) - 2 for p in o.data.polygons)
    tot += t
    b = wbounds(o)
    if not b:
        continue
    lo, hi = b
    glo = Vector(map(min, glo, lo)); ghi = Vector(map(max, ghi, hi))
    mats = [m.name if m else None for m in o.data.materials]
    rows.append((o.name, path(o), t, mats, tuple(round(x, 3) for x in lo), tuple(round(x, 3) for x in hi)))
print("TOTAL tris", tot, "objects", len(rows))
print("BOUNDS", tuple(round(x, 3) for x in glo), tuple(round(x, 3) for x in ghi))
for r in sorted(rows, key=lambda r: r[1] + r[0]):
    print("OBJ", r[0], "| parent:", r[1], "| tris", r[2], "| mats", r[3], "| lo", r[4], "hi", r[5])
print("EMPTIES")
for o in scene.objects:
    if o.type != 'MESH':
        print("  ", o.type, o.name, "parent", o.parent.name if o.parent else None, tuple(round(x, 3) for x in o.matrix_world.to_translation()),
              tuple(round(x, 3) for x in o.matrix_world.to_scale()))
print("MATERIALS")
for m in bpy.data.materials:
    imgs = []
    if m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                link = [l.to_socket.name + "@" + l.to_node.name for l in n.outputs[0].links]
                imgs.append((n.image.name, tuple(n.image.size), link))
    b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m.node_tree else None
    bc = tuple(round(x, 2) for x in b.inputs["Base Color"].default_value) if b else None
    users = [o.name for o in scene.objects if o.type == 'MESH' and m.name in [x.name for x in o.data.materials if x]]
    print("MAT", m.name, "| base", bc, "| imgs", imgs, "| users", len(users), users[:6])
