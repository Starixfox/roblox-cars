"""Save processed images from a variant .blend as PNGs for checking. Args: <blend> <outdir>"""
import bpy, sys, os

blend, out = sys.argv[1], sys.argv[2]
bpy.ops.wm.open_mainfile(filepath=blend)
os.makedirs(out, exist_ok=True)
for name in ("1AMo-1AMo.dds", "aion_hypergt_Int1_Diffuse", "000002DA6BA25BF8-000002DA6BA25BF8.dds",
             "245_Tyre_D-245_Tyre_D.dds", "245_Tyre_D_nm", "Plate_D-Plate_D.dds"):
    img = bpy.data.images.get(name)
    if not img:
        print("missing", name)
        continue
    s = bpy.context.scene
    s.render.image_settings.file_format = 'PNG'
    path = os.path.join(out, name.split("-")[0].split(".")[0] + ".png")
    img.save_render(path, scene=s)
    print("saved", path, tuple(img.size))
