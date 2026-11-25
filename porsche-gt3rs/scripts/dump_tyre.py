import bpy, os
GLB = r"C:\Users\jordan\RobloxCars\porsche-gt3rs\source\source\Porsche_GT3RS_MOD.glb"
OUT = r"C:\Users\jordan\RobloxCars\porsche-gt3rs\scripts\tex_dump"
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
for img in bpy.data.images:
    if img.name.startswith(("Tyre", "License")):
        img.filepath_raw = os.path.join(OUT, img.name + ".png")
        img.file_format = 'PNG'
        img.save()
        print(img.name, img.size[:])
