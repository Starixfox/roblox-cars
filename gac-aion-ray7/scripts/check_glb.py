"""Check an exported glb against the naming contract. Args: <model.glb>"""
import bpy, sys, re
from collections import Counter

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=sys.argv[1])
CHUNKED = {"Hood", "Trunk", "Door_L", "Door_R", "Door_RL", "Door_RR", "FrontBumper", "RearBumper", "Wing",
           "Body_Front", "Body_Mid", "Body_Rear"}
UNCHUNKED = {"Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR", "Mirror_L", "Mirror_R", "Interior", "SteeringWheel",
             "Brakes", "HeadLight_L", "HeadLight_R", "TailLight_L", "TailLight_R"}
pat_u = re.compile(r"^([A-Za-z_]+?)__([A-Za-z0-9_]+?)(_\d+)?$")
pat_c = re.compile(r"^([A-Za-z_]+?)__C(\d\d)__(DMG__)?([A-Za-z0-9_]+?)(_\d+)?$")
bad, groups, chunks = [], Counter(), {}
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in meshes:
    n = o.name
    t = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if len(o.data.materials) != 1:
        bad.append(f"{n}: {len(o.data.materials)} materials")
    if t > 19000:
        bad.append(f"{n}: {t} tris")
    m = pat_c.match(n)
    if m:
        g = m.group(1)
        if not (g in CHUNKED or g.startswith("Glass_")):
            bad.append(f"{n}: chunk id on unchunked group")
        if m.group(3) and not g.startswith("Glass_"):
            bad.append(f"{n}: DMG on non-glass")
        chunks.setdefault(g, set()).add(m.group(2))
    else:
        m = pat_u.match(n)
        if not m or m.group(1) not in UNCHUNKED:
            bad.append(f"{n}: name does not match contract")
            continue
        g = m.group(1)
    groups[g] += 1
    if not o.parent or o.parent.name != g:
        bad.append(f"{n}: parent {o.parent.name if o.parent else None}")
# wheel pivots: the group empty sits at the hub centre, parts have zero offset
for g in ("Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR"):
    e = bpy.data.objects.get(g)
    if e:
        offs = {tuple(round(c, 4) for c in o.location) for o in e.children}
        print("PIVOT", g, tuple(round(c, 3) for c in e.matrix_world.translation), "child offsets", offs)
print("MESHES", len(meshes))
for g in sorted(groups):
    print("GROUP", g, "parts", groups[g], "chunks", len(chunks.get(g, ())))
print("PROBLEMS", len(bad))
for b in bad[:40]:
    print("BAD", b)
