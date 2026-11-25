"""Debug: print material + UV of faces of a group near a point. Args: blend group x y z radius"""
import bpy, sys
from mathutils import Vector
path, group = sys.argv[1], sys.argv[2]
pt = Vector(tuple(float(a) for a in sys.argv[3:6]))
rad = float(sys.argv[6])
bpy.ops.wm.open_mainfile(filepath=path)
bpy.context.view_layer.update()
for o in bpy.context.scene.objects:
    if o.type != 'MESH' or not o.name.startswith(group):
        continue
    me = o.data
    uvl = me.uv_layers.active.data if me.uv_layers else None
    for p in me.polygons:
        c = o.matrix_world @ p.center
        if (c - pt).length < rad and uvl:
            uv = sum((uvl[li].uv for li in p.loop_indices), Vector((0, 0))) / p.loop_total
            print(o.name, tuple(round(x, 3) for x in c), "uv", round(uv.x, 3), round(uv.y, 3),
                  "px(top-left,512)", int(uv.x % 1 * 512), int((1 - uv.y % 1) * 512))
