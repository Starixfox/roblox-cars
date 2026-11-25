--!nonstrict
--[[
	CarDamage (ModuleScript)
	Server-side, per-piece vehicle damage for emergency / police roleplay cars.
	Put this ModuleScript in ServerScriptService or ServerStorage. Server only.

	Part naming (MeshParts anywhere under the car Model, split on "__"):
		<Group>__C<nn>__<Material>[_k]           chunk part (several materials can share one chunk id)
		<Group>__C<nn>__DMG__<Material>[_k]      cracked twin of that chunk (glass only)
		<Group>__<Material>[_k]                  unchunked part (wheels, mirrors, lights, interior, ...)

	Damage model:
		- Panels, body zones and glass are pre-fractured into chunks. Every chunk has its own health.
		- Damage is local: every hit has a world point; chunks near it take damage with distance falloff.
		- Panel / body chunks at 0 break loose as debris. Glass chunks crack on any damage (and cracks
		  spread to neighbours), at 0 they burst into a few shards and leave a hole.
		- Detachable groups (Hood, Trunk, Doors, Bumpers, Wing) fall off whole once too few chunks remain.
		- Wheels and mirrors use group health and fall off whole. Lights break. Body zones never fall off whole.
		- Bullet holes, tyre pops, sparks, engine smoke and fire, Wrecked.

	Public API (car = the car Model, any descendant of it, or the record returned by Setup):
		CarDamage.Setup(carModel, rootPart?) -> car record (or nil)
		CarDamage.Remove(carModel) / CarDamage.IsSetup(carModel)
		CarDamage.ApplyBulletHit(hitPart, hitPosition, hitNormal, damage?) -> boolean
		CarDamage.ApplyImpactAt(car, worldPos, direction, amount, radius?) -> boolean
		CarDamage.ApplyDamage(car, groupName, amount, direction?) -> boolean
		CarDamage.ApplyExplosion(car, position, radius, damage) -> boolean
		CarDamage.Detach(car, groupName) / CarDamage.Shatter(car, groupName) -> boolean
		CarDamage.Repair(car) -> boolean
		CarDamage.GetHealth(car), GetGroupHealth(car), GetChunkHealth(car, groupName), GetEvents(car)
		CarDamage.AssignCharacter(character) -> RBXScriptConnection
		CarDamage.Config
]]

local RunService = game:GetService("RunService")
local PhysicsService = game:GetService("PhysicsService")
local ServerStorage = game:GetService("ServerStorage")
local Debris = game:GetService("Debris")
local HttpService = game:GetService("HttpService")

if RunService:IsClient() then
	error("CarDamage must only be required on the server")
end

------------------------------------------------------------------------
-- CONFIG
------------------------------------------------------------------------
local Config = {
	-- Chunk health per group type (Groups.<Name>.Chunked = "Panel" | "Body" | "Glass")
	PanelChunkHealth = 40,
	BodyChunkHealth = 70,
	GlassChunkHealth = 60,

	-- Thresholds
	GlassCrackAt = 0.99, -- a glass chunk shows its cracked twin once health <= this fraction (0.99 = any hit)
	GlassShatterAt = 0.35, -- a whole window bursts once its intact chunk fraction drops below this (0 = never)
	GroupDetachAt = 0.45, -- detachable chunked groups fall off whole below this intact chunk fraction
	WreckedAt = 0, -- Wrecked fires once overall Health <= this value (0..100). Raise it to wreck sooner.

	-- Local damage radii (studs, measured from the hit point to chunk centres)
	CrashChunkRadius = 3.5,
	BulletChunkRadius = 1, -- the directly hit chunk always takes full damage
	CrackSpreadRadius = 2, -- glass chunks this close to any hit crack (tiny damage)
	CrackSpreadDamage = 1,

	-- Collision impacts (from the root part's velocity history)
	ImpactThreshold = 28, -- studs/s of velocity change over ImpactWindow before a crash counts
	ImpactWindow = 0.15,
	ImpactCooldown = 0.25,
	DamageScale = 1.5, -- crash damage at the impact point = (dv - ImpactThreshold) * DamageScale
	VerticalImpactFactor = 0.35, -- scales the vertical part of dv so landing from a jump hurts less
	TeleportThreshold = 400, -- dv above this is a teleport and is ignored
	SpawnGrace = 2, -- seconds after Setup / Repair with no crash damage

	-- Weapons
	BulletDamage = 6,
	GlassBulletDamage = 40, -- vs GlassChunkHealth 60: first shot cracks, second shot on the same spot holes it
	MaxBulletHoles = 40, -- bullet holes + crack marks per car, oldest removed first
	PoppedTireFriction = 0.35,

	-- Debris
	DebrisLifetime = 60, -- seconds a whole detached group stays
	ChunkLifetime = 30, -- seconds a loose panel chunk stays
	MaxLooseChunks = 40, -- per car, oldest loose chunk is removed first
	DebrisCollisionGroup = "CarDebris",
	CharacterCollisionGroup = "Characters", -- debris never collides with this group
	AssignCharacterGroup = true, -- CarDamageServer puts player characters into CharacterCollisionGroup
	DebrisCollidesWithDebris = false,
	DebrisKickMin = 15, -- whole groups
	DebrisKickMax = 35,
	DebrisUpKickMin = 5,
	DebrisUpKickMax = 12,
	ChunkKickMin = 6, -- single chunks
	ChunkKickMax = 18,

	-- Glass shards
	GlassChunkShardsMin = 2,
	GlassChunkShardsMax = 5,
	GlassShatterMaxShards = 30, -- cap for a whole-window burst
	ShardLifetimeMin = 6,
	ShardLifetimeMax = 10,
	ShardColor = Color3.fromRGB(196, 210, 220),

	-- Effects by overall Health (0..100)
	Effects = { Sparks = true, Smoke = true, Fire = true },
	SmokeBelow = 45,
	HeavySmokeBelow = 20,
	FireBelow = 8,
	-- Texture that ships inside the Roblox client (not an uploaded asset). "" = ParticleEmitter default.
	SmokeTexture = "rbxasset://textures/particles/smoke_main.dds",

	-- Sounds: your own uploaded audio as "rbxassetid://<id>". Empty string = no sound.
	SoundIds = {
		Crash = "",
		GlassShatter = "",
		PartFall = "",
	},
	SoundVolume = 0.8,

	-- Visual wheel group -> chassis physical wheel part name (searched anywhere under the car)
	PhysicalWheels = { Wheel_LF = "FL", Wheel_RF = "FR", Wheel_LR = "RL", Wheel_RR = "RR" },

	-- Per group settings
	--   Chunked     "Panel" | "Body" | "Glass": group made of chunks (a group exported without chunks
	--               becomes one big chunk, so Lite models still work)
	--   ChunkHealth optional override of the type's chunk health
	--   MaxHealth   health of an unchunked group
	--   Weight      share of overall car Health (0 = ignored)
	--   Detachable  falls off whole (chunked: below GroupDetachAt, unchunked: at 0 health)
	--   Parent      group it rides on (leaves together with the parent)
	--   Light, Immune (ignored by damage), ImpactMult (crash damage multiplier)
	DefaultGroup = { MaxHealth = 100, Weight = 0.5 },
	Groups = {
		Hood = { Chunked = "Panel", Weight = 1.5, Detachable = true },
		Trunk = { Chunked = "Panel", Weight = 2.5, Detachable = true }, -- rear engine cover
		Door_L = { Chunked = "Panel", Weight = 1, Detachable = true },
		Door_R = { Chunked = "Panel", Weight = 1, Detachable = true },
		Door_RL = { Chunked = "Panel", Weight = 1, Detachable = true }, -- rear doors on 4-door cars
		Door_RR = { Chunked = "Panel", Weight = 1, Detachable = true },
		FrontBumper = { Chunked = "Panel", Weight = 1, Detachable = true },
		RearBumper = { Chunked = "Panel", Weight = 1, Detachable = true },
		Wing = { Chunked = "Panel", Weight = 0.5, Detachable = true },
		Body_Front = { Chunked = "Body", Weight = 3 },
		Body_Mid = { Chunked = "Body", Weight = 3 },
		Body_Rear = { Chunked = "Body", Weight = 3 },

		Glass_Windshield = { Chunked = "Glass", Weight = 0.4, ImpactMult = 1.2 },
		Glass_Rear = { Chunked = "Glass", Weight = 0.3, ImpactMult = 1.2 },
		Glass_Quarter_L = { Chunked = "Glass", Weight = 0.15, ImpactMult = 1.2 },
		Glass_Quarter_R = { Chunked = "Glass", Weight = 0.15, ImpactMult = 1.2 },
		Glass_Door_L = { Chunked = "Glass", Weight = 0.2, ImpactMult = 1.2, Parent = "Door_L" },
		Glass_Door_R = { Chunked = "Glass", Weight = 0.2, ImpactMult = 1.2, Parent = "Door_R" },
		Glass_Roof = { Chunked = "Glass", Weight = 0.3 }, -- panoramic glass roof (fixed)
		Glass_Door_RL = { Chunked = "Glass", Weight = 0.2, ImpactMult = 1.2, Parent = "Door_RL" },
		Glass_Door_RR = { Chunked = "Glass", Weight = 0.2, ImpactMult = 1.2, Parent = "Door_RR" },

		Mirror_L = { MaxHealth = 25, Weight = 0.1, Detachable = true, Parent = "Door_L" },
		Mirror_R = { MaxHealth = 25, Weight = 0.1, Detachable = true, Parent = "Door_R" },
		Wheel_LF = { MaxHealth = 160, Weight = 1, Detachable = true, ImpactMult = 0.5 },
		Wheel_RF = { MaxHealth = 160, Weight = 1, Detachable = true, ImpactMult = 0.5 },
		Wheel_LR = { MaxHealth = 160, Weight = 1, Detachable = true, ImpactMult = 0.5 },
		Wheel_RR = { MaxHealth = 160, Weight = 1, Detachable = true, ImpactMult = 0.5 },
		HeadLight_L = { MaxHealth = 18, Weight = 0.2, Light = true },
		HeadLight_R = { MaxHealth = 18, Weight = 0.2, Light = true },
		TailLight_L = { MaxHealth = 18, Weight = 0.2, Light = true },
		TailLight_R = { MaxHealth = 18, Weight = 0.2, Light = true },
		Interior = { MaxHealth = 100, Weight = 0, Immune = true },
		SteeringWheel = { MaxHealth = 100, Weight = 0, Immune = true },
		Brakes = { MaxHealth = 100, Weight = 0, Immune = true },
	},
}

local CarDamage = {}
CarDamage.Config = Config

------------------------------------------------------------------------
-- STATE
------------------------------------------------------------------------
local FX_ATTR = "CarDamageFX" -- bullet holes / crack marks
local ANCHOR_ATTR = "CarDamageAnchor" -- invisible group anchors created by Setup
local HIST = 32
local EVENT_NAMES = { "HealthChanged", "PartDetached", "GlassShattered", "TirePopped", "Wrecked", "ChunkBroken" }
local IMPLICIT_CHUNK = "C00"

local FRONT_GROUPS = { "Glass_Windshield", "HeadLight_L", "HeadLight_R", "FrontBumper", "Hood" }
local REAR_GROUPS = { "TailLight_L", "TailLight_R", "Wing", "RearBumper", "Trunk", "Glass_Rear" }
local LEFT_GROUPS = { "Door_L", "Door_RL", "Mirror_L", "HeadLight_L", "TailLight_L", "Wheel_LF", "Wheel_LR", "Glass_Door_L", "Glass_Door_RL", "Glass_Quarter_L" }
local RIGHT_GROUPS = { "Door_R", "Door_RR", "Mirror_R", "HeadLight_R", "TailLight_R", "Wheel_RF", "Wheel_RR", "Glass_Door_R", "Glass_Door_RR", "Glass_Quarter_R" }

local registry = {} -- [Model] = car
local carCount = 0
local heartbeatConn: RBXScriptConnection? = nil
local collisionReady = false
local templateStores = {} -- [key] = { folder = Folder, byName = {[string]: BasePart}, refs = number }
local rng = Random.new()

------------------------------------------------------------------------
-- HELPERS
------------------------------------------------------------------------
local function splitName(name: string): { string }
	local segs = {}
	local start = 1
	while true do
		local i = string.find(name, "__", start, true)
		if not i then
			table.insert(segs, string.sub(name, start))
			return segs
		end
		table.insert(segs, string.sub(name, start, i - 1))
		start = i + 2
	end
end

-- Returns group, chunkId (or nil), isDmg, materialKey
local function parseName(name: string): (string?, string?, boolean, string)
	if not string.find(name, "__", 1, true) then
		return nil, nil, false, ""
	end
	local segs = splitName(name)
	local group = segs[1]
	if group == "" or #segs < 2 then
		return nil, nil, false, ""
	end
	local idx = 2
	local chunkId = nil
	if #segs >= 3 and string.match(segs[2], "^C%d+$") then
		chunkId = segs[2]
		idx = 3
	end
	local isDmg = false
	if segs[idx] == "DMG" then
		isDmg = true
		idx += 1
	end
	return group, chunkId, isDmg, table.concat(segs, "__", idx)
end

local function groupDef(name: string)
	return Config.Groups[name] or Config.DefaultGroup
end

local function volume(p: BasePart): number
	local s = p.Size
	return s.X * s.Y * s.Z
end

local function isJointLike(d: Instance): boolean
	return d:IsA("JointInstance") or d:IsA("WeldConstraint") or d:IsA("NoCollisionConstraint") or d:IsA("Constraint")
end

local function jointParts(j: Instance): (BasePart?, BasePart?)
	if j:IsA("JointInstance") or j:IsA("WeldConstraint") or j:IsA("NoCollisionConstraint") then
		return (j :: any).Part0, (j :: any).Part1
	elseif j:IsA("Constraint") then
		local a0 = (j :: any).Attachment0
		local a1 = (j :: any).Attachment1
		local p0 = a0 and a0.Parent
		local p1 = a1 and a1.Parent
		return (p0 and p0:IsA("BasePart")) and p0 or nil, (p1 and p1:IsA("BasePart")) and p1 or nil
	end
	return nil, nil
end

-- Destroys every joint linking the set to anything outside it (keeps internal joints and bullet hole welds)
local function cutExternalJoints(set)
	for p in set do
		for _, j in p:GetJoints() do
			local a, b = jointParts(j)
			local other = if a == p then b else a
			if not (other and (set[other] or other:GetAttribute(FX_ATTR))) then
				j:Destroy()
			end
		end
	end
end

local function makeWeld(a: BasePart, b: BasePart): WeldConstraint
	local w = Instance.new("WeldConstraint")
	w.Name = "CD_Weld"
	w.Part0 = a
	w.Part1 = b
	w.Parent = a
	return w
end

local function inModel(car, p: Instance?): boolean
	return p ~= nil and p.Parent ~= nil and p:IsDescendantOf(car.model)
end

local function ensureCollisionGroups()
	if collisionReady then
		return
	end
	collisionReady = true
	local ok, err = pcall(function()
		for _, name in { Config.DebrisCollisionGroup, Config.CharacterCollisionGroup } do
			if not PhysicsService:IsCollisionGroupRegistered(name) then
				PhysicsService:RegisterCollisionGroup(name)
			end
		end
		PhysicsService:CollisionGroupSetCollidable(Config.DebrisCollisionGroup, Config.CharacterCollisionGroup, false)
		PhysicsService:CollisionGroupSetCollidable(
			Config.DebrisCollisionGroup,
			Config.DebrisCollisionGroup,
			Config.DebrisCollidesWithDebris
		)
	end)
	if not ok then
		warn("[CarDamage] Collision group setup failed: " .. tostring(err))
	end
end

local function getDebrisFolder(): Folder
	local f = workspace:FindFirstChild("CarDebris")
	if not (f and f:IsA("Folder")) then
		f = Instance.new("Folder")
		f.Name = "CarDebris"
		f.Parent = workspace
	end
	return f
end

local function playSound(id: string?, parent: Instance?, volumeScale: number?)
	if not id or id == "" or not parent or not parent.Parent then
		return
	end
	local s = Instance.new("Sound")
	s.SoundId = id
	s.Volume = Config.SoundVolume * (volumeScale or 1)
	s.RollOffMaxDistance = 200
	s.Parent = parent
	s:Play()
	Debris:AddItem(s, 6)
end

local function carWorldCF(car): CFrame
	return car.root.CFrame * car.frame
end

local function findCar(inst: Instance?)
	local node = inst
	while node do
		local car = registry[node]
		if car then
			return car
		end
		node = node.Parent
	end
	return nil
end

local function resolveCar(ref)
	if type(ref) == "table" and ref.model then
		return registry[ref.model]
	end
	if typeof(ref) == "Instance" then
		return findCar(ref)
	end
	return nil
end

local function resetHistory(car, now: number, v: Vector3)
	car.histHead = 1
	car.histCount = 1
	car.histT[1] = now
	car.histV[1] = v
end

-- Horizontal direction from the car centre to a root-local point, blended with an optional force direction
local function outwardDir(car, centerRoot: Vector3, forceDir: Vector3?): (Vector3, Vector3)
	local cf = carWorldCF(car)
	local up = cf.UpVector
	local w = car.root.CFrame:PointToWorldSpace(centerRoot) - cf.Position
	w -= up * w:Dot(up)
	local out = if w.Magnitude > 0.05 then w.Unit else rng:NextUnitVector()
	if forceDir and forceDir.Magnitude > 1e-3 then
		out = (out + forceDir.Unit * 0.5).Unit
	end
	return out, up
end

local function groupFrac(g): number
	if g.detached then
		return 0
	end
	if g.chunked then
		return if g.hMax > 0 then math.clamp(g.hSum / g.hMax, 0, 1) else 1
	end
	return math.clamp(g.health / g.maxHealth, 0, 1)
end

------------------------------------------------------------------------
-- VISUALS: cracks, lights, marks, sparks, shards
------------------------------------------------------------------------
local function crackChunk(c)
	c.cracked = true
	if #c.dmg == 0 then
		return
	end
	for _, i in c.dmg do
		local p = i.part
		if p.Parent then
			p.Transparency = i.showT
			p.CanQuery = true
		end
	end
	for _, i in c.normal do
		local p = i.part
		if i.counterpart and p.Parent then
			p.Transparency = 1
			p.CanQuery = false
		end
	end
end

local function breakLight(g)
	g.broken = true
	table.clear(g.lightStates)
	table.clear(g.saStates)
	for _, i in g.parts do
		local p = i.part
		if p.Parent then
			for _, d in p:GetDescendants() do
				if d:IsA("Light") then
					table.insert(g.lightStates, { light = d, enabled = d.Enabled })
					d.Enabled = false
				elseif d:IsA("SurfaceAppearance") then
					-- SurfaceAppearance overrides Color/Material, so park it while broken
					table.insert(g.saStates, { sa = d, parent = d.Parent })
					d.Parent = nil
				end
			end
			p.Material = Enum.Material.SmoothPlastic
			p.Color = i.color:Lerp(Color3.new(0, 0, 0), 0.65)
			if p:IsA("MeshPart") and p.TextureID ~= "" then
				i.textureId = p.TextureID
				pcall(function()
					p.TextureID = ""
				end)
			end
		end
	end
end

local function restoreLight(g)
	for _, i in g.parts do
		local p = i.part
		if p.Parent then
			p.Material = i.material
			p.Color = i.color
			if i.textureId and p:IsA("MeshPart") then
				local tex = i.textureId
				pcall(function()
					p.TextureID = tex
				end)
			end
		end
		i.textureId = nil
	end
	for _, s in g.saStates do
		if s.parent and s.parent.Parent then
			s.sa.Parent = s.parent
		end
	end
	for _, s in g.lightStates do
		if s.light.Parent then
			s.light.Enabled = s.enabled
		end
	end
	table.clear(g.saStates)
	table.clear(g.lightStates)
	g.broken = false
end

-- Thin cylinder (bullet hole or glass crack mark) parented and welded to the hit part, so it leaves with it
local function makeMark(car, hitPart: BasePart, pos: Vector3, normal: Vector3, diameter: number, thickness: number, color: Color3, transparency: number)
	local n = if normal.Magnitude > 1e-3 then normal.Unit else Vector3.yAxis
	local upHint = if math.abs(n.Y) > 0.99 then Vector3.xAxis else Vector3.yAxis
	local p0 = pos + n * (thickness * 0.3)
	local mark = Instance.new("Part")
	mark.Name = "CD_Mark"
	mark.Shape = Enum.PartType.Cylinder
	mark.Size = Vector3.new(thickness, diameter, diameter)
	-- lookAt puts -Z along the normal; rotating 90 deg about Y moves the cylinder axis (local X) onto it
	mark.CFrame = CFrame.lookAt(p0, p0 + n, upHint) * CFrame.Angles(0, math.rad(90), 0)
	mark.Anchored = false
	mark.CanCollide = false
	mark.CanQuery = false
	mark.CanTouch = false
	mark.Massless = true
	mark.CastShadow = false
	mark.Material = Enum.Material.SmoothPlastic
	mark.Color = color
	mark.Transparency = transparency
	mark:SetAttribute(FX_ATTR, true)
	mark.Parent = hitPart
	makeWeld(mark, hitPart)
	local marks = car.marks
	table.insert(marks, mark)
	while #marks > Config.MaxBulletHoles do
		local old = table.remove(marks, 1)
		if old then
			old:Destroy()
		end
	end
end

local function destroyMarks(p: BasePart)
	for _, c in p:GetChildren() do
		if c:GetAttribute(FX_ATTR) then
			c:Destroy()
		end
	end
end

local function spawnImpactFx(car, worldPos: Vector3, outward: Vector3, severity: number)
	local wantSparks = Config.Effects.Sparks
	local soundId = Config.SoundIds.Crash
	if not wantSparks and soundId == "" then
		return
	end
	local root = car.root
	local n = if outward.Magnitude > 1e-3 then outward.Unit else Vector3.yAxis
	local upHint = if math.abs(n.Y) > 0.99 then Vector3.xAxis else Vector3.yAxis
	local att = Instance.new("Attachment")
	att.Name = "CD_Impact"
	att.Parent = root
	att.CFrame = root.CFrame:ToObjectSpace(CFrame.lookAt(worldPos, worldPos + n, upHint))
	if wantSparks then
		local pe = Instance.new("ParticleEmitter")
		pe.Enabled = false
		pe.Color = ColorSequence.new(Color3.fromRGB(255, 170, 60), Color3.fromRGB(255, 90, 20))
		pe.LightEmission = 1
		pe.Lifetime = NumberRange.new(0.2, 0.5)
		pe.Speed = NumberRange.new(15, 30)
		pe.SpreadAngle = Vector2.new(60, 60)
		pe.Acceleration = Vector3.new(0, -40, 0)
		pe.Drag = 2
		pe.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.2), NumberSequenceKeypoint.new(1, 0) })
		pe.EmissionDirection = Enum.NormalId.Front -- attachment -Z = outward
		pe.Parent = att
		pe:Emit(20)
	end
	playSound(soundId, att, math.clamp(severity / 40, 0.3, 1))
	Debris:AddItem(att, if soundId ~= "" then 4 else 2)
end

local function spawnShards(car, sources: { BasePart }, count: number, dir: Vector3)
	if #sources == 0 or count <= 0 then
		return
	end
	local folder = getDebrisFolder()
	local carVel = car.root.AssemblyLinearVelocity
	for _ = 1, count do
		local src = sources[rng:NextInteger(1, #sources)]
		local s = src.Size
		local offset = Vector3.new(
			rng:NextNumber(-0.5, 0.5) * s.X,
			rng:NextNumber(-0.5, 0.5) * s.Y,
			rng:NextNumber(-0.5, 0.5) * s.Z
		)
		local shard = if rng:NextNumber() < 0.5 then Instance.new("WedgePart") else Instance.new("Part")
		shard.Name = "GlassShard"
		shard.Size = Vector3.new(rng:NextNumber(0.15, 0.6), rng:NextNumber(0.05, 0.12), rng:NextNumber(0.15, 0.6))
		shard.CFrame = src.CFrame
			* CFrame.new(offset)
			* CFrame.Angles(rng:NextNumber(0, 6.28), rng:NextNumber(0, 6.28), rng:NextNumber(0, 6.28))
		shard.Material = Enum.Material.Glass
		shard.Transparency = 0.3
		shard.Color = Config.ShardColor
		shard.Anchored = false
		shard.CanCollide = true
		shard.CanTouch = false
		shard.CanQuery = false
		shard.CastShadow = false
		shard.CollisionGroup = Config.DebrisCollisionGroup
		shard.Parent = folder
		shard.AssemblyLinearVelocity = carVel + dir * rng:NextNumber(4, 12) + rng:NextUnitVector() * rng:NextNumber(1, 5)
		shard.AssemblyAngularVelocity = rng:NextUnitVector() * rng:NextNumber(5, 15)
		Debris:AddItem(shard, rng:NextNumber(Config.ShardLifetimeMin, Config.ShardLifetimeMax))
	end
end

------------------------------------------------------------------------
-- ENGINE SMOKE / FIRE + OVERALL HEALTH
------------------------------------------------------------------------
local function destroyEffects(car)
	if car.fx then
		car.fx.att:Destroy()
		car.fx = nil
	end
end

local function updateEffects(car)
	local h = car.health
	local E = Config.Effects
	local wantSmoke = E.Smoke and h <= Config.SmokeBelow
	local wantFire = E.Fire and h <= Config.FireBelow
	local fx = car.fx
	if not wantSmoke and not wantFire then
		if fx then
			if fx.smoke then
				fx.smoke.Enabled = false
			end
			if fx.fire then
				fx.fire.Enabled = false
			end
		end
		return
	end
	if not fx then
		local att = Instance.new("Attachment")
		att.Name = "CD_EngineFx"
		att.CFrame = car.frame * CFrame.new(car.enginePos)
		att.Parent = car.root
		fx = { att = att, smoke = nil, fire = nil, heavy = nil }
		car.fx = fx
	end
	if wantSmoke and not fx.smoke then
		local pe = Instance.new("ParticleEmitter")
		pe.Name = "CD_Smoke"
		if Config.SmokeTexture ~= "" then
			pe.Texture = Config.SmokeTexture
		end
		pe.Lifetime = NumberRange.new(2, 4)
		pe.Speed = NumberRange.new(2, 4)
		pe.SpreadAngle = Vector2.new(20, 20)
		pe.Acceleration = Vector3.new(0, 2, 0)
		pe.Rotation = NumberRange.new(0, 360)
		pe.RotSpeed = NumberRange.new(-30, 30)
		pe.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.4), NumberSequenceKeypoint.new(1, 1) })
		pe.EmissionDirection = Enum.NormalId.Top
		pe.Parent = fx.att
		fx.smoke = pe
	end
	if fx.smoke then
		fx.smoke.Enabled = wantSmoke
		local heavy = h <= Config.HeavySmokeBelow
		if fx.heavy ~= heavy then
			fx.heavy = heavy
			local s = fx.smoke
			if heavy then
				s.Color = ColorSequence.new(Color3.fromRGB(25, 25, 25))
				s.Rate = 28
				s.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 1.5), NumberSequenceKeypoint.new(1, 7) })
			else
				s.Color = ColorSequence.new(Color3.fromRGB(150, 150, 150))
				s.Rate = 12
				s.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 1), NumberSequenceKeypoint.new(1, 4) })
			end
		end
	end
	if wantFire and not fx.fire then
		local fire = Instance.new("Fire")
		fire.Name = "CD_Fire"
		fire.Size = 6
		fire.Heat = 9
		fire.Parent = fx.att
		fx.fire = fire
	end
	if fx.fire then
		fx.fire.Enabled = wantFire
	end
end

-- Flushes group attributes and recomputes overall Health (O(groups), called once per damage operation)
local function recomputeHealth(car)
	local sumW, sum = 0, 0
	local model = car.model
	for _, g in car.order do
		local f = groupFrac(g)
		if g.attrDirty then
			g.attrDirty = false
			model:SetAttribute("Health_" .. g.attrName, math.floor(f * 100 + 0.5))
		end
		if g.weight > 0 then
			sumW += g.weight
			sum += g.weight * f
		end
	end
	local h = if sumW > 0 then (sum / sumW) * 100 else 100
	h = math.floor(h * 10 + 0.5) / 10
	if h == car.health then
		return
	end
	car.health = h
	model:SetAttribute("Health", h)
	car.events.HealthChanged:Fire(h)
	updateEffects(car)
	if not car.wrecked and h <= Config.WreckedAt then
		car.wrecked = true
		model:SetAttribute("Wrecked", true)
		car.events.Wrecked:Fire()
	end
end

------------------------------------------------------------------------
-- DEBRIS / DETACH
------------------------------------------------------------------------
local function launchDebris(car, name: string, set, lead: BasePart?, kick: Vector3, spin: number, lifetime: number): Model
	local dm = Instance.new("Model")
	dm.Name = name
	dm:SetAttribute("DamageCarId", car.id)
	for p in set do
		p.Anchored = false
		p.CanTouch = false
		p.Massless = false
		local visible = p.Transparency < 1
		p.CanCollide = visible
		p.CanQuery = visible
		p.CollisionGroup = Config.DebrisCollisionGroup
		p.Parent = dm
	end
	dm.Parent = getDebrisFolder()
	if lead and lead.Parent == dm then
		dm.PrimaryPart = lead
		pcall(function()
			lead:SetNetworkOwner(nil)
		end)
		lead.AssemblyLinearVelocity = car.root.AssemblyLinearVelocity + kick
		lead.AssemblyAngularVelocity = rng:NextUnitVector() * spin
		playSound(Config.SoundIds.PartFall, lead, 1)
	end
	Debris:AddItem(dm, lifetime)
	return dm
end

local function collectDetachSet(car, g, out)
	table.insert(out, g)
	for _, childName in g.children do
		local c = car.groups[childName]
		if c and not c.detached then
			collectDetachSet(car, c, out)
		end
	end
end

local function detachGroup(car, g, forceDir: Vector3?): boolean
	if g.detached then
		return false
	end
	local list = {}
	collectDetachSet(car, g, list)
	local set = {}
	for _, gg in list do
		if inModel(car, gg.anchor) then
			set[gg.anchor] = true
		end
		for _, i in gg.parts do
			if inModel(car, i.part) then
				set[i.part] = true -- loose chunks already left the model, hidden glass chunks go along
			end
		end
	end
	if set[car.root] then
		warn("[CarDamage] Refusing to detach " .. g.name .. ": it contains the root part")
		return false
	end
	cutExternalJoints(set)
	local out, up = outwardDir(car, g.center, forceDir)
	local kick = out * rng:NextNumber(Config.DebrisKickMin, Config.DebrisKickMax)
		+ up * rng:NextNumber(Config.DebrisUpKickMin, Config.DebrisUpKickMax)
	local dm = launchDebris(car, car.model.Name .. "_" .. g.name, set, g.anchor, kick, rng:NextNumber(2, 8), Config.DebrisLifetime)
	table.insert(car.debris, dm)

	for _, gg in list do
		gg.detached = true
		gg.attrDirty = true
		local pw = car.physWheels[gg.name]
		if pw and pw.part.Parent then
			pw.part.CanCollide = false
		end
		if gg.isWheel then
			car.model:SetAttribute("WheelLost_" .. gg.attrName, true)
		end
		car.events.PartDetached:Fire(gg.name)
	end
	car.queryDirty = true
	return true
end

local function breakChunkLoose(car, c, forceDir: Vector3?)
	local g = c.group
	c.broken = true
	c.health = 0
	g.intact -= 1
	local set = {}
	local lead = nil
	for _, i in c.parts do
		if inModel(car, i.part) then
			set[i.part] = true
			lead = lead or i.part
		end
	end
	if c.lead and set[c.lead.part] then
		lead = c.lead.part
	end
	if lead then
		cutExternalJoints(set)
		local out, up = outwardDir(car, c.center, forceDir)
		local kick = out * rng:NextNumber(Config.ChunkKickMin, Config.ChunkKickMax) + up * rng:NextNumber(2, 8)
		local dm = launchDebris(car, g.name .. "_" .. c.id, set, lead, kick, rng:NextNumber(4, 12), Config.ChunkLifetime)
		local loose = car.loose
		table.insert(loose, dm)
		while #loose > Config.MaxLooseChunks do
			local old = table.remove(loose, 1)
			if old and old.Parent then
				old:Destroy()
			end
		end
	end
	car.queryDirty = true
	car.events.ChunkBroken:Fire(g.name, c.id)
end

local function breakGlassChunk(car, c, forceDir: Vector3?, shardCount: number?, silent: boolean)
	local g = c.group
	c.broken = true
	c.health = 0
	g.intact -= 1
	local sources = {}
	for _, i in c.parts do
		local p = i.part
		if p.Parent and p.Transparency < 1 then
			table.insert(sources, p)
		end
	end
	local dir = forceDir
	if not dir or dir.Magnitude < 1e-3 then
		dir = outwardDir(car, c.center, nil)
	end
	spawnShards(car, sources, shardCount or rng:NextInteger(Config.GlassChunkShardsMin, Config.GlassChunkShardsMax), dir.Unit)
	for _, i in c.parts do
		local p = i.part
		if p.Parent then
			p.Transparency = 1
			p.CanQuery = false
			p.CanCollide = false
			destroyMarks(p)
		end
	end
	if not silent then
		playSound(Config.SoundIds.GlassShatter, sources[1], 0.6)
	end
	car.queryDirty = true
	car.events.ChunkBroken:Fire(g.name, c.id)
end

local function shatterGroup(car, g, forceDir: Vector3?)
	if g.shattered or g.detached then
		return
	end
	g.shattered = true
	local per = if g.intact > 0
		then math.clamp(math.floor(Config.GlassShatterMaxShards / g.intact), 1, Config.GlassChunkShardsMax)
		else 0
	local soundPart = nil
	for _, c in g.chunks do
		if not c.broken then
			soundPart = soundPart or (c.lead and c.lead.part)
			g.hSum -= c.health
			breakGlassChunk(car, c, forceDir, per, true)
		end
	end
	g.hSum = math.max(0, g.hSum)
	g.attrDirty = true
	playSound(Config.SoundIds.GlassShatter, soundPart, 1)
	car.events.GlassShattered:Fire(g.name)
end

------------------------------------------------------------------------
-- DAMAGE CORE (callers run recomputeHealth once afterwards)
------------------------------------------------------------------------
local function damageChunk(car, c, amount: number, forceDir: Vector3?)
	local g = c.group
	if amount <= 0 or c.broken or g.detached then
		return
	end
	local before = c.health
	c.health = math.max(0, before - amount)
	g.hSum -= before - c.health
	g.attrDirty = true

	if g.isGlass then
		if c.health <= 0 then
			breakGlassChunk(car, c, forceDir, nil, false)
			if g.total > 0 and g.intact / g.total < Config.GlassShatterAt then
				shatterGroup(car, g, forceDir)
			end
		elseif not c.cracked and c.health <= c.maxHealth * Config.GlassCrackAt then
			crackChunk(c)
		end
	elseif c.health <= 0 then
		if g.detachable and g.total > 0 and (g.intact - 1) / g.total < Config.GroupDetachAt then
			-- the last chunk that drops the group below GroupDetachAt leaves together with the group
			c.broken = true
			g.intact -= 1
			car.events.ChunkBroken:Fire(g.name, c.id)
			detachGroup(car, g, forceDir)
		else
			breakChunkLoose(car, c, forceDir)
		end
	end
end

local function damageGroup(car, g, amount: number, forceDir: Vector3?)
	if amount <= 0 or g.detached or g.immune then
		return
	end
	g.health = math.max(0, g.health - amount)
	g.attrDirty = true
	if g.isLight and g.health <= 0 and not g.broken then
		breakLight(g)
	end
	if g.detachable and g.health <= 0 then
		detachGroup(car, g, forceDir)
	end
end

local function popTire(car, g)
	if car.tires[g.name] then
		return
	end
	car.tires[g.name] = true
	car.model:SetAttribute("TirePopped_" .. g.attrName, true)
	local pw = car.physWheels[g.name]
	if pw and pw.part.Parent then
		local base = pw.props or PhysicalProperties.new(pw.part.Material)
		pw.part.CustomPhysicalProperties = PhysicalProperties.new(
			base.Density,
			base.Friction * Config.PoppedTireFriction,
			base.Elasticity,
			base.FrictionWeight,
			base.ElasticityWeight
		)
	end
	car.events.TirePopped:Fire(g.name)
end

-- Local damage around a world point. One pass over the car's chunk array and one over unchunked groups.
local function hitAt(car, worldPos: Vector3, amount: number, glassAmount: number, radius: number, forceDir: Vector3?, directPart: BasePart?, useImpactMult: boolean)
	local localPos = car.root.CFrame:PointToObjectSpace(worldPos)
	local entry = directPart and car.partMap[directPart]
	local directChunk = entry and entry.chunk
	local directGroup = if entry and not entry.chunk and not entry.group.immune then entry.group else nil
	local crackR = Config.CrackSpreadRadius
	local hitAny = directChunk ~= nil or directGroup ~= nil
	local nearestC, nearestCD = nil, math.huge

	for _, c in car.chunks do
		local g = c.group
		if not c.broken and not g.detached then
			local d = (c.center - localPos).Magnitude - c.radius * 0.5
			if d < 0 then
				d = 0
			end
			local base = if g.isGlass then glassAmount else amount
			if useImpactMult then
				base *= g.impactMult
			end
			if c == directChunk then
				damageChunk(car, c, base, forceDir)
			elseif d < radius then
				hitAny = true
				damageChunk(car, c, base * (1 - d / radius), forceDir)
			elseif g.isGlass and d < crackR then
				damageChunk(car, c, Config.CrackSpreadDamage, forceDir) -- spreading crack
			elseif d < nearestCD then
				nearestC, nearestCD = c, d
			end
		end
	end

	local nearestG, nearestGD = nil, math.huge
	for _, g in car.plainGroups do
		if not g.detached then
			local d = (g.center - localPos).Magnitude - g.radius * 0.5
			if d < 0 then
				d = 0
			end
			local base = if useImpactMult then amount * g.impactMult else amount
			if g == directGroup then
				damageGroup(car, g, base, forceDir)
			elseif d < radius then
				hitAny = true
				damageGroup(car, g, base * (1 - d / radius), forceDir)
			elseif d < nearestGD then
				nearestG, nearestGD = g, d
			end
		end
	end

	if not hitAny then
		if nearestC and nearestCD <= nearestGD then
			damageChunk(car, nearestC, (if nearestC.group.isGlass then glassAmount else amount) * 0.5, forceDir)
		elseif nearestG then
			damageGroup(car, nearestG, amount * 0.5, forceDir)
		end
	end
end

local function getQueryParams(car): RaycastParams
	if car.queryDirty then
		local list = {}
		for _, g in car.order do
			if not g.detached then
				for _, i in g.parts do
					local c = i.chunk
					if not (c and c.broken) and i.part.Parent then
						table.insert(list, i.part)
					end
				end
			end
		end
		car.queryParams.FilterDescendantsInstances = list
		car.queryDirty = false
	end
	return car.queryParams
end

local function handleImpact(car, dvWorld: Vector3, severity: number)
	local root = car.root
	if not root.Parent then
		return
	end
	local cf = carWorldCF(car)
	local dvLocal = cf:VectorToObjectSpace(dvWorld)
	if dvLocal.Magnitude < 1e-3 then
		return
	end
	-- The obstacle is opposite to the change in velocity
	local dir = -dvLocal.Unit
	local he = car.halfExtents
	local m = math.max(math.abs(dir.X) / he.X, math.abs(dir.Y) / he.Y, math.abs(dir.Z) / he.Z)
	if m <= 0 then
		return
	end
	local dirWorld = cf:VectorToWorldSpace(dir)
	local point = cf:PointToWorldSpace(dir / m) -- bounding box estimate
	local normal = dirWorld
	-- Find the real surface: ray from outside the bounds back toward the centre, only against our parts
	local reach = he.Magnitude + 2
	local result = workspace:Raycast(cf.Position + dirWorld * reach, -dirWorld * reach, getQueryParams(car))
	if result then
		point = result.Position
		normal = result.Normal
	end
	local amount = severity * Config.DamageScale
	hitAt(car, point, amount, amount, Config.CrashChunkRadius, -dirWorld, nil, true)
	spawnImpactFx(car, point, normal, severity)
	recomputeHealth(car)
end

------------------------------------------------------------------------
-- HEARTBEAT (one connection for all cars, no per-frame allocations)
------------------------------------------------------------------------
local function onHeartbeat()
	local now = os.clock()
	local window = Config.ImpactWindow
	for _, car in registry do
		local root = car.root
		if root.Parent == nil then
			continue
		end
		local v = root.AssemblyLinearVelocity
		if root.Anchored then
			resetHistory(car, now, v)
			continue
		end
		local head = car.histHead % HIST + 1
		car.histHead = head
		car.histT[head] = now
		car.histV[head] = v
		if car.histCount < HIST then
			car.histCount += 1
		end
		if now < car.graceUntil or now - car.lastImpact < Config.ImpactCooldown then
			continue
		end
		local oldV = v
		local found = false
		for k = 1, car.histCount - 1 do
			local j = head - k
			if j < 1 then
				j += HIST
			end
			if now - car.histT[j] > window then
				break
			end
			oldV = car.histV[j]
			found = true
		end
		if not found then
			continue
		end
		local dv = v - oldV
		if dv.Magnitude > Config.TeleportThreshold then
			resetHistory(car, now, v)
			continue
		end
		local scaled = Vector3.new(dv.X, dv.Y * Config.VerticalImpactFactor, dv.Z)
		local mag = scaled.Magnitude
		if mag > Config.ImpactThreshold then
			car.lastImpact = now
			resetHistory(car, now, v)
			task.spawn(handleImpact, car, scaled, mag - Config.ImpactThreshold)
		end
	end
end

------------------------------------------------------------------------
-- SETUP HELPERS
------------------------------------------------------------------------
local function riskyRoot(p: BasePart): boolean
	local gname = parseName(p.Name)
	if not gname then
		return false
	end
	local def = groupDef(gname)
	return def.Detachable == true or def.Parent ~= nil or def.Chunked ~= nil
end

local function pickRoot(model: Model): BasePart?
	local pp = model.PrimaryPart
	if pp and not riskyRoot(pp) then
		return pp
	end
	local ds = model:FindFirstChild("DriveSeat", true)
	if ds and ds:IsA("BasePart") then
		return ds
	end
	local largest, bestV = nil, -1
	for _, d in model:GetDescendants() do
		if d:IsA("VehicleSeat") then
			return d
		end
		if d:IsA("BasePart") and not riskyRoot(d) and not d:GetAttribute(ANCHOR_ATTR) then
			local v = volume(d)
			if v > bestV then
				largest, bestV = d, v
			end
		end
	end
	return largest
end

local function newGroup(name: string)
	local def = groupDef(name)
	local maxH = def.MaxHealth or 100
	return {
		name = name,
		-- SetAttribute errors on names with anything but letters, digits and "_" (e.g. "Body.001")
		attrName = (string.gsub(name, "[^%w_]", "_")),
		chunkType = def.Chunked,
		chunked = false,
		chunks = {},
		chunkById = {},
		parts = {},
		normal = {},
		maxHealth = maxH,
		health = maxH,
		weight = def.Weight or 0.5,
		detachable = def.Detachable == true,
		isGlass = def.Chunked == "Glass" or string.sub(name, 1, 6) == "Glass_",
		isLight = def.Light == true,
		isWheel = string.sub(name, 1, 6) == "Wheel_",
		immune = def.Immune == true,
		impactMult = def.ImpactMult or 1,
		parentName = def.Parent,
		children = {},
		anchor = nil,
		anchorRel = CFrame.identity,
		anchorRelPhys = nil,
		welds = {},
		center = Vector3.zero,
		radius = 0,
		intact = 0,
		total = 0,
		hSum = 0,
		hMax = 0,
		detached = false,
		shattered = false,
		broken = false,
		chassisHandled = false,
		needsTemplate = false,
		attrDirty = true,
		lightStates = {},
		saStates = {},
	}
end

local function chunkHealthFor(g): number
	local def = groupDef(g.name)
	if def.ChunkHealth then
		return def.ChunkHealth
	end
	if g.isGlass then
		return Config.GlassChunkHealth
	elseif g.chunkType == "Body" then
		return Config.BodyChunkHealth
	end
	return Config.PanelChunkHealth
end

-- Root-local centre and rough radius of a list of PartInfos
local function centerAndRadius(root: BasePart, infos): (Vector3, number)
	local sum, n = Vector3.zero, 0
	for _, i in infos do
		sum += i.part.Position
		n += 1
	end
	if n == 0 then
		return Vector3.zero, 0
	end
	local cw = sum / n
	local r = 0
	for _, i in infos do
		r = math.max(r, (i.part.Position - cw).Magnitude + i.part.Size.Magnitude * 0.5)
	end
	return root.CFrame:PointToObjectSpace(cw), r
end

local function avgCenter(groups, names): Vector3?
	local sum, n = Vector3.zero, 0
	for _, nm in names do
		local g = groups[nm]
		if g then
			for _, i in g.normal do
				sum += i.part.Position
				n += 1
			end
		end
	end
	if n == 0 then
		return nil
	end
	return sum / n
end

-- Car frame (LookVector = front, RightVector = right, UpVector = up) derived from part positions
local function computeFrame(groups, root: BasePart)
	local worldUp = Vector3.yAxis
	local front, rear = avgCenter(groups, FRONT_GROUPS), avgCenter(groups, REAR_GROUPS)
	local left, right = avgCenter(groups, LEFT_GROUPS), avgCenter(groups, RIGHT_GROUPS)
	local fwd, up = nil, nil

	if front and rear and (front - rear).Magnitude > 0.1 then
		fwd = (front - rear).Unit
		if left and right then
			local lr = right - left
			lr -= fwd * lr:Dot(fwd)
			if lr.Magnitude > 0.1 then
				local u = lr.Unit:Cross(fwd) -- right x forward = up
				if u:Dot(worldUp) > 0.3 then
					up = u
				else
					warn("[CarDamage] Left/right groups look mirrored or the car is not upright; using world up")
				end
			end
		end
		if not up then
			local f = fwd - worldUp * fwd:Dot(worldUp)
			if f.Magnitude > 0.05 then
				fwd = f.Unit
				up = worldUp
			else
				fwd = nil
			end
		end
	end
	if not fwd and left and right then
		local r = right - left
		r -= worldUp * r:Dot(worldUp)
		if r.Magnitude > 0.1 then
			up = worldUp
			fwd = worldUp:Cross(r.Unit) -- up x right = forward
		end
	end
	if not fwd then
		warn("[CarDamage] Could not derive orientation from part names; using root LookVector")
		local f = root.CFrame.LookVector
		f -= worldUp * f:Dot(worldUp)
		fwd = if f.Magnitude > 0.05 then f.Unit else Vector3.new(0, 0, -1)
		up = worldUp
	end

	local rightVec = fwd:Cross(up).Unit
	up = rightVec:Cross(fwd).Unit
	local rot = CFrame.fromMatrix(Vector3.zero, rightVec, up)

	local mn = Vector3.new(math.huge, math.huge, math.huge)
	local mx = -mn
	for _, g in groups do
		for _, i in g.normal do
			local p = i.part
			local pcf, hs = p.CFrame, p.Size * 0.5
			for sx = -1, 1, 2 do
				for sy = -1, 1, 2 do
					for sz = -1, 1, 2 do
						local c = rot:PointToObjectSpace(pcf:PointToWorldSpace(Vector3.new(sx * hs.X, sy * hs.Y, sz * hs.Z)))
						mn = Vector3.new(math.min(mn.X, c.X), math.min(mn.Y, c.Y), math.min(mn.Z, c.Z))
						mx = Vector3.new(math.max(mx.X, c.X), math.max(mx.Y, c.Y), math.max(mx.Z, c.Z))
					end
				end
			end
		end
	end
	if mn.X == math.huge then
		return nil, nil, nil
	end
	local he = (mx - mn) * 0.5
	he = Vector3.new(math.max(he.X, 0.5), math.max(he.Y, 0.5), math.max(he.Z, 0.5))
	local carWorld = CFrame.fromMatrix(rot:PointToWorldSpace((mn + mx) * 0.5), rightVec, up)
	return root.CFrame:ToObjectSpace(carWorld), he, carWorld
end

local function findPhysical(model: Model, name: string, partMap): BasePart?
	for _, d in model:GetDescendants() do
		if d.Name == name and d:IsA("BasePart") and not partMap[d] then
			return d
		end
	end
	return nil
end

local function hasExternalJoint(g): boolean
	local set = {}
	for _, i in g.parts do
		set[i.part] = true
	end
	for _, i in g.parts do
		for _, j in i.part:GetJoints() do
			local a, b = jointParts(j)
			local other = if a == i.part then b else a
			if other and not set[other] then
				return true
			end
		end
	end
	return false
end

local function createAnchor(car, g, cf: CFrame): BasePart
	local a = Instance.new("Part")
	a.Name = "CD_Anchor_" .. g.name
	a.Size = Vector3.new(0.2, 0.2, 0.2)
	a.Transparency = 1
	a.CanCollide = false
	a.CanQuery = false
	a.CanTouch = false
	a.CastShadow = false
	a.Massless = true
	a.Anchored = false
	a.CFrame = cf
	a:SetAttribute(ANCHOR_ATTR, true)
	a.Parent = car.model
	return a
end

-- Chunk parts weld to their chunk lead, leads (or unchunked parts) weld to the group anchor,
-- the anchor welds to its parent group anchor, physical wheel or root.
local function weldGroup(car, g, isRepair: boolean)
	for _, w in g.welds do
		if w.Parent then
			w:Destroy()
		end
	end
	table.clear(g.welds)
	local anchor = g.anchor
	if not inModel(car, anchor) then
		return
	end
	local welds = g.welds
	if g.chunked then
		for _, c in g.chunks do
			local lead = c.lead and c.lead.part
			if inModel(car, lead) then
				for _, i in c.parts do
					if i.part ~= lead and inModel(car, i.part) then
						table.insert(welds, makeWeld(i.part, lead))
					end
				end
				table.insert(welds, makeWeld(lead, anchor))
			end
		end
	else
		for _, i in g.parts do
			if inModel(car, i.part) then
				table.insert(welds, makeWeld(i.part, anchor))
			end
		end
	end
	local target = nil
	local parentGroup = g.parentName and car.groups[g.parentName]
	local pw = car.physWheels[g.name]
	if parentGroup and inModel(car, parentGroup.anchor) then
		target = parentGroup.anchor
	elseif pw and pw.part.Parent then
		target = pw.part
	elseif g.chassisHandled and not isRepair then
		target = nil -- the chassis already joined this wheel to its own wheel assembly
	else
		target = car.root
	end
	if target then
		table.insert(welds, makeWeld(anchor, target))
	end
end

local function getEvents(model: Model)
	local folder = model:FindFirstChild("DamageEvents")
	if not (folder and folder:IsA("Folder")) then
		folder = Instance.new("Folder")
		folder.Name = "DamageEvents"
		folder.Parent = model
	end
	local ev = {}
	for _, n in EVENT_NAMES do
		local e = folder:FindFirstChild(n)
		if not (e and e:IsA("BindableEvent")) then
			e = Instance.new("BindableEvent")
			e.Name = n
			e.Parent = folder
		end
		ev[n] = e
	end
	return ev
end

local function stripClone(c: Instance)
	for _, d in c:GetDescendants() do
		if isJointLike(d) or d:GetAttribute(FX_ATTR) then
			d:Destroy()
		end
	end
end

-- Pristine copies of every part that can leave the car. Cars with the same "DamageTemplateKey"
-- attribute share one set (big memory saving with many identical cars).
local function acquireTemplates(model: Model, id: string, infos): string
	local names, dup = {}, false
	for _, i in infos do
		if names[i.name] then
			dup = true
		end
		names[i.name] = true
	end
	local key = model:GetAttribute("DamageTemplateKey")
	local shared = typeof(key) == "string" and key ~= "" and not dup
	if dup and typeof(key) == "string" then
		warn("[CarDamage] Duplicate part names in " .. model.Name .. ": templates not shared")
	end
	if not shared then
		key = id
	end
	local root = ServerStorage:FindFirstChild("CarDamageTemplates")
	if not root then
		root = Instance.new("Folder")
		root.Name = "CarDamageTemplates"
		root.Parent = ServerStorage
	end
	local store = templateStores[key]
	local fresh = store == nil
	if fresh then
		local folder = Instance.new("Folder")
		folder.Name = key
		folder.Parent = root
		store = { folder = folder, byName = {}, refs = 0 }
		templateStores[key] = store
	end
	store.refs += 1
	local missing = 0
	for _, i in infos do
		if fresh then
			local p = i.part
			local wasArchivable = p.Archivable
			p.Archivable = true
			local c = p:Clone()
			p.Archivable = wasArchivable
			if c then
				stripClone(c)
				c.Parent = store.folder
				if shared then
					store.byName[i.name] = c
				end
				i.template = c
			end
		else
			i.template = store.byName[i.name]
		end
		if not i.template then
			missing += 1
		end
	end
	if missing > 0 then
		warn(("[CarDamage] %d parts of %s have no template (Repair skips them). Use a different DamageTemplateKey per model variant."):format(missing, model.Name))
	end
	return key
end

local function releaseTemplates(key: string?)
	local store = key and templateStores[key]
	if not store then
		return
	end
	store.refs -= 1
	if store.refs <= 0 then
		store.folder:Destroy()
		templateStores[key] = nil
	end
end

------------------------------------------------------------------------
-- PUBLIC: SETUP / REMOVE
------------------------------------------------------------------------
function CarDamage.Setup(model: Model, rootPart: BasePart?)
	assert(typeof(model) == "Instance" and model:IsA("Model"), "CarDamage.Setup expects a Model")
	if registry[model] then
		return registry[model]
	end
	-- Leftovers from an earlier Setup on this model (e.g. a cloned, already set up car)
	for _, d in model:GetDescendants() do
		if
			(d:IsA("BasePart") and (d:GetAttribute(ANCHOR_ATTR) or d:GetAttribute(FX_ATTR)))
			or (d:IsA("WeldConstraint") and d.Name == "CD_Weld")
		then
			d:Destroy()
		end
	end
	local root = rootPart or pickRoot(model)
	if not root then
		warn("[CarDamage] " .. model:GetFullName() .. " has no usable root part")
		return nil
	end
	ensureCollisionGroups()

	-- 1. Collect parts
	local groups, partMap, allInfos = {}, {}, {}
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") and d ~= root and not d:GetAttribute(FX_ATTR) then
			local gname, chunkId, isDmg, key = parseName(d.Name)
			if gname then
				local g = groups[gname]
				if not g then
					g = newGroup(gname)
					groups[gname] = g
				end
				local lowerKey = string.lower(key)
				local info = {
					part = d,
					name = d.Name,
					group = g,
					chunk = nil,
					rawChunkId = chunkId,
					isDmg = isDmg,
					key = key,
					relCF = root.CFrame:ToObjectSpace(d.CFrame),
					showT = d.Transparency,
					canQuery = d.CanQuery,
					canCollide = d.CanCollide,
					color = d.Color,
					material = d.Material,
					parent = d.Parent,
					template = nil,
					counterpart = nil,
					relPhys = nil,
					textureId = nil,
					isTyre = string.find(lowerKey, "tyre", 1, true) ~= nil or string.find(lowerKey, "tire", 1, true) ~= nil,
				}
				table.insert(g.parts, info)
				if not isDmg then
					table.insert(g.normal, info)
				end
				table.insert(allInfos, info)
			end
		end
	end
	if #allInfos == 0 then
		warn("[CarDamage] No <Group>__... parts found under " .. model:GetFullName())
		return nil
	end
	-- REVIEW: Import 3D can parent node children under a MeshPart. A part that moves into debris takes its
	-- child parts with it (and templates would clone them twice), so warn if the hierarchy is nested.
	for _, info in allInfos do
		if info.parent and info.parent:IsA("BasePart") then
			warn("[CarDamage] " .. info.name .. " is parented to part " .. info.parent.Name .. "; move car MeshParts into Models/Folders so chunks break off cleanly")
			break
		end
	end

	-- 2. Chunks, DMG twins, centres
	local allChunks, plainGroups = {}, {}
	for _, g in groups do
		local anyChunkId = false
		for _, i in g.parts do
			if i.rawChunkId then
				anyChunkId = true
				break
			end
		end
		g.chunked = g.chunkType ~= nil or anyChunkId
		if g.chunked then
			local hp = chunkHealthFor(g)
			for _, i in g.parts do
				local cid = i.rawChunkId or IMPLICIT_CHUNK
				local c = g.chunkById[cid]
				if not c then
					c = { id = cid, group = g, parts = {}, normal = {}, dmg = {}, lead = nil, maxHealth = hp, health = hp, center = Vector3.zero, radius = 0, broken = false, cracked = false }
					g.chunkById[cid] = c
					table.insert(g.chunks, c)
				end
				i.chunk = c
				table.insert(c.parts, i)
				table.insert(if i.isDmg then c.dmg else c.normal, i)
			end
			table.sort(g.chunks, function(a, b)
				return a.id < b.id
			end)
			for _, c in g.chunks do
				local byKey, byBase = {}, {}
				for _, n in c.normal do
					byKey[n.key] = n
					-- fallback key without the "_k" suffix, in case the importer numbered twins differently
					local base = string.gsub(n.key, "_%d+$", "")
					if byBase[base] == nil then
						byBase[base] = n
					else
						byBase[base] = false -- ambiguous, exact match only
					end
				end
				for _, dm in c.dmg do
					local n = byKey[dm.key]
					if not n then
						local cand = byBase[(string.gsub(dm.key, "_%d+$", ""))]
						if cand and not cand.counterpart then
							n = cand
						end
					end
					dm.counterpart = n
					if n then
						n.counterpart = dm
					end
					local attr = dm.part:GetAttribute("CD_ShowTransparency")
					-- REVIEW: the twin uses the normal part's transparency even when the command bar saved the
					-- twin's own original (CD_ShowTransparency). Swap the first two branches if cracks look wrong.
					if n then
						dm.showT = n.showT
					elseif typeof(attr) == "number" then
						dm.showT = attr
					elseif dm.part.Transparency < 1 then
						dm.showT = dm.part.Transparency
					else
						dm.showT = 0
					end
					dm.canQuery = true
				end
				local pool = if #c.normal > 0 then c.normal else c.dmg
				local best, bestV = nil, -1
				for _, i in pool do
					local v = volume(i.part)
					if v > bestV then
						best, bestV = i, v
					end
				end
				c.lead = best
				c.center, c.radius = centerAndRadius(root, pool)
				g.hMax += c.maxHealth
				table.insert(allChunks, c)
			end
			g.total = #g.chunks
			g.intact = g.total
			g.hSum = g.hMax
			if #g.chunks > 0 and not g.isGlass then
				for _, c in g.chunks do
					if #c.dmg > 0 then
						warn("[CarDamage] " .. g.name .. " has DMG parts but only glass uses them; they stay hidden")
						break
					end
				end
			end
		else
			for _, i in g.parts do
				if i.isDmg then
					warn("[CarDamage] " .. g.name .. " has DMG parts but only glass chunks use them; they stay hidden")
					break
				end
			end
			if not g.immune then
				table.insert(plainGroups, g)
			end
		end
		g.center, g.radius = centerAndRadius(root, if #g.normal > 0 then g.normal else g.parts)
	end
	for _, info in allInfos do
		partMap[info.part] = { group = info.group, chunk = info.chunk, info = info }
	end

	-- 3. Parents, order (parents first)
	for _, g in groups do
		if g.parentName then
			local p = groups[g.parentName]
			if p then
				table.insert(p.children, g.name)
			else
				g.parentName = nil
			end
		end
		g.needsTemplate = g.detachable or g.parentName ~= nil or (g.chunked and not g.isGlass)
	end
	local order, childOrder = {}, {}
	for _, g in groups do
		table.insert(if g.parentName then childOrder else order, g)
	end
	local byName = function(a, b)
		return a.name < b.name
	end
	table.sort(order, byName)
	table.sort(childOrder, byName)
	for _, g in childOrder do
		table.insert(order, g)
	end

	-- 4. Car frame and extents
	local frameRel, halfExtents = computeFrame(groups, root)
	if not frameRel then
		warn("[CarDamage] Could not compute bounds for " .. model:GetFullName())
		return nil
	end
	local carCF = root.CFrame * frameRel
	local engineGroup = groups.Trunk or groups.Body_Rear
	local enginePos = if engineGroup
		then carCF:PointToObjectSpace(root.CFrame:PointToWorldSpace(engineGroup.center))
		else Vector3.new(0, 0, halfExtents.Z * 0.6) -- rear is +Z in the car frame

	-- 5. Physical wheels and chassis-joined wheels (before we add welds)
	local physWheels = {}
	for gname, pname in Config.PhysicalWheels do
		local g = groups[gname]
		if g then
			local pw = findPhysical(model, pname, partMap)
			if pw then
				physWheels[gname] = { part = pw, canCollide = pw.CanCollide, props = pw.CustomPhysicalProperties }
				for _, i in g.parts do
					i.relPhys = pw.CFrame:ToObjectSpace(i.part.CFrame)
				end
			end
		end
	end
	for _, g in order do
		if g.isWheel and not physWheels[g.name] then
			g.chassisHandled = hasExternalJoint(g)
		end
	end

	-- 6. Templates
	local id = HttpService:GenerateGUID(false)
	local templateInfos = {}
	for _, g in order do
		if g.needsTemplate then
			for _, i in g.parts do
				table.insert(templateInfos, i)
			end
		end
	end
	local templateKey = acquireTemplates(model, id, templateInfos)

	-- 7. Hide DMG parts
	for _, info in allInfos do
		if info.isDmg then
			info.part.Transparency = 1
			info.part.CanQuery = false
		end
	end

	-- 8. Car record, anchors, welds
	local queryParams = RaycastParams.new()
	queryParams.FilterType = Enum.RaycastFilterType.Include
	local car = {
		model = model,
		id = id,
		root = root,
		groups = groups,
		order = order,
		chunks = allChunks,
		plainGroups = plainGroups,
		partMap = partMap,
		physWheels = physWheels,
		frame = frameRel,
		halfExtents = halfExtents,
		enginePos = enginePos + Vector3.new(0, 0.5, 0),
		templateKey = templateKey,
		events = getEvents(model),
		health = 100,
		wrecked = false,
		marks = {},
		debris = {},
		loose = {},
		tires = {},
		fx = nil,
		conns = {},
		queryParams = queryParams,
		queryDirty = true,
		histT = table.create(HIST, 0),
		histV = table.create(HIST, Vector3.zero),
		histHead = 1,
		histCount = 0,
		lastImpact = 0,
		graceUntil = os.clock() + Config.SpawnGrace,
	}
	for _, g in order do
		local cf = root.CFrame * CFrame.new(g.center)
		g.anchorRel = CFrame.new(g.center)
		local pw = physWheels[g.name]
		if pw then
			g.anchorRelPhys = pw.part.CFrame:ToObjectSpace(cf)
		end
		g.anchor = createAnchor(car, g, cf)
	end
	for _, g in order do
		weldGroup(car, g, false)
	end

	-- 9. Attributes, connections
	model:SetAttribute("DamageCarId", id)
	model:SetAttribute("Health", 100)
	model:SetAttribute("Wrecked", false)
	for _, g in order do
		model:SetAttribute("Health_" .. g.attrName, 100)
		g.attrDirty = false
	end

	registry[model] = car
	carCount += 1
	table.insert(car.conns, model.Destroying:Connect(function()
		CarDamage.Remove(model)
	end))
	table.insert(car.conns, model.AncestryChanged:Connect(function()
		if not model:IsDescendantOf(game) then
			CarDamage.Remove(model)
		end
	end))
	table.insert(car.conns, root.AncestryChanged:Connect(function()
		if not root:IsDescendantOf(model) then
			warn("[CarDamage] Root part left " .. model.Name .. ", removing damage system")
			CarDamage.Remove(model)
		end
	end))
	if not heartbeatConn then
		heartbeatConn = RunService.Heartbeat:Connect(onHeartbeat)
	end
	return car
end

function CarDamage.Remove(ref)
	local car = resolveCar(ref)
	if not car then
		return
	end
	registry[car.model] = nil
	carCount -= 1
	for _, c in car.conns do
		c:Disconnect()
	end
	table.clear(car.conns)
	destroyEffects(car)
	releaseTemplates(car.templateKey)
	car.templateKey = nil
	if carCount <= 0 and heartbeatConn then
		heartbeatConn:Disconnect()
		heartbeatConn = nil
		carCount = 0
	end
end

function CarDamage.IsSetup(model: Instance): boolean
	return registry[model] ~= nil
end

------------------------------------------------------------------------
-- PUBLIC: DAMAGE
------------------------------------------------------------------------
function CarDamage.ApplyBulletHit(hitPart: BasePart, hitPosition: Vector3, hitNormal: Vector3?, damage: number?): boolean
	if typeof(hitPart) ~= "Instance" or not hitPart:IsA("BasePart") or typeof(hitPosition) ~= "Vector3" then
		return false
	end
	local car = findCar(hitPart)
	if not car then
		return false
	end
	local entry = car.partMap[hitPart]
	if entry and (entry.group.detached or (entry.chunk and entry.chunk.broken)) then
		return false
	end
	local normal = if typeof(hitNormal) == "Vector3" then hitNormal else Vector3.yAxis
	local amount = if type(damage) == "number" then damage else Config.BulletDamage
	local glassAmount = if type(damage) == "number"
		then damage * (Config.GlassBulletDamage / Config.BulletDamage)
		else Config.GlassBulletDamage

	if entry and not entry.group.immune then
		if entry.group.isGlass then
			makeMark(car, hitPart, hitPosition, normal, 0.6, 0.03, Color3.new(1, 1, 1), 0.35)
		else
			makeMark(car, hitPart, hitPosition, normal, 0.25, 0.06, Color3.fromRGB(22, 22, 22), 0)
			if entry.group.isWheel and entry.info.isTyre then
				popTire(car, entry.group)
			end
		end
	end
	hitAt(car, hitPosition, amount, glassAmount, Config.BulletChunkRadius, -normal, hitPart, false)
	recomputeHealth(car)
	return true
end

function CarDamage.ApplyImpactAt(ref, worldPos: Vector3, direction: Vector3?, amount: number, radius: number?): boolean
	local car = resolveCar(ref)
	if not car or typeof(worldPos) ~= "Vector3" or type(amount) ~= "number" then
		return false
	end
	local dir = if typeof(direction) == "Vector3" and direction.Magnitude > 1e-3 then direction.Unit else nil
	hitAt(car, worldPos, amount, amount, if type(radius) == "number" then radius else Config.CrashChunkRadius, dir, nil, true)
	spawnImpactFx(car, worldPos, if dir then -dir else Vector3.yAxis, amount / Config.DamageScale)
	recomputeHealth(car)
	return true
end

-- Chunked group: every remaining chunk takes `amount`. Unchunked group: the group takes `amount`.
function CarDamage.ApplyDamage(ref, groupName: string, amount: number, direction: Vector3?): boolean
	local car = resolveCar(ref)
	if not car or type(amount) ~= "number" or type(groupName) ~= "string" then
		return false
	end
	local g = car.groups[groupName]
	if not g then
		return false
	end
	local dir = if typeof(direction) == "Vector3" then direction else nil
	if g.chunked then
		for _, c in g.chunks do
			damageChunk(car, c, amount, dir)
		end
	else
		damageGroup(car, g, amount, dir)
	end
	recomputeHealth(car)
	return true
end

function CarDamage.ApplyExplosion(ref, position: Vector3, radius: number, damage: number): boolean
	local car = resolveCar(ref)
	if not car or typeof(position) ~= "Vector3" or type(radius) ~= "number" or radius <= 0 or type(damage) ~= "number" then
		return false
	end
	hitAt(car, position, damage, damage, radius, nil, nil, false)
	recomputeHealth(car)
	return true
end

function CarDamage.Detach(ref, groupName: string): boolean
	local car = resolveCar(ref)
	local g = car and car.groups[groupName]
	if not g or not g.detachable then
		return false
	end
	local ok = detachGroup(car, g, nil)
	recomputeHealth(car)
	return ok
end

function CarDamage.Shatter(ref, groupName: string): boolean
	local car = resolveCar(ref)
	local g = car and car.groups[groupName]
	if not g or not g.isGlass or not g.chunked or g.shattered or g.detached then
		return false
	end
	shatterGroup(car, g, nil)
	recomputeHealth(car)
	return true
end

------------------------------------------------------------------------
-- PUBLIC: REPAIR
------------------------------------------------------------------------
function CarDamage.Repair(ref): boolean
	local car = resolveCar(ref)
	if not car then
		return false
	end
	local model = car.model
	local root = car.root
	for _, list in { car.debris, car.loose } do
		for _, m in list do
			if m.Parent then
				m:Destroy()
			end
		end
		table.clear(list)
	end
	for _, mk in car.marks do
		mk:Destroy()
	end
	table.clear(car.marks)

	-- Parents come before children in car.order, so doors are rebuilt before their glass and mirrors
	for _, g in car.order do
		if g.broken then
			restoreLight(g)
		end
		local pw = car.physWheels[g.name]
		local rebuilt = false
		for _, i in g.parts do
			if not inModel(car, i.part) and i.template then
				local old = i.part
				local c = i.template:Clone()
				local parent = i.parent
				if not parent or not (parent == model or parent:IsDescendantOf(model)) then
					parent = model
				end
				if pw and pw.part.Parent and i.relPhys then
					c.CFrame = pw.part.CFrame * i.relPhys
				else
					c.CFrame = root.CFrame * i.relCF
				end
				c.Parent = parent
				car.partMap[old] = nil
				car.partMap[c] = { group = g, chunk = i.chunk, info = i }
				i.part = c
				if old and old.Parent then
					old:Destroy()
				end
				rebuilt = true
			end
		end
		if not inModel(car, g.anchor) then
			if g.anchor then
				g.anchor:Destroy()
			end
			local cf = if pw and pw.part.Parent and g.anchorRelPhys
				then pw.part.CFrame * g.anchorRelPhys
				else root.CFrame * g.anchorRel
			g.anchor = createAnchor(car, g, cf)
			rebuilt = true
		end
		if rebuilt then
			weldGroup(car, g, true)
		end
	end

	for _, g in car.order do
		for _, i in g.parts do
			local p = i.part
			if p.Parent then
				if i.isDmg then
					p.Transparency = 1
					p.CanQuery = false
				else
					p.Transparency = i.showT
					p.CanQuery = i.canQuery
				end
				p.CanCollide = i.canCollide
			end
		end
		for _, c in g.chunks do
			c.health = c.maxHealth
			c.broken = false
			c.cracked = false
		end
		g.intact = g.total
		g.hSum = g.hMax
		g.health = g.maxHealth
		g.detached = false
		g.shattered = false
		g.attrDirty = true
		if g.isWheel then
			model:SetAttribute("WheelLost_" .. g.attrName, nil)
			model:SetAttribute("TirePopped_" .. g.attrName, nil)
		end
	end
	for _, pw in car.physWheels do
		if pw.part.Parent then
			pw.part.CanCollide = pw.canCollide
			pw.part.CustomPhysicalProperties = pw.props
		end
	end
	table.clear(car.tires)
	destroyEffects(car)
	car.wrecked = false
	model:SetAttribute("Wrecked", false)
	car.queryDirty = true
	car.health = -1 -- force HealthChanged(100)
	recomputeHealth(car)
	local now = os.clock()
	resetHistory(car, now, root.AssemblyLinearVelocity)
	car.graceUntil = now + Config.SpawnGrace
	return true
end

------------------------------------------------------------------------
-- PUBLIC: QUERIES / UTIL
------------------------------------------------------------------------
function CarDamage.GetHealth(ref): number?
	local car = resolveCar(ref)
	return car and car.health
end

-- { [groupName] = 0..100 percent }
function CarDamage.GetGroupHealth(ref)
	local car = resolveCar(ref)
	if not car then
		return nil
	end
	local t = {}
	for name, g in car.groups do
		t[name] = math.floor(groupFrac(g) * 100 + 0.5)
	end
	return t
end

-- { [chunkId] = health } for a chunked group
function CarDamage.GetChunkHealth(ref, groupName: string)
	local car = resolveCar(ref)
	local g = car and car.groups[groupName]
	if not g or not g.chunked then
		return nil
	end
	local t = {}
	for _, c in g.chunks do
		t[c.id] = if g.detached then 0 else c.health
	end
	return t
end

function CarDamage.GetEvents(ref)
	local car = resolveCar(ref)
	return car and car.events
end

-- Puts a character's parts into Config.CharacterCollisionGroup so debris never hits players
function CarDamage.AssignCharacter(character: Model): RBXScriptConnection
	ensureCollisionGroups()
	local groupName = Config.CharacterCollisionGroup
	local function apply(d: Instance)
		if d:IsA("BasePart") then
			d.CollisionGroup = groupName
		end
	end
	for _, d in character:GetDescendants() do
		apply(d)
	end
	return character.DescendantAdded:Connect(apply)
end

return CarDamage
