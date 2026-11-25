--!nonstrict
--[[
	CarDamageServer (Script, put in ServerScriptService)

	- Sets up CarDamage on every Model tagged "DamageCar" that is (or later becomes) a descendant of
	  Workspace, including cars spawned at runtime by cloning a tagged template.
	- Exposes a BindableFunction ServerStorage.CarDamageAPI for other server scripts (guns, repair
	  tools, admin commands) that prefer not to require the module directly:

		local api = game:GetService("ServerStorage"):WaitForChild("CarDamageAPI")
		api:Invoke("BulletHit", hitPart, hitPosition, hitNormal, damage)
		api:Invoke("ImpactAt", carModel, worldPos, direction, amount, radius)
		api:Invoke("Damage", carModel, "Hood", 50, direction)
		api:Invoke("Explosion", carModel, position, radius, damage)
		api:Invoke("Repair", carModel)
		api:Invoke("Detach", carModel, "Door_L")
		api:Invoke("Shatter", carModel, "Glass_Windshield")
		api:Invoke("GetHealth", carModel)
		api:Invoke("GetGroupHealth", carModel)
		api:Invoke("Setup", carModel, rootPart)
]]

local CollectionService = game:GetService("CollectionService")
local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")
local ServerStorage = game:GetService("ServerStorage")

local TAG = "DamageCar"
local SETUP_DELAY = 1 -- seconds to wait after a car appears so a chassis script (A-Chassis) can initialise first
-- REVIEW: the command bar step unanchors every body part. Until Setup welds them (SETUP_DELAY), only the
-- chassis holds them. With A-Chassis that is fine (it welds Body to DriveSeat on init). Without a chassis
-- that welds, parts fall during this delay and Setup records wrong offsets: anchor the car until Setup runs.

local function findModule(): ModuleScript
	local candidates = {
		script.Parent and script.Parent:FindFirstChild("CarDamage"),
		ServerScriptService:FindFirstChild("CarDamage", true),
		ServerStorage:FindFirstChild("CarDamage", true),
	}
	for _, m in candidates do
		if m and m:IsA("ModuleScript") then
			return m
		end
	end
	error("[CarDamageServer] ModuleScript 'CarDamage' not found in ServerScriptService or ServerStorage")
end

local CarDamage = require(findModule())

------------------------------------------------------------------------
-- Auto setup of tagged cars
------------------------------------------------------------------------
local pending = {} -- [Model] = true while a delayed setup is queued
local watchers = {} -- [Instance] = RBXScriptConnection

local function trySetup(inst: Instance)
	if not inst:IsA("Model") or pending[inst] or CarDamage.IsSetup(inst) then
		return
	end
	if not inst:IsDescendantOf(workspace) then
		return
	end
	pending[inst] = true
	task.delay(SETUP_DELAY, function()
		pending[inst] = nil
		if
			inst.Parent
			and inst:IsDescendantOf(workspace)
			and CollectionService:HasTag(inst, TAG)
			and not CarDamage.IsSetup(inst)
		then
			local ok, err = pcall(CarDamage.Setup, inst)
			if not ok then
				warn("[CarDamageServer] Setup failed for " .. inst:GetFullName() .. ": " .. tostring(err))
			end
		end
	end)
end

local function unwatch(inst: Instance)
	local c = watchers[inst]
	if c then
		c:Disconnect()
		watchers[inst] = nil
	end
end

local function onTagged(inst: Instance)
	if not inst:IsA("Model") then
		return
	end
	-- Cars stored in ServerStorage / ReplicatedStorage get set up when they are moved into Workspace.
	if not watchers[inst] then
		watchers[inst] = inst.AncestryChanged:Connect(function()
			if not inst:IsDescendantOf(game) then
				unwatch(inst)
			elseif inst:IsDescendantOf(workspace) then
				trySetup(inst)
			end
		end)
	end
	trySetup(inst)
end

CollectionService:GetInstanceAddedSignal(TAG):Connect(onTagged)
CollectionService:GetInstanceRemovedSignal(TAG):Connect(function(inst)
	unwatch(inst)
	if CarDamage.IsSetup(inst) then
		CarDamage.Remove(inst)
	end
end)
for _, inst in CollectionService:GetTagged(TAG) do
	task.spawn(onTagged, inst)
end

------------------------------------------------------------------------
-- Characters: put them in their own collision group so debris passes through players
------------------------------------------------------------------------
if CarDamage.Config.AssignCharacterGroup then
	local function onCharacter(character: Model)
		CarDamage.AssignCharacter(character)
	end
	local function onPlayer(player: Player)
		player.CharacterAdded:Connect(onCharacter)
		if player.Character then
			onCharacter(player.Character)
		end
	end
	Players.PlayerAdded:Connect(onPlayer)
	for _, p in Players:GetPlayers() do
		task.spawn(onPlayer, p)
	end
end

------------------------------------------------------------------------
-- BindableFunction API (server to server only)
------------------------------------------------------------------------
local api = ServerStorage:FindFirstChild("CarDamageAPI")
if not (api and api:IsA("BindableFunction")) then
	api = Instance.new("BindableFunction")
	api.Name = "CarDamageAPI"
	api.Parent = ServerStorage
end

local actions = {
	BulletHit = CarDamage.ApplyBulletHit,
	ImpactAt = CarDamage.ApplyImpactAt,
	Damage = CarDamage.ApplyDamage,
	Explosion = CarDamage.ApplyExplosion,
	Repair = CarDamage.Repair,
	Detach = CarDamage.Detach,
	Shatter = CarDamage.Shatter,
	GetHealth = CarDamage.GetHealth,
	GetGroupHealth = CarDamage.GetGroupHealth,
	Setup = function(model, rootPart)
		return CarDamage.Setup(model, rootPart) ~= nil
	end,
}

api.OnInvoke = function(action: string, ...)
	local fn = actions[action]
	if not fn then
		warn("[CarDamageServer] Unknown CarDamageAPI action: " .. tostring(action))
		return nil
	end
	local ok, result = pcall(fn, ...)
	if not ok then
		warn("[CarDamageServer] " .. tostring(action) .. " failed: " .. tostring(result))
		return nil
	end
	return result
end
