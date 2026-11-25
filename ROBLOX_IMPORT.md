# Roblox import guide

Instructions for putting these models into the Roblox game (written for the Claude Code session on the
game PC). Nothing here has been tested in Roblox Studio yet: expect small fixes on the first run.

## Models to import (Studio: Avatar tab or File > Import 3D, choose the .glb, scale unit: meters)

| Model | High (showcase / few cars) | Lite (many cars on a server) | Credits |
|---|---|---|---|
| Porsche 911 GT3 RS | `porsche-gt3rs/roblox/GT3RS_High.glb` | `porsche-gt3rs/roblox/GT3RS_Lite.glb` | `porsche-gt3rs/roblox/CREDITS.txt` |
| BMW M4 GT3 | `bmw-m4-gt3/roblox/BMW_M4GT3_High.glb` | `bmw-m4-gt3/roblox/BMW_M4GT3_Lite.glb` | `bmw-m4-gt3/roblox/CREDITS.txt` (license warning) |
| GAC AION RAY7 | `gac-aion-ray7/roblox/GAC_AionRay7_High.glb` | `gac-aion-ray7/roblox/GAC_AionRay7_Lite.glb` | `gac-aion-ray7/roblox/CREDITS.txt` |
| GAC empow | `gac-empow/roblox/GAC_Empow_High.glb` | `gac-empow/roblox/GAC_Empow_Lite.glb` | `gac-empow/roblox/CREDITS.txt` (license warning) |
| London Skyscraper | `buildings/london-skyscraper/roblox/LondonSkyscraper.glb` | (one version) | `buildings/london-skyscraper/roblox/CREDITS.txt` |

Do NOT import `porsche-gt3rs/roblox/GT3RS_Roblox.glb` or `.fbx`: that is the first Porsche version without
damage parts. Cars are real size (about 4.5 to 5 m, roughly 16 to 18 studs long).

## Damage system (shared by all four cars)

Scripts: `porsche-gt3rs/roblox/scripts/` (full setup steps in its `README.md`).

1. Put `CarDamage.lua` in ServerScriptService as a ModuleScript named `CarDamage`, and
   `CarDamageServer.server.lua` as a Script.
2. Import a car, select its Model, paste `StudioSetup_CommandBar.lua` into the Studio command bar and run it.
   It sets collision and render fidelity, glass transparency (AlphaMode), hides the cracked-glass twins and
   tags the model `DamageCar`. Run it once per imported car.
3. Make the car drivable with your chassis (A-Chassis or your own). Wheel meshes are groups `Wheel_LF`,
   `Wheel_RF`, `Wheel_LR`, `Wheel_RR` with their pivot at the hub; see the README for wheel hookup.
4. Guns: call `CarDamage.ApplyBulletHit(hitPart, hitPosition, hitNormal)` from server-side raycasts
   (example in `GunHookExample.lua`).
5. Test: crash into a wall, shoot glass and panels, then call `CarDamage.Repair(car)`.

Part names follow `<Group>__<Material>` or `<Group>__C<nn>__<Material>` (chunks) and
`<Group>__C<nn>__DMG__<Material>` (cracked glass). The scripts find parts by these names, so if Import 3D
renames parts (for example drops the double underscores), the damage system will not find them: check the
Output window summary printed by the command-bar setup.

Groups per car: all cars have Hood, Trunk, Door_L, Door_R, FrontBumper, RearBumper, Mirror_L/R, Wheel_*,
Body_Front/Mid/Rear, Interior, SteeringWheel, Brakes, HeadLight_L/R, TailLight_L/R and glass groups.
Porsche and BMW also have Wing. AION RAY7 and empow also have rear doors (Door_RL, Door_RR with
Glass_Door_RL/RR) and a panoramic Glass_Roof.

## Skyscraper

Anchored = true, CollisionFidelity Box or Hull. It includes a separate NightWindows set: at night hide the
day window parts and show the NightWindows ones (see `buildings/london-skyscraper/roblox/README.md`).

## Credits (required by the licenses)

Put the credit lines from each CREDITS.txt in the game description or an in-game credits screen.
BMW: NonCommercial license and likely based on a ripped game model (do not use in a game that earns Robux).
empow: the uploader says the model is not theirs (license may not be valid).
