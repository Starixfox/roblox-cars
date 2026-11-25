-- StudioSetup_CommandBar.lua
-- Paste ONCE into the Studio command bar (View > Command Bar) with the imported car Model selected.
-- CollisionFidelity, RenderFidelity and SurfaceAppearance.AlphaMode can only be changed in Studio,
-- not from a running game, which is why this step exists. Safe to run again. Undo with Ctrl+Z.
local function runCarDamageSetup()
	local Selection = game:GetService("Selection")
	local CollectionService = game:GetService("CollectionService")
	local ChangeHistoryService = game:GetService("ChangeHistoryService")

	local model = Selection:Get()[1]
	if not model or not model:IsA("Model") then
		warn("[CarDamage setup] Select the imported car Model first")
		return
	end

	local recording = nil
	pcall(function()
		recording = ChangeHistoryService:TryBeginRecording("CarDamage setup")
	end)

	local expected = {
		"Hood", "Trunk", "Door_L", "Door_R", "FrontBumper", "RearBumper", "Wing", "Mirror_L", "Mirror_R",
		"Wheel_LF", "Wheel_RF", "Wheel_LR", "Wheel_RR", "Body_Front", "Body_Mid", "Body_Rear", "Interior",
		"SteeringWheel", "Brakes", "HeadLight_L", "HeadLight_R", "TailLight_L", "TailLight_R",
		"Glass_Windshield", "Glass_Rear", "Glass_Quarter_L", "Glass_Quarter_R", "Glass_Door_L", "Glass_Door_R",
	}

	-- Same parsing rules as CarDamage.lua: split on "__", optional C<nn> chunk id, optional DMG
	local function parse(name)
		if not string.find(name, "__", 1, true) then
			return nil
		end
		local segs, start = {}, 1
		while true do
			local i = string.find(name, "__", start, true)
			if not i then
				table.insert(segs, string.sub(name, start))
				break
			end
			table.insert(segs, string.sub(name, start, i - 1))
			start = i + 2
		end
		if segs[1] == "" or #segs < 2 then
			return nil
		end
		local idx, chunkId = 2, nil
		if #segs >= 3 and string.match(segs[2], "^C%d+$") then
			chunkId = segs[2]
			idx = 3
		end
		local isDmg = segs[idx] == "DMG"
		if isDmg then
			idx += 1
		end
		return segs[1], chunkId, isDmg, table.concat(segs, "__", idx)
	end

	local groups = {} -- [name] = { normal, dmg, chunks = {[id]=true}, keys = {}, dmgKeys = {} }
	local meshCount, unnamed, chunkParts, alphaSet = 0, 0, 0, 0

	for _, d in model:GetDescendants() do
		if d:IsA("MeshPart") then
			meshCount += 1
			local gname, chunkId, isDmg, key = parse(d.Name)

			if gname then
				-- Only <Group>__ parts: chassis MeshParts (A-Chassis wheels, hitbox) must keep their physics,
				-- so running this again after adding a chassis stays safe.
				-- Chunk pieces use Box collision so they stay cheap when they fall off
				local fidelity = if chunkId then Enum.CollisionFidelity.Box else Enum.CollisionFidelity.Hull
				pcall(function()
					d.CollisionFidelity = fidelity
				end)
				pcall(function()
					d.RenderFidelity = Enum.RenderFidelity.Automatic
				end)
				d.CanCollide = false
				d.CanTouch = false
				d.CanQuery = true
				d.Massless = true
				d.Anchored = false

				local g = groups[gname]
				if not g then
					g = { normal = 0, dmg = 0, chunks = {}, keys = {}, dmgKeys = {} }
					groups[gname] = g
				end
				local fullKey = (chunkId or "") .. "|" .. key
				if chunkId then
					g.chunks[chunkId] = true
					chunkParts += 1
				end
				if string.sub(gname, 1, 6) == "Glass_" then
					for _, sa in d:GetChildren() do
						if sa:IsA("SurfaceAppearance") then
							pcall(function()
								sa.AlphaMode = Enum.AlphaMode.Transparency
							end)
							alphaSet += 1
						end
					end
				end
				if isDmg then
					g.dmg += 1
					g.dmgKeys[fullKey] = true
					if d:GetAttribute("CD_ShowTransparency") == nil and d.Transparency < 1 then
						d:SetAttribute("CD_ShowTransparency", d.Transparency)
					end
					d.Transparency = 1
					d.CanQuery = false
				else
					g.normal += 1
					g.keys[fullKey] = true
				end
			else
				unnamed += 1
			end
		end
	end

	CollectionService:AddTag(model, "DamageCar")

	print(("[CarDamage setup] %s: %d MeshParts (%d chunk parts), %d without a <Group>__ name, %d glass SurfaceAppearances set to AlphaMode.Transparency"):format(
		model.Name, meshCount, chunkParts, unnamed, alphaSet))
	local names = {}
	for name in groups do
		table.insert(names, name)
	end
	table.sort(names)
	local totalChunks = 0
	for _, name in names do
		local g = groups[name]
		local chunkCount = 0
		for _ in g.chunks do
			chunkCount += 1
		end
		totalChunks += chunkCount
		local unmatched = 0
		for key in g.dmgKeys do
			if not g.keys[key] then
				unmatched += 1
			end
		end
		local note = ""
		if unmatched > 0 then
			note ..= (" (%d DMG parts without a normal twin)"):format(unmatched)
		end
		if g.dmg > 0 and string.sub(name, 1, 6) ~= "Glass_" then
			note ..= " (DMG parts ignored: only glass uses them)"
		end
		print(("  %-18s chunks: %3d   normal: %3d   DMG: %3d%s"):format(name, chunkCount, g.normal, g.dmg, note))
	end
	print(("[CarDamage setup] %d chunks in total"):format(totalChunks))
	local missing = {}
	for _, name in expected do
		if not groups[name] then
			table.insert(missing, name)
		end
	end
	if #missing > 0 then
		warn("[CarDamage setup] Groups not found (fine for a Lite model): " .. table.concat(missing, ", "))
	end
	print("[CarDamage setup] Tagged '" .. model.Name .. "' with DamageCar. Done.")

	if recording then
		pcall(function()
			ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
		end)
	end
end
runCarDamageSetup()
