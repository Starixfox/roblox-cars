# Cloud brief: finish the car conversions

This repo holds Roblox-ready car models built with headless Blender. The work was done on a Windows PC
with only 4 GB RAM (Blender jobs crashed it), so the remaining work moves to a Linux cloud session.

## Rules
- Never write text with em dashes. Use commas, colons, parentheses.
- Run ONE Blender process at a time (memory).
- Commit to a branch and push when a car is done, with a short message per car. Do not touch `main` history.

## Folder layout
- `porsche-gt3rs/` : FINISHED reference car. `scripts/prep2.py` is the reference pipeline,
  `scripts/render.py` the preview renderer, `roblox/scripts/` the SHARED Roblox damage system
  (`CarDamage.lua`, `README.md` = naming contract every car must follow).
- `bmw-m4-gt3/`, `gac-aion-ray7/`, `gac-empow/` : three cars, each with `source/` (original model),
  `scripts/` (that car's adapted pipeline, e.g. `prep.py`, `render.py`) and `roblox/` (High + Lite GLB
  already built once, plus `_report.json`). They are NOT verified yet.
- `buildings/london-skyscraper/roblox/` : finished building, no work needed.

## Step 1: Blender on Linux
Install Blender 4.2 LTS or newer (the scripts use 4.1+ APIs such as `set_sharp_from_angle`,
`corner_normals`, `surface_render_method`). Try the official Linux tarball from download.blender.org;
if network rules block it, try `apt-get install blender` and check the version; if neither works,
stop and report that clearly (the user can allow the domain in the cloud environment's network settings).
Rendering: use EEVEE if it works headless; otherwise switch previews to `BLENDER_WORKBENCH` or Cycles CPU
with low samples. Run scripts as `blender -b --factory-startup --python <script> -- <args>`.

## Step 2: port the scripts
All Python scripts hardcode Windows paths like `C:\Users\jordan\RobloxCars\...`. Replace them with
paths relative to the repo root (e.g. `ROOT = Path(__file__).resolve().parents[1]`). `run.ps1`,
`render_set.ps1` and `wrap.py` are Windows helpers: replace with a small bash runner that runs one
script, captures stdout/stderr to `<script>_<arg>.log`, and retries a render up to 3 times if the PNG
was not written.

## Step 3: finish and verify each car (one at a time: BMW, AION RAY7, empow)
For each car: rebuild High and Lite with its pipeline, then render and LOOK at:
normal front34 + rear34 (must match a render of the original), tyre/wheel close-up (no brand text),
windshield in dmg mode (visible white cracks), chunkcolors, impact simulation, `remove:` ALL detachable
groups (nothing may float that belongs to a removed panel), explode. Fix and rebuild until good.

Requirements (all cars):
- Naming contract (see `porsche-gt3rs/roblox/scripts/README.md`): unchunked `<Group>__<Material>[_k]`,
  chunked `<Group>__C<nn>__<Material>[_k]`, glass cracked twins `<Group>__C<nn>__DMG__<Material>[_k]`.
  Groups: Hood, Trunk, Door_L, Door_R, Door_RL, Door_RR (rear doors on 4-door cars), FrontBumper,
  RearBumper, Wing, Mirror_L/R, Wheel_LF/RF/LR/RR, Body_Front/Mid/Rear, Interior, SteeringWheel, Brakes,
  HeadLight_L/R, TailLight_L/R, Glass_Windshield, Glass_Rear, Glass_Door_L/R/RL/RR, Glass_Quarter_L/R.
  One material per object, at most 19,000 triangles per object.
- Car orientation: real size, front toward -Y, Z up, +X = driver's left. Wheels pivot at the hub.
- No dents. Damage = chunks break off, panels fall off, glass cracks then shatters, lights break.
- Remove ALL brand marks (logos, badges, model lettering, sponsor/livery text, tyre sidewall text in
  diffuse AND normal maps, caliper text, plate text, dashboard/screen brand text).
- High about 100k visible triangles and up to ~850 parts, Lite about 45k and up to ~600 parts.
- Bay floors under hood/trunk. Hidden-face removal only against fixed, non-glass occluders.

Lessons from the Porsche: record every matrix_world before unparenting; bound_box of new objects is stale
(use vertices); matrix_world is stale after setting location; delete vertices flung outside the original
bounds after decimation; weight paint panels higher in the triangle budget; smooth + sharp-by-angle 35 deg
+ frozen custom normals before chunk splitting; classify big multi-panel meshes per face with region boxes
plus nearest paint panel; glass: subdivide before chunking and use one planar CrackUV per window.

## Credits / licenses (keep in each car's CREDITS.txt)
- Porsche 911 GT3 RS Weissach by VTDAT23, CC BY 4.0.
- 2025 BMW M4 GT3 EVO G82 by Ddiaz Design, CC BY-NC-SA: NonCommercial (no Robux-earning game), and
  "based on a Need For Speed Mobile 3d model" (likely ripped, takedown risk). User chose to convert anyway.
- GAC AION RAY7 by GARAGISTA, CC BY 4.0.
- GAC empow by ParticleAccelerator5000, listed CC BY 4.0, but the uploader says the model is not theirs
  (license may not be valid, takedown risk). User chose to convert anyway.
- London Skyscraper by 99.Miles, CC BY 4.0.

## When done
Push the branch and open a pull request against `main` summarising, per car: triangle and part counts for
High and Lite, groups with chunk counts, brand marks removed, and any problems you could not fix.
Also move the shared damage scripts from `porsche-gt3rs/roblox/scripts/` to a top-level `damage-system/`
folder and update READMEs that point to them.
