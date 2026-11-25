# London Skyscraper (One Blackfriars) for Roblox

Real scale (1:1, metres). The tower is about 170 m tall, which is roughly 600 studs at Roblox's
default 1 stud = 0.28 m. Credit is required, see `CREDITS.txt`.

## Files

| File | What it is |
|---|---|
| `LondonSkyscraper.glb` | Primary file for Roblox import (textures embedded) |
| `LondonSkyscraper_optimized.blend` | Optimized Blender scene (textures packed) |
| `textures/` | The same textures as separate files (max 1024 px), useful for SurfaceAppearance |
| `report.json` | Per-part triangle counts, materials, texture sizes, totals |
| `CREDITS.txt` | Required CC BY 4.0 credit line |

## Structure

- `LondonSkyscraper` (root)
  - `Building`: 37 day parts named `<Section>__<MATERIAL>`, for example `Tower_Band03__FACADE`.
    Sections: `Podium` (lobby, sidewalks, 0 to 12 m), `Tower_Band01` to `Tower_Band05` (12 to 153 m in ~28 m bands),
    `Crown` (153 m and up), `Tower` (small parts spread over the full height such as the red aircraft lights).
  - `NightWindows`: 14 optional parts named `NightWindows_<Section>__<MATERIAL>_NIGHT` (see below).
- Every part has one material and at most 19,000 triangles (largest is 17,061).
- Origin: the base center of the building is at (0, 0, 0). Ground level (top of the sidewalk) is Y = 0;
  the lobby floor slab goes about 0.6 m below that.

## Importing into Roblox Studio

1. Home or Avatar tab > **Import 3D**, pick `LondonSkyscraper.glb`.
2. In the import settings, set the **file dimensions / unit to Meters** so it stays real size
   (do not let the importer rescale it; the tower should end up about 600 studs tall).
3. Keep texture/material import enabled. Insert it, then move the model so its pivot sits on your ground.
4. Select all MeshParts in the model and set:
   - `Anchored = true`
   - `CollisionFidelity = Box` (or `Hull` if players need to walk close to the curved facade). Turn
     `CanCollide` off on interior, glass, furniture and NightWindows parts; it saves a lot of physics work.
   - `RenderFidelity = Automatic` (lets Roblox drop detail on far bands).
   - `CastShadow` off on interior and NightWindows parts.
5. Streaming: enable `Workspace.StreamingEnabled`. Because the tower is split into height bands, Roblox can stream and
   LOD the bands independently. With the default `ModelStreamingMode` the upper bands may pop in as you approach.
   For a skyline landmark that must always be visible, set `ModelStreamingMode = Persistent` (costs memory on every
   client), or keep the default and raise `StreamingTargetRadius`. `Atomic` streams the whole tower in or out as one unit.

### Transparency

The facade texture has cut-out windows (alpha), so the baked interiors are visible behind the glass.
These parts import with a SurfaceAppearance whose `AlphaMode` should be **Transparency**:
`*__FACADE`, `*__GLASS*`, `*__BLINDS`, `*__LOBBY_CURTAINS`, `*__LOBBY_FURNITURE`, `*__FURNITURE`, `*__FLARE_RED`.
If a facade part looks solid after import, open its SurfaceAppearance and set `AlphaMode = Transparency`.
Glass parts only have a small tinted texture; if they come in opaque, set the part `Transparency` to about 0.6 instead.

## Night windows

Roblox SurfaceAppearance has no emissive slot, so the glowing night windows from the original model do not show up
on the normal parts. The `NightWindows` group is a workaround: it duplicates every surface that had an emissive map
(office interiors, lobby, furniture, red aircraft lights, palette props) with a material whose **base color is the
emissive (lit) texture**.

- Day: keep `NightWindows` parts hidden (`Transparency = 1`) or remove the folder entirely.
- Night: for each `NightWindows_<X>_NIGHT` part, show it and hide its day twin `<X>` (same geometry, same position;
  showing both causes z-fighting). Setting the night parts' `Material = Neon` is not needed and would wipe the texture;
  instead keep the SurfaceAppearance and, if you want extra glow, add a `PointLight`/`SurfaceLight` or a bloom effect
  in `Lighting`.
- A simple script can toggle this from `Lighting.ClockTime` (for example night between 18 and 6).

The night set adds 23,654 triangles if you keep it in the game.

## Triangle budget

| | Triangles |
|---|---|
| Source FBX | 142,785 |
| Day building (Building group) | 120,599 |
| Optional NightWindows group | 23,654 |
