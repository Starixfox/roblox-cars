"""Debug: list faces with very long edges in a .blend (arg: path) - finds stray sheets."""
import bpy, sys
path = sys.argv[1]
bpy.ops.wm.open_mainfile(filepath=path)
bpy.context.view_layer.update()
for o in bpy.context.scene.objects:
    if o.type != 'MESH':
        continue
    mw = o.matrix_world
    me = o.data
    bad = []
    for p in me.polygons:
        vs = [mw @ me.vertices[i].co for i in p.vertices]
        L = max((vs[i] - vs[(i + 1) % len(vs)]).length for i in range(len(vs)))
        if L > 0.9:
            bad.append((round(L, 2), [tuple(round(x, 2) for x in v) for v in vs]))
    if bad:
        print(o.name, len(bad), bad[:3])
