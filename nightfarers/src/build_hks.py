"""Stage 3: Elden Ring's player script (c0000.hks) with Nightreign's Surge Sprint ported in.

  python build_hks.py <er c0000 decompiled .lua> <out c0000.hks> [<nr c0000 decompiled .lua> (Claw Shot)]

The input is Elden Ring's own c0000.hks decompiled with DSLuaDecompiler (from the user's game files). Every patch
below names the function it edits and the exact Elden Ring text it replaces, and fails if that text is not found
exactly once. Ported code comes from Nightreign's c0000.hks (functions named in the comments); its SpEffect ids are
moved to 9102xxx because Elden Ring uses 1020xx for physick tears.

Surge Sprint is only active while the player has SpEffect NF_SP_NIGHTFARER (resident on the nightfarer armor).
Then L3 / Elden Ring's Crouch binding starts or stops it, as in Nightreign, and no longer crouches.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hero  # noqa: E402

HEADER = '''
-- Nightfarers mod (Stage 3): Nightreign's Surge Sprint, sprint jump (in Jump_D), roll into run/dash/sprint. SpEffects: 9102900 nightfarer (armor), 9102000 sprinting,
-- 9102010 can sprint-turn, 9102030 sprint start can move (Nightreign 102000 / 102010 / 102030, set by TAE).
NF_SP_NIGHTFARER = 9102900
NF_SP_SPRINT = 9102000
NF_SP_SPRINT180 = 9102010
NF_SP_SPRINTSTART_MOVE = 9102030
ISENABLE_SPRINTSTART = TRUE
ISENABLE_SPRINTSTOP = TRUE
STAMINA_REDUCE_SPRINTSTART = -30
STAMINA_REDUCE_SPRINTJUMP = -15
STAMINA_REDUCE_DASHJUMP = -10
NF_JUMPS = 0
NF_SPRINTJUMP = 0
NF_SPRINTJUMP_CLIP = 0 -- 1 = NR's sprint-jump clip (202050); it does not lift off in Elden Ring yet
-- Crouch is Y + L3 for nightfarers (user; L3 is Surge Sprint): the native helper's marker, once per press.
NF_SP_CROUCH = 9103005
NF_CROUCH_LATCH = FALSE

function IsNightfarer()
    if env(1116, NF_SP_NIGHTFARER) == TRUE then
        return TRUE
    end
    return FALSE
end

function NF_CrouchToggle()
    if IsNightfarer() == FALSE then
        return env(1106, ACTION_ARM_L3)
    end
    if env(1116, NF_SP_CROUCH) == TRUE and NF_CROUCH_LATCH == FALSE then
        NF_CROUCH_LATCH = TRUE
        return TRUE
    end
    return FALSE
end
'''

# Nightreign functions, ported (NR c0000.hks). Hero-specific branches (demon sword, necromancy, Claw Shot aim, night,
# bird) are left out: those systems are not in Elden Ring yet.
FUNCTIONS = '''
-- NR BanSprint: actions that can't keep sprinting drop to dash speed.
function BanSprint()
    if GetVariable("MoveSpeedIndex") >= 3 then
        SetVariable("MoveSpeedIndex", 2)
    end
end

-- NR SprintUpdate: standing still ends the sprint.
function SprintUpdate()
    local stick_level = GetVariable("MoveSpeedLevel")
    if stick_level == 0 and GetVariable("MoveSpeedIndex") == 3 then
        ChangeMoveSpeedIndex(0)
    end
end

-- NR ExecSprintStart
function ExecSprintStart()
    if IsNodeActive("GroundNonCombatArea_Upper_SM") == TRUE then
        return FALSE
    end
    -- Crouched (Y + L3 here): surge straight out of it (user), as Elden Ring's crouch has its own move nodes.
    if c_IsStealth == TRUE then
        ISENABLE_SPRINTSTOP = FALSE
        act(2018)
        ExecEventAllBody("W_SprintStart")
        return TRUE
    end
    local blend_type, lower_state = GetHalfBlendInfo()
    if lower_state == LOWER_MOVE then
        if IsNodeActive("Move_Upper Selector") == TRUE then
            ISENABLE_SPRINTSTOP = FALSE
            act(2018)
            ExecEventAllBody("W_SprintStart")
            return TRUE
        end
    else
        ISENABLE_SPRINTSTOP = FALSE
        act(2018)
        ExecEventAllBody("W_SprintStart")
        return TRUE
    end
    return FALSE
end

function SprintStart_onActivate()
    act(101, TRUE)
    AddStamina(STAMINA_REDUCE_SPRINTSTART)
end

function SprintStart_onUpdate()
    act(2018)
    act(101, TRUE)
    SpeedUpdate()
    if QuickTurnCommonFunction() == TRUE then
        return
    end
    if env(1116, NF_SP_SPRINTSTART_MOVE) == TRUE and MoveStart(ALLBODY, Event_Move, FALSE) == TRUE then
        return TRUE
    end
    if ExecStop() == TRUE then
        return
    end
end

function Sprint180_onActivate()
    act(9104)
    ChangeMoveSpeedIndex(3)
end

function Sprint180_onUpdate()
    if env(1116, 5030) == TRUE then
        act(9104)
        act(9105, 180)
    end
    if QuickTurnCommonFunction() == TRUE then
        return
    end
    if env(1116, NF_SP_SPRINT) == FALSE then
        ChangeMoveSpeedIndex(0)
    end
end

function SprintStop_onActivate()
    act(9100)
    ChangeMoveSpeedIndex(0)
end

function SprintStop_onUpdate()
    if StopCommonFunction(TRUE) == TRUE then
        return
    end
end

-- NR's sprint jump plays inside Elden Ring's Jump_D state (behaviour variable NFSprintJump = 1 would pick NR's clips;
-- off for now, see NF_SPRINTJUMP_CLIP):
-- the engine only lifts off in jump states it knows. NR JUMPN/F/D/S = Elden Ring PROTO1/2/3 + NF_JUMPS.
function Jump_Land_S_onUpdate()
    if JumpLandCommonFunction() == TRUE then
        return
    end
end

-- NR Jump_Land_To_Sprint / Rolling_To_Dash / Rolling_To_Sprint have Elden Ring's Jump_Land_To_Dash body.
function Jump_Land_To_Sprint_onUpdate()
    SetVariable("MoveSpeedIndex", 3)
    Jump_Land_To_Dash_onUpdate()
end

function Rolling_To_Dash_onUpdate()
    Jump_Land_To_Dash_onUpdate()
end

function Rolling_To_Sprint_onUpdate()
    Jump_Land_To_Dash_onUpdate()
end

-- NR Rolling_To_Run
function Rolling_To_Run_onUpdate()
    act(101, TRUE)
    SetEnableAimMode()
    SetVariable("JumpLandMoveDirection", GetVariable("MoveDirection"))
    SetVariable("MoveSpeedLevelReal", 1)
    if ExecStop() == TRUE then
        return
    end
    if env(2000) == TRUE and MoveStart(ALLBODY, Event_MoveLong, FALSE) == TRUE then
        return
    end
    if EvasionCommonFunction(FALL_TYPE_DEFAULT, "W_AttackRightLight1", "W_AttackRightHeavy1Start", "W_AttackLeftLight1", "W_AttackLeftHeavy1", "W_AttackBothLight1", "W_AttackBothHeavy1Start", QUICKTYPE_NORMAL) == TRUE then
        return
    end
end
'''

PATCHES = [  # (function, Elden Ring text, replacement)
    # NR SpeedUpdate: L3 released re-arms start/stop; nightfarers use move type 0 (NR HERO_BALANCE etc.).
    ("SpeedUpdate", '''    local is_lockon = GetVariable("IsLockon")
''', '''    local is_lockon = GetVariable("IsLockon")
    if IsNightfarer() == TRUE then
        if env(1108, ACTION_ARM_ACTION) <= 0 and env(1108, ACTION_ARM_L3) <= 0 then
            ISENABLE_SPRINTSTART = TRUE
            ISENABLE_SPRINTSTOP = TRUE
        end
        SetVariable("MoveTypeIndex", 0)
    end
'''),
    # NR SpeedUpdate: while sprinting, L3 again drops to dash; otherwise hold speed 3 (out of stamina: dash).
    ("SpeedUpdate", '''    elseif env(1116, 100220) == TRUE then
        ChangeMoveSpeedIndex(2)
    else
''', '''    elseif env(1116, 100220) == TRUE then
        ChangeMoveSpeedIndex(2)
    elseif IsNightfarer() == TRUE and (env(1116, NF_SP_SPRINT) == TRUE or GetVariable("MoveSpeedIndex") == 3) then
        if ISENABLE_SPRINTSTOP == TRUE and env(1108, ACTION_ARM_L3) > 0 then
            ISENABLE_SPRINTSTART = FALSE
            ChangeMoveSpeedIndex(2)
        elseif env(1116, 100020) == TRUE then
            ISENABLE_SPRINTSTART = FALSE
            ChangeMoveSpeedIndex(2)
        else
            act(2018)
            ChangeMoveSpeedIndex(3)
        end
        act(110)
    else
'''),
    # NR SpeedUpdate: L3 while moving starts the sprint.
    ("SpeedUpdate", '''        if stick_level > 1.100000023841858 then
            if env(1116, 100020) == TRUE then''', '''        if IsNightfarer() == TRUE and ISENABLE_SPRINTSTART == TRUE and env(1108, ACTION_ARM_L3) > 0 and env(1001) >= 0 and ExecSprintStart() == TRUE then
        elseif stick_level > 1.100000023841858 then
            if env(1116, 100020) == TRUE then'''),
    # NR ExecStop: stopping from a sprint plays the sprint stop.
    ("ExecStop", '''    if stop_speed >= 0 and stop_speed <= 1 then
''', '''    if GetVariable("MoveSpeedIndex") > 2 then
        if c_IsStealth == TRUE then
            ExecEventAllBody("W_StealthDashStop")
        else
            ExecEventAllBody("W_SprintStop")
        end
    elseif stop_speed >= 0 and stop_speed <= 1 then
'''),
    # NR ExecDashTurn: sprint 180 turn.
    ("ExecDashTurn", '''        ExecEventAllBody("W_Dash180")
''', '''        if env(1116, NF_SP_SPRINT180) == TRUE then
            ExecEventAllBody("W_Sprint180")
        else
            ExecEventAllBody("W_Dash180")
        end
'''),
    # Nightreign has no crouch on L3 (it is Surge Sprint there): nightfarers crouch and stand with Y + L3 (user). The helper hides
    # that L3 from the game, so there is no action request: the marker is checked before Elden Ring's early return.
    ("ExecEvasion", '''    if c_HasActionRequest == FALSE then
        return FALSE
    end
    local request = GetEvasionRequest()
    if env(1106, ACTION_ARM_L3) == TRUE and c_IsStealth == FALSE then''',
     '''    local crouch = NF_CrouchToggle()
    if c_HasActionRequest == FALSE and crouch == FALSE then
        return FALSE
    end
    local request = GetEvasionRequest()
    if crouch == TRUE and c_IsStealth == FALSE then'''),
    ("ExecEvasion", '''    elseif env(1106, ACTION_ARM_L3) == TRUE and c_IsStealth == TRUE then''',
     '''    elseif crouch == TRUE and c_IsStealth == TRUE then'''),
    # NR ExecJump: plain jumps cost nightfarers no stamina (dash -10 and sprint -15 below).
    ("ExecJump", '''    if env(1116, 102360) == FALSE then
        AddStamina(STAMINA_REDUCE_JUMP)''', '''    if env(1116, 102360) == FALSE and IsNightfarer() == FALSE then
        AddStamina(STAMINA_REDUCE_JUMP)'''),
    ("ExecJump", '''GetVariable("MoveSpeedIndex") == 2 then''', '''GetVariable("MoveSpeedIndex") >= 2 then'''),
    # NR ExecJump: from a sprint (or its start, a sprint landing, a roll into sprint) the sprint jump (NR W_Jump_S).
    ("ExecJump", '''    if JumpMoveLevel == 2 then
        if env(700) == TRUE then
            act(4001)
        end
''', '''    if JumpMoveLevel >= 1 and IsNightfarer() == TRUE and (GetVariable("LocomotionState") == 1 and GetVariable("MoveSpeedIndex") == 3 or IsNodeActive("SprintStart_Selector") == TRUE or IsNodeActive("Jump_Land_To_Sprint_Height_Selector") == TRUE or IsNodeActive("Rolling_To_Sprint_Selector") == TRUE) then
        JumpMoveLevel = 3
    end
    if JumpMoveLevel == 3 then
        if env(700) == TRUE then
            act(4001)
        end
        act(2025, env(404))
        SetAIActionState()
        AddStamina(STAMINA_REDUCE_SPRINTJUMP)
        NF_SPRINTJUMP = 1
        SetVariable("NFSprintJump", NF_SPRINTJUMP_CLIP)
        -- Elden Ring knows speed indices 0-2 only; at 3 (sprint) the jump never lifted off.
        SetVariable("MoveSpeedIndex", 2)
        ExecEvent("W_Jump_D")
        return TRUE
    elseif JumpMoveLevel == 2 then
        if env(700) == TRUE then
            act(4001)
        end
        NF_SPRINTJUMP = 0
        SetVariable("NFSprintJump", 0)
        if IsNightfarer() == TRUE then
            AddStamina(STAMINA_REDUCE_DASHJUMP)
        end
'''),
    # NR: landing from a sprint jump with the stick held -> W_Jump_Land_To_Sprint, else W_Jump_Land_S. Not after a
    # jump attack: NR's Land_S state has its own attack landings, which cut the attack into another slash.
    ("Jump_Loop_onUpdate", '''        if JumpMoveLevel == 2 then
            ExecEventNoReset("W_Jump_Land_To_Dash")
''', '''        if NF_JUMPS == 1 and JumpMoveLevel >= 1 then
            ExecEventNoReset("W_Jump_Land_To_Sprint")
            return
        elseif JumpMoveLevel == 2 then
            ExecEventNoReset("W_Jump_Land_To_Dash")
'''),
    ("Jump_Loop_onUpdate", '''        elseif PROTO3 == 1 then
            ExecEventNoReset("W_Jump_Land_D")
''', '''        elseif NF_JUMPS == 1 and GetVariable("JumpAttackForm") == 0 then
            ExecEventNoReset("W_Jump_Land_S")
        elseif PROTO3 == 1 then
            ExecEventNoReset("W_Jump_Land_D")
'''),
    ("FallCommonFunction", '''                    if JumpMoveLevel == 2 then
                        ExecEventNoReset("W_Jump_Land_To_Dash")
''', '''                    if NF_JUMPS == 1 and JumpMoveLevel >= 1 then
                        ExecEventNoReset("W_Jump_Land_To_Sprint")
                        return TRUE
                    elseif JumpMoveLevel == 2 then
                        ExecEventNoReset("W_Jump_Land_To_Dash")
'''),
    ("JumpCommonFunction", '''            if JumpMoveLevel == 2 then
                hkbFireEvent("W_Jump_Land_To_Dash")
''', '''            if NF_JUMPS == 1 and JumpMoveLevel >= 1 then
                hkbFireEvent("W_Jump_Land_To_Sprint")
            elseif JumpMoveLevel == 2 then
                hkbFireEvent("W_Jump_Land_To_Dash")
'''),
    ("JumpCommonFunction", '''            elseif jump_type == 2 then
                ExecEventNoReset("W_Jump_Land_D")
            end
            return TRUE
        else
''', '''            elseif jump_type == 2 and NF_JUMPS == 1 and GetVariable("JumpAttackForm") == 0 then
                ExecEventNoReset("W_Jump_Land_S")
            elseif jump_type == 2 then
                ExecEventNoReset("W_Jump_Land_D")
            end
            return TRUE
        else
'''),
    ("JumpCommonFunction", '''        elseif jump_type == 2 then
            ExecEventNoReset("W_Jump_Land_D")
        end
        return TRUE
    elseif env(301, 0)''', '''        elseif jump_type == 2 and NF_JUMPS == 1 and GetVariable("JumpAttackForm") == 0 then
            ExecEventNoReset("W_Jump_Land_S")
        elseif jump_type == 2 then
            ExecEventNoReset("W_Jump_Land_D")
        end
        return TRUE
    elseif env(301, 0)'''),
    # NR MoveStartonCancelTiming: a roll's move cancel goes on into sprint / dash / run. NR gates it with SpEffect
    # 102040 (not found in NR's TAE or params); here: while a roll node is active.
    ("MoveStartonCancelTiming", '''    if env(2000) == TRUE then
''', '''    if env(2000) == TRUE then
        if IsNightfarer() == TRUE and (IsNodeActive("Rolling_Selector") == TRUE or IsNodeActive("Rolling_Selftrans_Selector") == TRUE) then
            if GetVariable("MoveSpeedIndex") >= 3 then
                hkbFireEvent("W_Rolling_To_Sprint")
                return TRUE
            elseif GetVariable("MoveSpeedLevel") >= 2 then
                hkbFireEvent("W_Rolling_To_Dash")
                return TRUE
            elseif GetVariable("MoveSpeedLevel") >= 1 then
                hkbFireEvent("W_Rolling_To_Run")
                return TRUE
            end
        end
'''),
    # Sprint attacks, items and guard use Elden Ring's dash versions (NR also maps speed 3 to its *Dash events).
    ("MoveCommonFunction", '''    local speed = GetVariable("MoveSpeedIndex")
''', '''    local speed = GetVariable("MoveSpeedIndex")
    if speed == 3 then
        speed = 2
    end
'''),
    ("Move_onUpdate", '''    local move_speed = GetVariable("MoveSpeedIndex")
''', '''    local move_speed = GetVariable("MoveSpeedIndex")
    if move_speed == 3 then
        move_speed = 2
    end
'''),
]
# NR calls these at the start of the listed Elden Ring functions.
PROLOGUES = [("FallCommonFunction", "SprintUpdate()"), ("LandCommonFunction", "SprintUpdate()"),
             ("JumpCommonFunction", "SprintUpdate()"), ("Jump_Loop_onUpdate", "SprintUpdate()"),
             ("Jump_N_onUpdate", "NF_JUMPS = 0"), ("Jump_F_onUpdate", "NF_JUMPS = 0"), ("Jump_D_onUpdate", "NF_JUMPS = NF_SPRINTJUMP"),
             ("ExecFallStart", "NF_JUMPS = 0"),
             ("Guard_Update", "BanSprint()"), ("SwordArts_Update", "BanSprint()"), ("Item_Upper_Update", "BanSprint()"),
             ("MagicRight_Upper_Update", "BanSprint()"), ("MagicLeft_Upper_Update", "BanSprint()")]


# Inserted before the final `end` of the listed Elden Ring functions.
EPILOGUES = [
    # Y + L3 crouch: re-arm once the helper's marker is gone.
    ("Update", '''    if env(1116, NF_SP_CROUCH) == FALSE then
        NF_CROUCH_LATCH = FALSE
    end
'''),
    # NR Update: outside movement (attacks, rolls, items...) the sprint ends. Node list from NR minus systems not
    # ported yet (Claw Shot, dragoon / bird / spiritstream jumps).
    ("Update", '''    if GetVariable("MoveSpeedIndex") == 3 then
        if IsNodeActive("NewJump LayerGenerator") == TRUE and GetVariable("JumpAttackForm") ~= 0 then
            SetVariable("MoveSpeedIndex", 0)
        end
        if (IsNodeActive("HandChange_Upper_SM") == TRUE or IsNodeActive("WeaponChange_Upper_SM") == TRUE) and GetVariable("MoveSpeedLevel") == 0 then
            SetVariable("MoveSpeedIndex", 0)
        end
        if IsNodeActive("NewJump LayerGenerator") == FALSE and IsNodeActive("Fall_SM") == FALSE and IsNodeActive("Move_Upper Selector") == FALSE and IsNodeActive("HandChange_Upper_SM") == FALSE and IsNodeActive("WeaponChange_Upper_SM") == FALSE and IsNodeActive("Sprint180_CMSG") == FALSE and IsNodeActive("Rolling_To_Sprint_Selector") == FALSE then
            SetVariable("MoveSpeedIndex", 0)
        end
    end
'''),
    # NR SetWeightIndex: always MOVE_WEIGHT_LIGHT (NR has no equip-load move styles). NR's sprint selectors have only
    # Light (0) and Over (1), so ER's medium load (1) picked the overweight sprint.
    ("SetWeightIndex", '''    if IsNightfarer() == TRUE and math.mod(env(257), 20) ~= WEIGHT_OVERWEIGHT then
        SetVariable("MoveWeightIndex", MOVE_WEIGHT_LIGHT)
    end
'''),
]


# Hero data: NR functions copied by name, their engine-only queries answered by NF_* helpers that read the native
# helper's marker SpEffects (src/native). See heroes/<name>.toml [script].
HERO = hero.load()["script"]
NR_PORT = HERO["port"]
NR_SUBST = [tuple(s) for s in HERO["subst"]]
NR_HELPERS = HERO["helpers"]
NR_HEADER = HERO["header"]


def nr_function(nr_text, name):
    """A Nightreign function as plain `function Name(...)` text (DSLuaDecompiler writes most as f0_local0 = ...)."""
    m = re.search(rf"^function {re.escape(name)}\((.*)\)\n", nr_text, re.M)
    if m:
        end = re.compile(r"^end\n", re.M).search(nr_text, m.end())
        return nr_text[m.start():end.end()]
    m = re.search(rf"^{re.escape(name)} = f0_local0\n", nr_text, re.M)
    assert m, f"Nightreign has no function {name}"
    head = [h for h in re.finditer(r"^f0_local0 = function \((.*)\)\n", nr_text[:m.start()], re.M)][-1]
    end = re.compile(r"^end\n", re.M).search(nr_text, head.end())
    return f"function {name}({head.group(1)})\n" + nr_text[head.end():end.end()]


def port_nr(nr_text, er_text, defines, nr_defines):
    code = "\n".join(nr_function(nr_text, n) for n in NR_PORT)
    for old, new in NR_SUBST:
        code = code.replace(old, new)
    left = sorted(set(re.findall(r"env\((371|411|412|413|1122)\b", code)) | {"ACTION_ARM_SKILL"} & set(re.findall(r"ACTION_ARM_\w+", code)))
    assert not left, f"Nightreign-only queries left: {left}"
    defined = set(re.findall(r"^function (\w+)\(", er_text + defines + code + NR_HELPERS + FUNCTIONS, re.M))
    missing = sorted({c for c in re.findall(r"\b([A-Z]\w*)\(", code) if c not in defined} - {"TRUE", "FALSE"})
    assert not missing, f"ported code calls undefined functions: {missing}"
    # Globals the ported code reads must exist (Havok Script aborts on undefined globals): take Nightreign's values.
    known = set(re.findall(r"^(\w+) = ", er_text + defines + HEADER + NR_HEADER, re.M))
    nr_globals = dict(re.findall(r"^([A-Z_][A-Z0-9_]*|g_\w+) = (.+)$", nr_defines + nr_text, re.M))
    used = set(re.findall(r"\b([A-Z][A-Z0-9_]{2,}|g_\w+)\b", code)) - known - {"TRUE", "FALSE"}
    extra = "".join(f"{g} = {nr_globals[g]}\n" for g in sorted(used) if g in nr_globals)
    unknown = sorted(g for g in used if g not in nr_globals and not re.search(rf"^function {g}\(", code, re.M))
    assert not unknown, f"ported code reads unknown globals: {unknown}"
    return NR_HEADER + extra, NR_HELPERS + "\n-- Nightreign functions (Claw Shot), ported by name.\n" + code


def function_span(text, name):
    m = list(re.finditer(rf"^function {re.escape(name)}\(.*\)\n", text, re.M))
    assert len(m) == 1, (name, len(m))
    end = re.compile(r"^end\n", re.M).search(text, m[0].end())
    return m[0].start(), m[0].end(), end.end()


def main(src, out, nr_src=None):
    text = Path(src).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    header, functions = HEADER, FUNCTIONS
    if nr_src:
        nr_text = Path(nr_src).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        # Nightreign's hero types (not in Elden Ring's common define).
        nr_defines = Path(nr_src).with_name("nr_common_define.lua").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        hero = "".join(l + "\n" for l in nr_defines.split("\n") if l.startswith("HERO_"))
        defines = Path(src).with_name("er_common_define.lua").read_text(encoding="utf-8-sig") + hero
        nr_head, nr_code = port_nr(nr_text, text, defines, nr_defines)
        header, functions = header + hero + nr_head, functions + nr_code
        PATCHES.extend((p["function"], p["old"], p["new"]) for p in HERO["patches"])
        EPILOGUES.extend((e["function"], e["code"]) for e in HERO["epilogues"])
        PROLOGUES.extend((e["function"], e["call"]) for e in HERO["prologues"])
    for name, old, new in PATCHES:
        start, _, end = function_span(text, name)
        body = text[start:end]
        assert body.count(old) == 1, f"{name}: patch anchor found {body.count(old)}x: {old!r}"
        text = text[:start] + body.replace(old, new) + text[end:]
    # NF_PROBES=1: stamina-bar probes for the sprint jump (-40 on entering Jump_D from a sprint, refill on Jump_Loop).
    probes = [("Jump_D_onActivate", 'if NF_SPRINTJUMP == 1 then AddStamina(-40) end'),
              ("Jump_Loop_onActivate", "if NF_JUMPS == 1 then AddStamina(999) end")]
    # NF_BIND_PROBE=1: the native helper's bind markers (9103001 Y + LT, 9103002 Y + RT) -> stamina -40 / -80 once.
    if os.environ.get("NF_BIND_PROBE") == "1":
        text = "NF_BIND_SKILL = 0\nNF_BIND_ULT = 0\n" + text
        EPILOGUES.append(("Update", '''    if env(1116, 9103001) == TRUE then
        if NF_BIND_SKILL == 0 then
            AddStamina(-40)
        end
        NF_BIND_SKILL = 1
    else
        NF_BIND_SKILL = 0
    end
    if env(1116, 9103002) == TRUE then
        if NF_BIND_ULT == 0 then
            AddStamina(-80)
        end
        NF_BIND_ULT = 1
    else
        NF_BIND_ULT = 0
    end
'''))
    # NF_INPUT_PROBE=1: Y + LT / RT arrive as Elden Ring's two-hand (change style) input. Is L2 / R2 held then (vs
    # Y + LB / RB)? Stamina -40 / -80 and no two-handing.
    if os.environ.get("NF_INPUT_PROBE") == "1":
        probes = []  # input probes only
        # Probe 3: Y + trigger = change style without the bumper held (Y + LB holds L1). -20 = the path runs at all.
        probes.append(("ExecHandChange", 'if IsNightfarer() == TRUE and env(1106, ACTION_ARM_CHANGE_STYLE_L) == TRUE and '
                       'env(1108, ACTION_ARM_L1) <= 0 then AddStamina(-40) ResetRequest() return FALSE end'))
        probes.append(("ExecHandChange", 'if IsNightfarer() == TRUE and env(1106, ACTION_ARM_CHANGE_STYLE_R) == TRUE and '
                       'env(1108, ACTION_ARM_R1) <= 0 then AddStamina(-80) ResetRequest() return FALSE end'))
        probes.append(("ExecHandChange", 'if IsNightfarer() == TRUE and (env(1106, ACTION_ARM_CHANGE_STYLE_L) == TRUE or '
                       'env(1106, ACTION_ARM_CHANGE_STYLE_R) == TRUE) then AddStamina(-20) end'))
    use_probes = os.environ.get("NF_PROBES") == "1" or os.environ.get("NF_INPUT_PROBE") == "1"
    for name, call in PROLOGUES + (probes if use_probes else []):
        _, head_end, _ = function_span(text, name)
        text = text[:head_end] + f"    {call}\n" + text[head_end:]
    for name, code in EPILOGUES:
        _, _, end = function_span(text, name)
        last = end - len("end\n")
        # Lua: a bare `return` must stay the last statement, so insert before a trailing one.
        m = re.search(r"\n    return\n[ \n]*$", text[:last])
        if m:
            last = m.start() + 1
        text = text[:last] + code + text[last:]
    for name in ("BanSprint", "SprintUpdate", "ExecSprintStart", "SprintStart_onUpdate", "IsNightfarer", "Jump_Land_S_onUpdate",
                 "Jump_Land_To_Sprint_onUpdate", "Rolling_To_Run_onUpdate"):
        assert not re.search(rf"^function {name}\(", text, re.M), f"Elden Ring already defines {name}"
    # Constants first (top of file), functions at the end, as plain Lua 5.1 text.
    Path(out).write_text(header.lstrip() + "\n" + text.rstrip() + "\n" + functions, encoding="utf-8", newline="\n")
    print(f"{out}: {len(PATCHES)} patches, {len(PROLOGUES)} prologues")


if __name__ == "__main__":
    main(*sys.argv[1:4])
