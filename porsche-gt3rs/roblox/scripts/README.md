# CarDamage: per-piece vehicle damage for Roblox emergency roleplay

Server-side damage system for the GT3 RS model (and any car that follows the same part naming). Panels and glass are pre-fractured into chunks and break piece by piece where they are hit.

What damage looks like:

- **Local damage:** every bullet, crash and explosion has a point in the world. Chunks near that point take damage, chunks further away do not.
- **Panel and body chunks break loose** as debris at 0 health, leaving a hole in the panel.
- **Glass cracks** on any damage (bullets and crashes), and the crack spreads to neighbouring chunks. A glass chunk at 0 bursts into a few small shards and leaves a hole. When most of a window is gone, the rest bursts too.
- **Detachable groups fall off whole** (Hood, Trunk, doors, bumpers, wing) once too few of their chunks remain. Body zones (`Body_Front`, `Body_Mid`, `Body_Rear`) only lose chunks, they never fall off whole.
- **Wheels and mirrors** have one health value each and fall off whole. **Lights break** (go dark).
- **Bullet holes** stick to the chunk that was hit and leave with it. Shot tyres pop.
- **Sparks** on crashes, **engine smoke** (grey, then black) and **fire** at low overall Health.
- There are no dents.

> Status: written without access to Roblox Studio and **not tested in Studio yet**. Expect to fix small things on the first run. Check the Output window for `[CarDamage]` warnings.

## Files

| File | Type | Where |
|---|---|---|
| `CarDamage.lua` | ModuleScript named `CarDamage` | ServerScriptService (or ServerStorage) |
| `CarDamageServer.server.lua` | Script named `CarDamageServer` | ServerScriptService |
| `StudioSetup_CommandBar.lua` | Paste into the command bar once | (not a game script) |
| `GunHookExample.lua` | Script, example only | ServerScriptService |

## 1. Part naming

MeshParts can be anywhere under the car Model (flattened or in sub-Models). Names are split on `__`:

```
<Group>__C<nn>__<Material>[_k]          chunk part        Hood__C03__CarPaint_flake
<Group>__C<nn>__DMG__<Material>[_k]     cracked glass     Glass_Windshield__C17__DMG__EXT_GLASS
<Group>__<Material>[_k]                 unchunked part    Wheel_LF__Tyre, HeadLight_L__EXT_GLASS_1
```

- A segment like `C03` right after the group is the chunk id. Several MeshParts (one per material) with the same id form one chunk.
- Chunked groups: `Hood, Trunk, Door_L, Door_R, FrontBumper, RearBumper, Wing, Body_Front, Body_Mid, Body_Rear` and all `Glass_*`.
- Unchunked groups: `Wheel_*, Mirror_*, Interior, SteeringWheel, Brakes, HeadLight_*, TailLight_*`.
- Only glass has `DMG` twins. A twin is matched to its chunk part by chunk id + material. The crack texture is mapped across the whole window, so cracked chunks line up into one pattern.
- `Mirror_*` and `Glass_Door_*` ride on their door and leave with it.
- A chunked group exported without chunk ids (for example in a Lite model) is treated as one big chunk, so it still works. Missing groups are fine.

## 2. Import and one-time Studio setup

1. Studio: **Home > Import 3D**, pick the `.glb`, import as a Model. Keep the part names.
2. Select the imported Model in the Explorer.
3. **View > Command Bar**, paste all of `StudioSetup_CommandBar.lua`, press Enter. On every `<Group>__` MeshPart (other MeshParts, such as chassis parts, are left alone) it sets:
   - `CollisionFidelity = Box` for chunk parts (cheap physics when they fall) and `Hull` for the rest,
   - `RenderFidelity = Automatic`, `CanCollide = false`, `CanTouch = false`, `CanQuery = true`, `Massless = true`, `Anchored = false`,
   - `SurfaceAppearance.AlphaMode = Transparency` on all `Glass_*` parts.

   It also hides DMG parts (`Transparency = 1`, `CanQuery = false`), tags the model `DamageCar`, and prints every group with its chunk and part counts, DMG parts without a twin, and missing groups.
   These properties can only be set in Studio, so the game scripts cannot do this step.
4. Put `CarDamage` and `CarDamageServer` in ServerScriptService.
5. Add a chassis (section 3). Body parts do not collide and are massless: the chassis provides the physics.
6. Optional, recommended: give the car Model a string attribute `DamageTemplateKey` (for example `GT3RS_High`). Every spawned copy then shares one set of repair templates instead of copying ~700 parts per car. Use a different key per variant (`GT3RS_Lite`).

`CarDamageServer` sets up every Model tagged `DamageCar` in Workspace, also cars cloned in later. It waits 1 second (`SETUP_DELAY`) so the chassis script can initialise first.

## 3. How it is welded, and chassis integration

At setup every group gets an invisible, non-colliding, massless anchor Part (`CD_Anchor_<Group>`) at its centre. Chunk parts weld to their chunk's largest part, each chunk welds to the group anchor, and the anchor welds to its parent group's anchor (mirrors, door glass) or to the root. Losing any chunk never leaves the others hanging. When a chunk or group breaks off, **every** joint between it and the rest of the car is destroyed (WeldConstraint, Weld, ManualWeld, Motor6D, constraints), so it also works when A-Chassis made its own welds.

The root part is picked in this order: `model.PrimaryPart` (unless it is a chunk or detachable part), a part named `DriveSeat`, any `VehicleSeat`, else the largest safe part. Pass your own with `CarDamage.Setup(model, rootPart)` if needed.

The car's front, left and up directions come from part positions (windshield / headlights vs taillights / wing, Door_L vs Door_R), so the import orientation does not matter. The car should be upright when it is set up.

### A-Chassis

- Put A-Chassis (`Body`, `Wheels`, `DriveSeat`, ...) in the car Model as usual.
- Body MeshParts can go anywhere in A-Chassis `Body`; names are what matters.
- Put each `Wheel_XX__*` MeshPart into the matching A-Chassis wheel's `Parts` model (`FL`, `FR`, `RL`, `RR`) so it spins with the wheel. The wheel's anchor is also welded to the physical wheel named in `Config.PhysicalWheels`.
- When a visual wheel falls off, its physical wheel gets `CanCollide = false` (the car drops onto that corner) and the attribute `WheelLost_<group> = true` is set.
- Shot tyre: the physical wheel's friction is multiplied by `PoppedTireFriction`. Newer A-Chassis versions recalculate wheel friction while driving and may undo this. For a reliable flat, listen to `TirePopped` and change your tune values.
- Turn the engine off on `Wrecked` (for example set A-Chassis `IsOn` to false).

### Custom chassis

- Any root part works. Rename `Config.PhysicalWheels` to match your wheel parts, or leave it: without a physical wheel only the visual wheel falls off.
- If your chassis already joins the visual wheels to its own wheel parts, CarDamage does not weld them to the root at setup. After Repair, rebuilt wheels are welded to the root, so re-run your wheel welding then if needed (listen to `HealthChanged(100)`).

## 4. Events and attributes

Folder `DamageEvents` under each car, with BindableEvents:

| Event | Arguments |
|---|---|
| `HealthChanged` | `newHealth` (0..100) |
| `ChunkBroken` | `groupName, chunkId` (panel chunk broke loose, or glass chunk burst) |
| `PartDetached` | `groupName` (a door also fires for its mirror and glass) |
| `GlassShattered` | `groupName` (the whole remaining window burst) |
| `TirePopped` | `groupName` |
| `Wrecked` | none, once when Health <= `WreckedAt` |

Attributes on the car Model: `Health`, `Wrecked`, `DamageCarId`, `Health_<Group>` (0..100 percent of that group), `TirePopped_<Wheel>`, `WheelLost_<Wheel>`.

Overall `Health` is the weighted average of every group's remaining health (chunked groups: sum of chunk health; detached groups count as 0). Weights are in `Config.Groups`.

## 5. Guns

All hits are decided on the server. See `GunHookExample.lua`: the client sends its aim point, the server checks the shooter, raycasts itself from the character's head and calls:

```lua
CarDamage.ApplyBulletHit(result.Instance, result.Position, result.Normal, damage) -- damage optional
```

- The chunk that was hit always takes full damage; chunks within `BulletChunkRadius` (1 stud) take less.
- Panels take `BulletDamage` (6, so about 7 shots to knock out a 40 hp panel chunk). Glass takes `GlassBulletDamage` (40): the first shot cracks the chunk and its neighbours, a second shot nearby holes it. With your own `damage`, glass gets `damage * GlassBulletDamage / BulletDamage`.
- Bullet holes are welded to the hit part, at most `MaxBulletHoles` (40) per car.
- Hitting a part with `Tyre` or `Tire` in its material name in a `Wheel_*` group pops that tyre.

Other server scripts can use the BindableFunction instead of `require`:

```lua
local api = game:GetService("ServerStorage"):WaitForChild("CarDamageAPI")
api:Invoke("BulletHit", hitPart, hitPos, hitNormal)
api:Invoke("ImpactAt", carModel, worldPos, direction, 60)
api:Invoke("Explosion", carModel, position, 20, 150)
api:Invoke("Repair", carModel)
```

## 6. Public API

```lua
CarDamage.Setup(carModel, rootPart?)                          -- done for you by CarDamageServer
CarDamage.ApplyBulletHit(hitPart, hitPosition, hitNormal, damage?)
CarDamage.ApplyImpactAt(car, worldPos, direction, amount, radius?) -- crash-style local hit (radius default CrashChunkRadius)
CarDamage.ApplyDamage(car, groupName, amount, direction?)     -- chunked group: every remaining chunk takes amount
CarDamage.ApplyExplosion(car, position, radius, damage)       -- linear falloff over chunks and groups
CarDamage.Detach(car, groupName)                              -- detachable groups only
CarDamage.Shatter(car, groupName)                             -- bursts all remaining chunks of a Glass_* group
CarDamage.Repair(car)
CarDamage.GetHealth(car), GetGroupHealth(car), GetChunkHealth(car, groupName), GetEvents(car)
CarDamage.Remove(carModel)                                    -- automatic on Destroy
CarDamage.AssignCharacter(character)                          -- automatic when AssignCharacterGroup = true
```

`car` can be the car Model, any part inside it, or the record returned by `Setup`.

## 7. Crashes

One Heartbeat connection for all cars samples each root's `AssemblyLinearVelocity`. A velocity change above `ImpactThreshold` (28 studs/s) within `ImpactWindow` (0.15 s) is a crash:

1. The obstacle direction is the opposite of the velocity change.
2. A ray is cast from outside the car bounds back toward the centre, only against the car's own visible parts, to find the real surface point (falls back to the bounding box estimate if it misses).
3. Chunks and groups within `CrashChunkRadius` (3.5 studs) of that point take `(dv - threshold) * DamageScale` with linear falloff. Glass within `CrackSpreadRadius` cracks.
4. Sparks and the optional crash sound play at that point.

Ignored: changes above `TeleportThreshold` (400), the first `SpawnGrace` seconds after setup or repair, and anchored cars. Vertical changes are scaled by `VerticalImpactFactor` so jump landings hurt less.

## 8. Tuning (`CarDamage.Config`)

| Setting | Default | Effect |
|---|---|---|
| `PanelChunkHealth` / `BodyChunkHealth` / `GlassChunkHealth` | 40 / 70 / 60 | health of one chunk (override per group with `ChunkHealth`) |
| `GroupDetachAt` | 0.45 | detachable groups fall off whole below this fraction of intact chunks |
| `GlassCrackAt` | 0.99 | glass chunk shows its cracked twin once health <= this fraction |
| `GlassShatterAt` | 0.35 | whole window bursts below this fraction of intact chunks (0 = never) |
| `CrashChunkRadius` | 3.5 | crash damage radius around the impact point |
| `BulletChunkRadius` | 1 | bullet splash radius (hit chunk always takes full damage) |
| `CrackSpreadRadius` / `CrackSpreadDamage` | 2 / 1 | how far cracks spread around any hit |
| `ImpactThreshold` / `DamageScale` | 28 / 1.5 | crash sensitivity and strength |
| `BulletDamage` / `GlassBulletDamage` | 6 / 40 | default weapon damage |
| `Groups.<Name>.MaxHealth` | varies | health of unchunked groups (wheels, mirrors, lights) |
| `Groups.<Name>.Weight` | varies | share of overall Health |
| `WreckedAt` | 0 | Health at which `Wrecked` fires; raise (for example 10) to wreck sooner |
| `SmokeBelow` / `HeavySmokeBelow` / `FireBelow` | 45 / 20 / 8 | effect thresholds |
| `MaxLooseChunks` / `ChunkLifetime` | 40 / 30 | loose chunk cap per car (oldest removed first) and lifetime |
| `DebrisLifetime` | 60 | seconds a whole fallen group stays |
| `GlassChunkShardsMin/Max`, `GlassShatterMaxShards` | 2 / 5, 30 | shard counts |
| `MaxBulletHoles` | 40 | per car |
| `SoundIds` | all `""` | your own `rbxassetid://` ids, empty = silent |

Change config before cars spawn, or edit the table at the top of `CarDamage.lua`:

```lua
local CarDamage = require(game.ServerScriptService.CarDamage)
CarDamage.Config.GlassChunkHealth = 45
CarDamage.Config.SoundIds.GlassShatter = "rbxassetid://YOUR_ID"
```

Debris uses collision group `CarDebris`, which does not collide with player characters (moved into `Characters`) or with other debris. If your game already has a character collision group, set `CharacterCollisionGroup` to its name and `AssignCharacterGroup = false`.

## 9. Repair

```lua
CarDamage.Repair(carModel)
```

Destroys the car's debris and loose chunks, rebuilds every missing chunk and fallen group from the pristine templates in `ServerStorage/CarDamageTemplates/<key>` at its original position relative to the current root, recreates missing anchors, rebuilds the welds of every affected group, resets all chunk and group health, unhides burst glass, swaps cracked glass back, restores lights, removes bullet holes, smoke and fire, re-enables the physical wheels and their friction, clears `Wrecked` and fires `HealthChanged(100)`. Hook it to a mechanic tool or repair zone (check permissions on the server).

## 10. Performance notes

- The High model has roughly 600 to 900 MeshParts. Setup walks them once: chunk centres are precomputed in root-local space, and every hit transforms one point and loops over the car's chunk array once (no per-hit searching).
- Per frame the only work is one velocity sample per car (no allocations).
- Setup cost grows with part count: templates are cloned once per car, or once per `DamageTemplateKey` when shared. Use the key when you spawn many identical cars.
- Loose chunks are capped per car (`MaxLooseChunks`) and despawn after `ChunkLifetime`. Glass shards live 6 to 10 s. Debris does not collide with other debris.
- The crash raycast filter list is rebuilt only after something broke off, not every crash.
- The Lite model has fewer chunks (or none: an unchunked panel acts as one chunk), so it is cheaper in every way. Use it for traffic or far-away cars.
- Chunk parts use Box collision (set by the command bar step), so falling chunks are cheap for the physics engine.

## 11. Known limits

- Not tested in Studio yet.
- `ApplyDamage` on a chunked group hits every remaining chunk at once (it has no hit point); use `ApplyImpactAt` for local damage.
- Glass that bursts disappears and shards spawn instead; glass chunks never fall as big rigid pieces (on purpose).
- No hood "fly up" before it falls off.
- Broken lights park their SurfaceAppearance and clear TextureID so the darker colour shows; Repair restores both.
- A car moved out of Workspace and back keeps its damage state; destroying the car cleans everything up.
