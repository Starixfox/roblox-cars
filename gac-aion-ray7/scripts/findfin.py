"""Find vertices in a processed blend that stick out of the body. Args: <blend>"""
import bpy, sys

bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
for o in bpy.data.objects:
    if o.type != 'MESH' or o.name.startswith(("Wheel_", "Mirror_")):
        continue
    mw = o.matrix_world
    vs = [mw @ v.co for v in o.data.vertices]
    w = [v for v in vs if (abs(v.x) > 0.93 and v.y < -1.75) or v.y < -2.48 or (abs(v.x) > 0.80 and v.y < -2.2)]
    if w:
        print("OUT", o.name, len(w), [tuple(round(c, 3) for c in v) for v in w[:4]])
