"""Print material alpha / culling settings of the source glb."""
import bpy

GLB = r"C:\Users\jordan\RobloxCars\gac-aion-ray7\source\source\GAC AION RAY7.glb"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
for m in bpy.data.materials:
    b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m.node_tree else None
    al = b.inputs["Alpha"] if b else None
    src = None
    if al is not None and al.is_linked:
        l = al.links[0]
        src = f"{l.from_node.type}:{getattr(getattr(l.from_node, 'image', None), 'name', '')}:{l.from_socket.name}"
    print("MAT", m.name, "| method", getattr(m, "surface_render_method", None), "| blend", m.blend_method,
          "| cull", m.use_backface_culling, "| alpha", (round(al.default_value, 3) if al is not None and not al.is_linked else src),
          "| metal", round(b.inputs["Metallic"].default_value, 2) if b else None,
          "| rough", round(b.inputs["Roughness"].default_value, 2) if b else None,
          "| nodes", sorted({n.type for n in m.node_tree.nodes}) if m.node_tree else None)
for img in bpy.data.images:
    print("IMG", img.name, tuple(img.size), "ch", img.channels, "alpha_mode", img.alpha_mode, "users", img.users)
