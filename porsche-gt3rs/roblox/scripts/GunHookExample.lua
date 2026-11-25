--!nonstrict
--[[
	GunHookExample (Script in ServerScriptService)

	Minimal server-authoritative gun hook. The client only says "I fired, aiming at this point".
	The server checks the shooter, fire rate and range, then does its OWN raycast from the
	shooter's head and passes the server result to CarDamage. Client hit data is never trusted.

	Client side (LocalScript inside the Tool), for reference:
		local tool = script.Parent
		local remote = game:GetService("ReplicatedStorage"):WaitForChild("FireWeapon")
		local mouse = game:GetService("Players").LocalPlayer:GetMouse()
		tool.Activated:Connect(function()
			remote:FireServer(mouse.Hit.Position)
		end)
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")
local ServerStorage = game:GetService("ServerStorage")

local CarDamage = require(
	ServerScriptService:FindFirstChild("CarDamage", true) or ServerStorage:FindFirstChild("CarDamage", true)
)

local MAX_RANGE = 400 -- studs
local FIRE_INTERVAL = 0.1 -- seconds between shots per player (fastest weapon you allow)
local BULLET_DAMAGE = nil -- nil = CarDamage.Config.BulletDamage / GlassBulletDamage

local remote = ReplicatedStorage:FindFirstChild("FireWeapon")
if not remote then
	remote = Instance.new("RemoteEvent")
	remote.Name = "FireWeapon"
	remote.Parent = ReplicatedStorage
end

local lastShot = {} -- [Player] = os.clock()
Players.PlayerRemoving:Connect(function(p)
	lastShot[p] = nil
end)

local function isFiniteVector(v: Vector3): boolean
	return v.X == v.X and v.Y == v.Y and v.Z == v.Z
		and math.abs(v.X) < 1e6 and math.abs(v.Y) < 1e6 and math.abs(v.Z) < 1e6
end

remote.OnServerEvent:Connect(function(player: Player, aimPoint)
	-- 1. Validate input type
	if typeof(aimPoint) ~= "Vector3" or not isFiniteVector(aimPoint) then
		return
	end
	-- 2. Validate shooter state
	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	local head = character and character:FindFirstChild("Head")
	if not humanoid or humanoid.Health <= 0 or not head then
		return
	end
	local tool = character:FindFirstChildOfClass("Tool") -- must be holding a weapon
	-- REVIEW: any equipped Tool passes. In a real game check it is a gun (tag/attribute) and take
	-- FIRE_INTERVAL / damage from that weapon's server-side config, not from the client.
	if not tool then
		return
	end
	-- REVIEW: head position replicates from the client (it owns its character physics). Range is capped by
	-- MAX_RANGE from the head, but a teleporting exploiter still needs your general movement anti-cheat.
	-- 3. Rate limit
	local now = os.clock()
	if lastShot[player] and now - lastShot[player] < FIRE_INTERVAL then
		return
	end
	lastShot[player] = now

	-- 4. Server raycast from the head toward the aim point
	local origin = head.Position
	local toAim = aimPoint - origin
	if toAim.Magnitude < 0.1 then
		return
	end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { character }
	params.IgnoreWater = true
	local result = workspace:Raycast(origin, toAim.Unit * MAX_RANGE, params)
	if not result then
		return
	end

	-- 5. Hand the SERVER result to the damage system (returns false if it was not a car)
	local hitCar = CarDamage.ApplyBulletHit(result.Instance, result.Position, result.Normal, BULLET_DAMAGE)
	if not hitCar then
		-- not a car: apply your normal player / NPC damage here
	end
end)
