//! Nightfarers native helper, loaded by ME3 ([[natives]] in nightfarers.me3).
//!
//! Binds: Nightreign's hold Y + LT = character skill, hold Y + RT = ultimate (Xbox pad). Elden Ring turns Y + trigger
//! into two-handing before the player script sees it, so the helper wraps the game's XInputGetState import: while Y is
//! held and a trigger is used, the game sees neither Y nor the triggers, and the player script (c0000.hks) is told by
//! short marker SpEffects it reads with env(1116, id).
//!
//! Claw Shot (Wylder's skill) needs what Nightreign's engine reports to its script: whether the claw hooked a target
//! and whether Nightreign marks it no-pull (hit type 21: pull it in, 20: drag Wylder to it; claw_drags), and the pull / drag itself. The
//! claw's hit bullet marks the target with SpEffect 8880001; the helper finds the freshly marked character after the
//! skill is released, classifies it by its hit radius, tells the script, then moves the target or the player.
mod hud;
#[cfg(feature = "rig")]
mod pad_script;
#[cfg(feature = "rig")]
mod rig;

use std::collections::HashMap;
use std::ffi::c_void;
use std::io::Write;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use eldenring::cs::{
    AtkParam_Pc, BlockId, BulletSpawnData, CSBulletManager, CSCamera, CSHavokMan, CSTaskGroupIndex, CSTaskImp, ChrIns, ChrInsExt,
    FieldInsHandle, PlayerIns, SoloParamRepository, WorldChrMan, WorldChrManDbgFlags,
};
use eldenring::fd4::FD4TaskData;
use eldenring::position::{BlockPosition, HavokPosition, PositionDelta};
use fromsoftware_shared::{F32Vector4, FromStatic, SharedTaskImpExt};

// Marker SpEffects (built by build_wylder_params.py BIND_SPEFFECTS).
const SPEFFECT_SKILL: i32 = 9103001;
const SPEFFECT_ULTIMATE: i32 = 9103002;
const SPEFFECT_SKILL_HELD: i32 = 9103003;
const SPEFFECT_ULTIMATE_HELD: i32 = 9103004;
const SPEFFECT_CROUCH: i32 = 9103005;
const SPEFFECT_HOOK_PULL: i32 = 9103010;
const SPEFFECT_HOOK_MOVE: i32 = 9103011;
const SPEFFECT_SKILL_COOLDOWN: i32 = 9103020;
/// Nightreign's Claw Shot hit mark (30 s, applied by hit bullet 98800001).
const SPEFFECT_CLAW_MARK: i32 = 8880001;
/// Nightreign's Claw Shot hit bullet (ported to Elden Ring's Bullet param).
const CLAW_HIT_BULLET: i32 = 98800001;

/// How long after the release the claw can still hook something.
const HOOK_WINDOW: Duration = Duration::from_millis(1500);
/// Claw Shot fire animations (ground, air) and the time their AttackBehavior starts (TAE 0.167 s).
const FIRE_ANIMS: [i32; 2] = [900500000, 900505000];
const FIRE_TIME: f32 = 0.17;
/// Hook reach (m, to the target's edge) and how far (m, beyond its hit radius) an enemy may be off the aim line without lock-on.
const CLAW_RANGE: f32 = 20.0;
const AIM_SLACK: f32 = 0.8;
/// Locked on: how far (m, horizontally, beyond its hit radius) a character may be from the lock-on point to count.
const LOCK_ON_SLACK: f32 = 1.5;
/// Elden Ring TEAM_TYPE values that are not targets (none, the player, co-op and friendly NPCs, neutral, objects,
/// spirit summons). Everything else is: field enemies log as team 48, which the Smithbox enum calls "Unknown".
const FRIENDLY_TEAMS: [u8; 14] = [0, 1, 2, 8, 12, 14, 19, 20, 22, 26, 28, 30, 31, 47];
/// Enemies Nightreign doesn't know: a hit radius below this is pulled in, bigger drags Wylder to them (agrees with
/// Nightreign's mark on 241 of 279 shared models, src/build_claw_targets.py).
const SMALL_TARGET_RADIUS: f32 = 0.75;
/// Pull / drag: speeds (m/s; the pull is a bit slower so the pulled target stays readable), stop distance (m),
/// longest time.
const PULL_SPEED: f32 = 18.0;
const DRAG_SPEED: f32 = 23.0;
const STOP_DISTANCE: f32 = 2.0;
const MOVE_TIME: Duration = Duration::from_millis(1500);
/// NR's drag: about 0.62 s at about 23 m/s (7 m), then the follow-up clip carries him to about 9.5 m (refs/wylder/*: 3 clean shots).
const DRAG_TIME: Duration = Duration::from_millis(620);
/// Terrain hook: ray filter (walls and ground, from the earlier wall-check work), nearest point worth dragging to (m), how
/// close the drag ends, chest height the claw fires from, and the view axis in CSCam (matrix at +0x10, third row).
const TERRAIN_FILTER: u32 = 0x2000058;
const TERRAIN_MIN: f32 = 2.0;
/// Offsets from the aim (right, up; about 6 degrees), exact aim first, lower ones before upper.
const TERRAIN_AIM_FAN: [(f32, f32); 7] = [(0.0, 0.0), (0.0, -0.1), (-0.1, 0.0), (0.1, 0.0), (0.0, 0.1), (-0.1, -0.1), (0.1, -0.1)];
const TERRAIN_STOP: f32 = 0.3;
const CLAW_ORIGIN_HEIGHT: f32 = 1.4;
const CAM_VIEW_AXIS: usize = 0x30;
const FLOOR_CLEARANCE: f32 = 0.3;
const KNEE_HEIGHT: f32 = 0.5;
const BODY_WIDTH: f32 = 0.5;

const XINPUT_GAMEPAD_Y: u16 = 0x8000;
const XINPUT_GAMEPAD_LEFT_THUMB: u16 = 0x0040;
const XINPUT_GAMEPAD_RIGHT_THUMB: u16 = 0x0080;
const TRIGGER_PRESSED: u8 = 64;

#[repr(C)]
pub(crate) struct XInputGamepad {
    pub buttons: u16,
    pub left_trigger: u8,
    pub right_trigger: u8,
    pub thumb_lx: i16,
    pub thumb_ly: i16,
    pub thumb_rx: i16,
    pub thumb_ry: i16,
}

#[repr(C)]
pub(crate) struct XInputState {
    pub packet_number: u32,
    pub gamepad: XInputGamepad,
}

type XInputGetStateFn = unsafe extern "system" fn(u32, *mut XInputState) -> u32;

unsafe extern "system" {
    fn GetModuleHandleA(name: *const u8) -> *const u8;
    fn GetProcAddress(module: *const u8, name: *const u8) -> usize;
    fn VirtualProtect(address: *mut c_void, size: usize, protect: u32, old: *mut u32) -> i32;
    fn GetModuleFileNameA(module: *const c_void, name: *mut u8, size: u32) -> u32;
}

static ORIGINAL: AtomicUsize = AtomicUsize::new(0);
static SKILL: AtomicBool = AtomicBool::new(false);
static ULTIMATE: AtomicBool = AtomicBool::new(false);
static SKILL_HELD: AtomicBool = AtomicBool::new(false);
static SKILL_RELEASED: AtomicBool = AtomicBool::new(false);
static ULTIMATE_HELD: AtomicBool = AtomicBool::new(false);
/// Y + L3: crouch or stand (user); L3 alone is Surge Sprint.
static CROUCH: AtomicBool = AtomicBool::new(false);
/// Per pad: both sticks clicked in (L3 + R3), the unstuck hold.
static BOTH_STICKS: [AtomicBool; 4] = [const { AtomicBool::new(false) }; 4];
static L3_DOWN: [AtomicBool; 4] = [const { AtomicBool::new(false) }; 4];
/// Per pad: Y is held and a trigger or L3 was used with it (the game keeps seeing neither until Y is released).
static COMBO: [AtomicBool; 4] = [const { AtomicBool::new(false) }; 4];
static TRIGGERS_DOWN: [[AtomicBool; 2]; 4] = [const { [const { AtomicBool::new(false) }; 2] }; 4];
static LOG: Mutex<Option<std::fs::File>> = Mutex::new(None);
/// Claw Shot drag table from native/claw_targets.txt: (NpcParam rows, models = row / 10000) -> drags Wylder.
static CLAW_TARGETS: std::sync::OnceLock<(HashMap<i32, bool>, HashMap<i32, bool>)> = std::sync::OnceLock::new();

/// Elden Ring reads the user's pad itself; only Nightreign needs the launcher's copy (src/nr_rig).
#[cfg(feature = "rig")]
pub(crate) fn real_pad() -> Option<(u32, u16, u8, u8, [i16; 4])> {
    None
}

#[cfg(feature = "rig")]
pub(crate) fn rec_start(path: std::path::PathBuf) {
    rig::start(path);
}

#[cfg(feature = "rig")]
pub(crate) fn rec_stop() {
    rig::stop();
}

pub(crate) fn log(line: &str) {
    if let Ok(mut guard) = LOG.lock() {
        if let Some(file) = guard.as_mut() {
            let _ = writeln!(file, "{line}");
        }
    }
}

unsafe extern "system" fn xinput_get_state(index: u32, state: *mut XInputState) -> u32 {
    let original: XInputGetStateFn = unsafe { std::mem::transmute(ORIGINAL.load(Ordering::Relaxed)) };
    let result = unsafe { original(index, state) };
    #[cfg(feature = "rig")]
    let result = pad_script::feed(index, state, result);
    if result != 0 || state.is_null() || index > 3 {
        return result;
    }
    let pad = unsafe { &mut (*state).gamepad };
    let i = index as usize;
    let y = pad.buttons & XINPUT_GAMEPAD_Y != 0;
    let down = [pad.left_trigger >= TRIGGER_PRESSED, pad.right_trigger >= TRIGGER_PRESSED];
    let l3 = pad.buttons & XINPUT_GAMEPAD_LEFT_THUMB != 0;
    BOTH_STICKS[i].store(l3 && pad.buttons & XINPUT_GAMEPAD_RIGHT_THUMB != 0, Ordering::Relaxed);
    if y && l3 && !L3_DOWN[i].swap(true, Ordering::Relaxed) {
        CROUCH.store(true, Ordering::Relaxed);
    } else if !l3 {
        L3_DOWN[i].store(false, Ordering::Relaxed);
    }
    if y && (down[0] || down[1] || l3) {
        COMBO[i].store(true, Ordering::Relaxed);
    } else if !y {
        COMBO[i].store(false, Ordering::Relaxed);
    }
    let combo = COMBO[i].load(Ordering::Relaxed);
    for (t, flag) in [&SKILL, &ULTIMATE].into_iter().enumerate() {
        let was = TRIGGERS_DOWN[i][t].swap(down[t], Ordering::Relaxed);
        if y && down[t] && !was {
            flag.store(true, Ordering::Relaxed);
        }
        // The skill fires when LT is let go (or Y, which ends the combo) after a press.
        if t == 0 && was && (!down[t] || !y) && SKILL_HELD.load(Ordering::Relaxed) {
            SKILL_RELEASED.store(true, Ordering::Relaxed);
        }
    }
    SKILL_HELD.store(combo && y && down[0], Ordering::Relaxed);
    ULTIMATE_HELD.store(combo && y && down[1], Ordering::Relaxed);
    if combo {
        pad.buttons &= !(XINPUT_GAMEPAD_Y | XINPUT_GAMEPAD_LEFT_THUMB);
        pad.left_trigger = 0;
        pad.right_trigger = 0;
    }
    result
}

/// Point the game's XInputGetState import (xinput1_4.dll, imported by ordinal) at the wrapper.
unsafe fn patch_xinput_import() -> Result<usize, &'static str> {
    unsafe {
        let target = proc_address(c"xinput1_4.dll", c"XInputGetState");
        if target == 0 {
            return Err("XInputGetState not found");
        }
        ORIGINAL.store(target, Ordering::Relaxed);
        match patch_import(target, xinput_get_state as *const () as usize) {
            0 => Err("no import slot points at XInputGetState"),
            n => Ok(n),
        }
    }
}

pub(crate) unsafe fn proc_address(module: &std::ffi::CStr, name: &std::ffi::CStr) -> usize {
    unsafe {
        let handle = GetModuleHandleA(module.as_ptr().cast());
        if handle.is_null() { 0 } else { GetProcAddress(handle, name.as_ptr().cast()) }
    }
}

/// Point every import slot of the game holding `target` at `hook`; returns how many.
pub(crate) unsafe fn patch_import(target: usize, hook: usize) -> usize {
    unsafe {
        let base = GetModuleHandleA(std::ptr::null());
        let nt = base.add(*(base.add(0x3c) as *const u32) as usize);
        // PE32+ optional header at nt + 24; data directory 12 (IAT) at optional header + 112 + 12 * 8.
        let iat_dir = nt.add(24 + 112 + 12 * 8);
        let (rva, size) = (*(iat_dir as *const u32) as usize, *(iat_dir.add(4) as *const u32) as usize);
        let mut patched = 0;
        for slot in (0..size / 8).map(|k| base.add(rva + k * 8) as *mut usize) {
            if *slot == target {
                let mut old = 0;
                VirtualProtect(slot.cast(), 8, 0x04, &mut old); // PAGE_READWRITE
                *slot = hook;
                VirtualProtect(slot.cast(), 8, old, &mut old);
                patched += 1;
            }
        }
        patched
    }
}

fn has_speffect(chr: &ChrIns, id: i32) -> Option<f32> {
    chr.special_effect.entries().find(|e| e.param_id == id).map(|e| e.removal_timer)
}

/// Newest animation in the time-act queue.
pub(crate) fn current_anim(chr: &ChrIns) -> (i32, f32) {
    let ta = &chr.modules.time_act;
    let a = &ta.anim_queue[(ta.write_idx as usize + 9) % 10];
    (a.anim_id, a.play_time)
}

pub(crate) fn position(chr: &ChrIns) -> HavokPosition {
    chr.modules.physics.position
}

/// Ride link: (ride state 0/3/5/7, rider done mounting, is the ridden one), or None without a ride module. Read through raw
/// pointers: not every character may have the module or node.
fn ride_info(chr: &ChrIns) -> Option<(u32, bool, bool)> {
    let module = unsafe { *(&chr.modules.ride as *const _ as *const *const eldenring::cs::CSChrRideModule) };
    let module = unsafe { module.as_ref() }?;
    let node = unsafe { *(&module.ride_node as *const _ as *const *const eldenring::cs::CSRideNode) };
    let state = unsafe { node.as_ref() }.map_or(0, |n| n.ride_state);
    Some((state, module.is_mounted, module.is_ride_character))
}

/// A rider or its mount: the rider is snapped to the mount each frame, so it can't be pulled; Wylder goes to them instead.
fn mounted(chr: &ChrIns) -> bool {
    ride_info(chr).is_some_and(|(state, on, ridden)| state != 0 || on || ridden)
}

fn load_claw_targets(path: &std::path::Path) {
    let (mut rows, mut models) = (HashMap::new(), HashMap::new());
    for line in std::fs::read_to_string(path).unwrap_or_default().lines() {
        let mut parts = line.split(' ');
        let (Some(kind), Some(Ok(id)), Some(drag)) = (parts.next(), parts.next().map(str::parse), parts.next()) else { continue };
        match kind {
            "r" => rows.insert(id, drag == "1"),
            "m" => models.insert(id, drag == "1"),
            _ => None,
        };
    }
    log(&format!("Claw Shot targets: {} models, {} row exceptions", models.len(), rows.len()));
    let _ = CLAW_TARGETS.set((rows, models));
}

/// Whether hooking this target drags Wylder to it, and why: Nightreign's no-pull mark (SpEffect 700500) by NpcParam
/// row, else by model, else by hit radius; riders and mounts always drag.
fn claw_drags(chr: &ChrIns) -> (bool, &'static str) {
    if mounted(chr) {
        return (true, "mounted");
    }
    let id = chr.npc_param_id;
    if let Some((rows, models)) = CLAW_TARGETS.get() {
        if let Some(&drag) = rows.get(&id) {
            return (drag, "NR row");
        }
        if let Some(&drag) = models.get(&(id / 10000)) {
            return (drag, "NR model");
        }
    }
    (chr.modules.physics.hit_radius >= SMALL_TARGET_RADIUS, "radius")
}

/// Where a drag aims: a rider's seat is above the mount, so aim at the mount's body when the rider knows it.
fn drag_goal(chr: &ChrIns) -> HavokPosition {
    let p = position(chr);
    if ride_info(chr).is_some_and(|(_, on, _)| on) {
        let module = unsafe { *(&chr.modules.ride as *const _ as *const *const eldenring::cs::CSChrRideModule) };
        let m = unsafe { &(*module).mount_data.mount_position };
        if (m.0 - p.0).powi(2) + (m.1 - p.1).powi(2) + (m.2 - p.2).powi(2) < 9.0 {
            return HavokPosition(m.0, m.1, m.2, p.3);
        }
    }
    p
}

/// Move `chr` toward `goal` by at most `step` metres; returns the distance left.
fn step_toward(chr: &mut ChrIns, goal: HavokPosition, step: f32, stop: f32) -> f32 {
    let p = &mut chr.modules.physics;
    let d = [goal.0 - p.position.0, goal.1 - p.position.1, goal.2 - p.position.2];
    let dist = (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt();
    if dist > stop {
        let k = (step / dist).min((dist - stop) / dist);
        p.position = HavokPosition(p.position.0 + d[0] * k, p.position.1 + d[1] * k, p.position.2 + d[2] * k, p.position.3);
        p.chr_proxy_pos_update_requested = true;
    }
    dist
}

/// Face where the hook caught: the follow-up clip carries him along his facing, so a camera aim away from it pulled him one way, then
/// the other (user).
fn face_toward(player: &mut ChrIns, to: [f32; 3]) {
    let p = position(player);
    let (dx, dz) = (to[0] - p.0, to[2] - p.2);
    if dx.hypot(dz) < 0.01 {
        return;
    }
    // Inverse of facing(): a turn about y by phi gives facing (-sin phi, -cos phi).
    let half = (-dx).atan2(-dz) * 0.5;
    player.modules.physics.orientation = eldenring::rotation::Quaternion(0.0, half.sin(), 0.0, half.cos());
}

/// Wylder's point on terrain the claw reaches along the camera's aim. The camera matrix's third row is its view axis; its sign
/// is taken from the player's facing, since he turns to the aim while it is held.
fn aim_direction(player: &PlayerIns) -> Option<[f32; 3]> {
    let camera = unsafe { CSCamera::instance() }.ok()?;
    let cam = &*camera.pers_cam_1 as *const _ as *const u8;
    let axis = unsafe { std::ptr::read_unaligned(cam.add(CAM_VIEW_AXIS) as *const [f32; 3]) };
    let len = (axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2]).sqrt();
    if !(0.5..2.0).contains(&len) {
        log(&format!("Claw Shot: odd camera axis {axis:?}"));
        return None;
    }
    let (fx, fz) = facing(&player.chr_ins.modules.physics.orientation);
    let sign = if axis[0] * fx + axis[2] * fz < 0.0 { -1.0 } else { 1.0 };
    Some([axis[0] * sign / len, axis[1] * sign / len, axis[2] * sign / len])
}

/// Nothing solid between the claw and a point `to` (relative to the claw's origin), `dist` metres away.
fn clear_line(player: &PlayerIns, to: [f32; 3], dist: f32) -> bool {
    let p = position(&player.chr_ins);
    let origin = HavokPosition(p.0, p.1 + CLAW_ORIGIN_HEIGHT, p.2, p.3);
    let Ok(havok) = (unsafe { CSHavokMan::instance() }) else { return true };
    match havok.phys_world.cast_ray(TERRAIN_FILTER, &origin, PositionDelta(to[0], to[1], to[2]), player) {
        Some(h) => ((h.0 - origin.0).powi(2) + (h.1 - origin.1).powi(2) + (h.2 - origin.2).powi(2)).sqrt() >= dist - 0.5,
        None => true,
    }
}

fn terrain_hook(player: &PlayerIns) -> Option<HavokPosition> {
    let dir = aim_direction(player)?;
    let p = position(&player.chr_ins);
    let origin = HavokPosition(p.0, p.1 + CLAW_ORIGIN_HEIGHT, p.2, p.3);
    let havok = unsafe { CSHavokMan::instance() }.ok()?;
    // The exact aim first, then a small ring around it: the middle of the screen isn't quite the chest's line, and an aim just past
    // a ledge or at the sky did nothing at all (user).
    let (hit, dist) = TERRAIN_AIM_FAN.iter().find_map(|&(right, up)| {
        let (rx, rz) = (-dir[2], dir[0]);
        let d = [dir[0] + rx * right, dir[1] + up, dir[2] + rz * right];
        let reach = PositionDelta(d[0] * CLAW_RANGE, d[1] * CLAW_RANGE, d[2] * CLAW_RANGE);
        let hit = havok.phys_world.cast_ray(TERRAIN_FILTER, &origin, reach, player)?;
        let dist = ((hit.0 - origin.0).powi(2) + (hit.1 - origin.1).powi(2) + (hit.2 - origin.2).powi(2)).sqrt();
        (dist >= TERRAIN_MIN).then_some((hit, dist))
    })?;
    log(&format!("Claw Shot terrain ray {dist:.1} m"));
    // Stand just short of the hit: on the floor there if there is one, else hanging with the chest at the hit.
    let (x, z) = (hit.0 - dir[0] * 0.6, hit.2 - dir[2] * 0.6);
    let feet = floor_under(player, x, hit.1 + 0.5, z, 2.0).map_or(hit.1 - CLAW_ORIGIN_HEIGHT, |f| f + FLOOR_CLEARANCE);
    Some(HavokPosition(x, feet, z, p.3))
}

/// Height of the first surface below (x, y, z), within `depth` metres.
fn floor_under(player: &PlayerIns, x: f32, y: f32, z: f32, depth: f32) -> Option<f32> {
    let havok = unsafe { CSHavokMan::instance() }.ok()?;
    let from = HavokPosition(x, y, z, 0.0);
    havok.phys_world.cast_ray(TERRAIN_FILTER, &from, PositionDelta(0.0, -depth, 0.0), player).map(|h| h.1)
}

/// Would this frame's step put the body into something? Rays from the knees and the chest along the path, a body's width
/// further than the step. The drag ends there and the game's own physics takes over, instead of pushing him inside.
fn path_blocked(player: &PlayerIns, goal: HavokPosition, step: f32) -> bool {
    let p = position(&player.chr_ins);
    let d = [goal.0 - p.0, goal.1 - p.1, goal.2 - p.2];
    let dist = (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt().max(0.01);
    let reach = (step + BODY_WIDTH) / dist;
    let Ok(havok) = (unsafe { CSHavokMan::instance() }) else { return false };
    [KNEE_HEIGHT, CLAW_ORIGIN_HEIGHT].iter().any(|h| {
        let from = HavokPosition(p.0, p.1 + h, p.2, p.3);
        havok.phys_world.cast_ray(TERRAIN_FILTER, &from, PositionDelta(d[0] * reach, d[1] * reach, d[2] * reach), player).is_some()
    })
}

/// Never let the drag put the feet under the ground: a character below the terrain falls through the world.
fn keep_above_floor(player: &mut PlayerIns) {
    let p = position(&player.chr_ins);
    if let Some(floor) = floor_under(player, p.0, p.1 + CLAW_ORIGIN_HEIGHT, p.2, CLAW_ORIGIN_HEIGHT + 0.5) {
        if p.1 < floor + FLOOR_CLEARANCE {
            let ph = &mut player.chr_ins.modules.physics;
            ph.position = HavokPosition(p.0, floor + FLOOR_CLEARANCE, p.2, p.3);
            ph.chr_proxy_pos_update_requested = true;
        }
    }
}

/// Diagnostics while the claw is out: animations the player plays and bullets alive (param ids), each logged once.
fn state_seen() -> std::sync::MutexGuard<'static, Vec<(char, i32)>> {
    static SEEN: Mutex<Vec<(char, i32)>> = Mutex::new(Vec::new());
    SEEN.lock().unwrap()
}

fn log_new_anims_and_bullets(mut seen: std::sync::MutexGuard<'static, Vec<(char, i32)>>, player: &ChrIns) {
    let mut ids: Vec<(char, i32)> = player.modules.time_act.anim_queue.iter().map(|a| ('a', a.anim_id)).collect();
    if let Ok(bullets) = unsafe { CSBulletManager::instance() } {
        for b in bullets.bullets() {
            for p in [&b.wait_state.base.param, &b.fly_state.base.param, &b.exp_state.base.param] {
                ids.push(('b', p.param_id));
            }
        }
    }
    for id in ids {
        if id.1 > 0 && !seen.contains(&id) {
            seen.push(id);
            log(&format!("  {} {}", if id.0 == 'a' { "anim" } else { "bullet" }, id.1));
        }
    }
}

/// Layout of eldenring::cs::BulletSpawnData (0x110 bytes; the crate keeps its fields private).
#[repr(C)]
struct SpawnData {
    owner: FieldInsHandle,
    behavior_id: i32,
    magic_id: i32,
    unk10: u32,
    bullet_id: i32,
    goods_id: i32,
    dummy_poly_id: i32,
    target: FieldInsHandle,
    unk28: [u32; 2],
    unk30: F32Vector4,
    unk40: [u32; 4],
    acceleration_angle: F32Vector4,
    unk60: F32Vector4,
    angle: F32Vector4,
    position: F32Vector4,
    unk90: [u8; 0x80],
}
const _: () = assert!(size_of::<SpawnData>() == size_of::<BulletSpawnData>());

/// Spawn a bullet param owned by the player at `position`, flying along the player's facing.
fn spawn_bullet(player: &ChrIns, target: FieldInsHandle, bullet_id: i32, position: F32Vector4) -> Result<(), i32> {
    let (fx, fz) = facing(&player.modules.physics.orientation);
    let zero = F32Vector4(0.0, 0.0, 0.0, 0.0);
    let data = SpawnData {
        owner: player.field_ins_handle,
        behavior_id: -1,
        magic_id: -1,
        unk10: 0,
        bullet_id,
        goods_id: -1,
        dummy_poly_id: -1,
        target,
        unk28: [0; 2],
        unk30: zero,
        unk40: [0; 4],
        acceleration_angle: zero,
        unk60: zero,
        angle: F32Vector4(fx, 0.0, fz, 0.0),
        position,
        unk90: [0; 0x80],
    };
    let manager = unsafe { CSBulletManager::instance_mut() }.map_err(|_| -2)?;
    manager.spawn_bullet(unsafe { &*(&data as *const SpawnData).cast::<BulletSpawnData>() })
}

/// Nightreign's claw hit (bullet 98800001: 1.7 m sphere, NR attack 878800000 = 120 magic + base attack, small flinch,
/// mark 8880001), spawned at the hooked character's centre and owned by the player.
fn spawn_claw_hit(player: &ChrIns, target: &ChrIns) -> Result<(), i32> {
    let t = position(target);
    let at = F32Vector4(t.0, t.1 + target.modules.physics.hit_height * 0.5, t.2, 1.0);
    spawn_bullet(player, target.field_ins_handle, CLAW_HIT_BULLET, at)
}

/// Onslaught Stake's fire (heroes/wylder.toml ultimate.fire_hits): a flat hit of its own, because a flat element on the
/// weapon-tied attack rows does nothing. (animation, strike time from its TAE, bullet).
const STAKE_FIRE_HITS: [(i32, f32, i32); 5] = [
    (900600000, 1.867, 30900901), (900600100, 1.867, 30900901), (900600200, 1.867, 30900901),
    (900600005, 0.6, 30900902), (900605000, 0.633, 30900902),
];
/// Stand-in for NR's gauge (NOTES "GAUGE"): a plain cooldown, the user's choice of a reasonable one for now.
/// The gauge: NR charges per hit (AtkParam ultimateChargeCorrection, 0 on the Stake's own rows), scaled here by how hard the hit was
/// against his recent average, so it doesn't depend on level. About 13 average hits fill it, by the user's feel, not measured in NR.
const GAUGE_PER_HIT: f32 = 0.075;
const GAUGE_NEAR: f32 = 30.0;
const STAKE_ANIMS: std::ops::Range<i32> = 900600000..900606000;
const STAKE_START_ANIMS: [i32; 4] = [900600000, 900600100, 900600200, 900605000];
const STAKE_REACH: f32 = 1.0;
const STAKE_HEIGHT: f32 = 1.1;

#[derive(Default)]
struct Stake {
    anim: i32,
    play: f32,
}

fn stake_fire_frame(stake: &mut Stake, player: &ChrIns) {
    let (anim, play) = current_anim(player);
    if anim != stake.anim || play < stake.play {
        stake.anim = anim;
        stake.play = -1.0;
    }
    for &(a, time, bullet) in &STAKE_FIRE_HITS {
        if a == anim && stake.play < time && play >= time {
            let (fx, fz) = facing(&player.modules.physics.orientation);
            let p = position(player);
            let at = F32Vector4(p.0 + fx * STAKE_REACH, p.1 + STAKE_HEIGHT, p.2 + fz * STAKE_REACH, 1.0);
            match spawn_bullet(player, player.field_ins_handle, bullet, at) {
                Ok(()) => log(&format!("Stake: fire hit {bullet}")),
                Err(e) => log(&format!("Stake: fire hit {bullet} NOT spawned (error {e})")),
            }
        }
    }
    stake.play = play;
}

/// NR's jumping Stake holds him up (TAE type 154, which ER lacks). Height against clip time, from the start of the clip, averaged
/// from two NR recordings (refs/wylder/*): up a little, down to the strike. Holding only the hang did nothing visible (user): an ER
/// jump is barely off the ground when the clip starts, so he also lifts to NR's height. What looked like a hang after the strike is
/// the recoil below.
const STAKE_AIR_ANIM: i32 = 900605000;
const STAKE_AIR_PROFILE: [(f32, f32); 5] = [(0.0, 0.0), (0.2, 0.45), (0.4, 0.4), (0.62, -0.7), (STAKE_AIR_RECOIL_TIME, -0.7)];
/// NR's clip starts about this far above the ground.
const STAKE_AIR_START: f32 = 1.9;
const STAKE_AIR_LIFT_TIME: f32 = 0.2;
/// Then NR kicks him back off the strike (TAE 530, which ER lacks: ChrPhysicsVelocityChangeParam 11001 = 12.5 m/s back, 5 m/s up).
/// Gravity fitted to the NR recording (refs/wylder/nr_user2.jsonl 120.96-121.58 s: 7.3 m back, 0.56 m up first). Until he lands or
/// meets something; the game's physics takes over from there.
const STAKE_AIR_RECOIL_TIME: f32 = 0.767;
const STAKE_AIR_RECOIL_BACK: f32 = 12.5;
const STAKE_AIR_RECOIL_UP: f32 = 5.0;
const STAKE_AIR_RECOIL_GRAVITY: f32 = 21.5;
const STAKE_AIR_RECOIL_MAX: f32 = 2.0;

#[derive(Default)]
struct StakeAir {
    /// (height when the clip started, height to lift to).
    hang: Option<(f32, f32)>,
    /// (where it started, when, facing then).
    recoil: Option<(HavokPosition, Instant, (f32, f32))>,
    recoil_done: bool,
}

fn profile_height(play: f32) -> f32 {
    for w in STAKE_AIR_PROFILE.windows(2) {
        if play <= w[1].0 {
            return w[0].1 + (w[1].1 - w[0].1) * (play - w[0].0) / (w[1].0 - w[0].0);
        }
    }
    STAKE_AIR_PROFILE[STAKE_AIR_PROFILE.len() - 1].1
}

fn set_position(player: &mut PlayerIns, to: HavokPosition) {
    let ph = &mut player.chr_ins.modules.physics;
    ph.position = to;
    ph.chr_proxy_pos_update_requested = true;
}

fn stake_air(air: &mut StakeAir, player: &mut PlayerIns) {
    let (anim, play) = current_anim(&player.chr_ins);
    if anim != STAKE_AIR_ANIM {
        *air = StakeAir::default();
        return;
    }
    let p = position(&player.chr_ins);
    // Once the recoil has begun, a clip looping back to 0 must not restart the hang.
    if play < STAKE_AIR_RECOIL_TIME && air.recoil.is_none() && !air.recoil_done {
        if air.hang.is_none() {
            let floor = floor_under(player, p.0, p.1 + 1.0, p.2, 6.0);
            air.hang = Some((p.1, floor.map_or(p.1, |f| p.1.max(f + STAKE_AIR_START))));
        }
        let (start, base) = air.hang.unwrap();
        let y = start + (base - start) * (play / STAKE_AIR_LIFT_TIME).min(1.0) + profile_height(play);
        set_position(player, HavokPosition(p.0, y, p.2, p.3));
        keep_above_floor(player);
        return;
    }
    if air.recoil_done {
        return;
    }
    let (origin, since, (fx, fz)) =
        *air.recoil.get_or_insert_with(|| (p, Instant::now(), facing(&player.chr_ins.modules.physics.orientation)));
    let t = since.elapsed().as_secs_f32();
    let goal = HavokPosition(
        origin.0 - fx * STAKE_AIR_RECOIL_BACK * t,
        origin.1 + STAKE_AIR_RECOIL_UP * t - 0.5 * STAKE_AIR_RECOIL_GRAVITY * t * t,
        origin.2 - fz * STAKE_AIR_RECOIL_BACK * t,
        p.3,
    );
    let step = ((goal.0 - p.0).powi(2) + (goal.1 - p.1).powi(2) + (goal.2 - p.2).powi(2)).sqrt();
    let falling = STAKE_AIR_RECOIL_UP < STAKE_AIR_RECOIL_GRAVITY * t;
    let floor = floor_under(player, goal.0, p.1.max(goal.1) + 0.5, goal.2, (p.1 - goal.1).max(0.0) + 1.0);
    let landed = falling && floor.is_some_and(|f| goal.1 <= f + FLOOR_CLEARANCE);
    if t > STAKE_AIR_RECOIL_MAX || landed || path_blocked(player, goal, step) {
        if landed {
            set_position(player, HavokPosition(goal.0, floor.unwrap() + FLOOR_CLEARANCE, goal.2, p.3));
        }
        let moved = ((p.0 - origin.0).powi(2) + (p.2 - origin.2).powi(2)).sqrt();
        log(&format!("Stake: air recoil ended after {t:.2} s, {moved:.1} m back ({})", if landed { "landed" } else { "blocked or timed out" }));
        air.recoil_done = true;
        return;
    }
    set_position(player, goal);
    keep_above_floor(player);
}

/// Sixth Sense: recorded in NR: the lethal hit plays a forced dodge (the script's marker here, heroes/wylder.toml). "Cheat death a single
/// time", until restored at a Site of Grace or by revival (NR text). While it's ready the player can't die from a hit; the hit that
/// would kill takes no HP at all (user's choice; NR not measured) and plays the dodge. A fall still kills:
/// without that a player falling out of the world would never die.
const SPEFFECT_SIXTH_DODGE: i32 = 9103030;
/// The dodge's invincibility: NR's clip holds 430 for 0.67 s; a little more because the dodge can start a few frames late.
const SIXTH_INVINCIBLE: Duration = Duration::from_millis(1000);
const CLAW_COOLDOWN: f32 = 8.0;
/// Optional add-on, NR's relic "[Wylder] +1 additional Character Skill use" (SpEffect 7033200, additionalCharacterSkillUse 1):
/// this file next to the DLL gives the Claw Shot 2 charges. Each charge has its own 8 s refill, but only one refills at a time
/// (user's account of NR). The cooldown SpEffect is the refill clock.
const TWO_CLAWS_FILE: &str = "claw_two_uses.txt";

struct ClawCharges {
    max: u32,
    ready: u32,
    /// A refill was started; `seen` once the cooldown SpEffect showed up, so a refill applied this frame isn't taken as finished.
    refilling: bool,
    seen: bool,
    /// A charge spent on a press whose shot isn't confirmed yet, and when the button came up. A press the game refused (too soon
    /// after the last shot, user report) never plays a fire animation: the charge comes back after the hook window.
    unconfirmed: Option<Option<Instant>>,
}

impl ClawCharges {
    /// Advances the refill and spends a charge on a press. Returns whether the press may shoot.
    fn frame(&mut self, player: &mut PlayerIns, cooling: bool, pressed: bool) -> bool {
        if self.refilling {
            if cooling {
                self.seen = true;
            } else if self.seen {
                self.refilling = false;
                self.ready = (self.ready + 1).min(self.max);
                log(&format!("Claw charge back: {}/{}", self.ready, self.max));
            }
        }
        let shoot = pressed && self.ready > 0;
        if shoot {
            self.ready -= 1;
            if self.unconfirmed.is_some() {
                log("Claw charge: earlier press never fired, kept spent");
            }
            self.unconfirmed = Some(None);
        }
        if self.ready < self.max && !self.refilling {
            player.apply_speffect(SPEFFECT_SKILL_COOLDOWN, true);
            self.refilling = true;
            self.seen = false;
        }
        shoot
    }

    /// Confirms the charge once a fire animation starts after the release, or gives it back if none did.
    fn confirm(&mut self, player: &mut PlayerIns, released: bool) {
        let Some(up) = self.unconfirmed else { return };
        let up = match up {
            None if released => { self.unconfirmed = Some(Some(Instant::now())); return; }
            None => return,
            Some(t) => t,
        };
        // Newest animation, started since the release: an older shot's fire clip may still be playing.
        let (anim, play) = current_anim(&player.chr_ins);
        if FIRE_ANIMS.contains(&anim) && play <= up.elapsed().as_secs_f32() + 0.1 {
            self.unconfirmed = None;
        } else if up.elapsed() > HOOK_WINDOW {
            self.unconfirmed = None;
            self.ready += 1;
            if self.ready >= self.max && self.refilling {
                player.remove_speffect(SPEFFECT_SKILL_COOLDOWN);
                self.refilling = false;
            }
            log(&format!("Claw charge given back, no shot: {}/{}", self.ready, self.max));
        }
    }
}
/// Airborne this long, or this soon after, a lethal hit is taken to be a killbox: Sixth Sense lets it through.
const FALL_NO_SAVE_AIR: f32 = 0.5;
const FALL_NO_SAVE_AFTER: Duration = Duration::from_millis(500);
/// A lethal drop on the ground this long after a fall is still the fall's: once the engine's landing damage came after the 0.5 s
/// and Sixth Sense took it [User, Run: anim 12004210, fall timer 0].
const FALL_LANDING: Duration = Duration::from_millis(2500);
const SPEFFECT_NIGHTFARER: i32 = 9102900;
/// Elden Ring's sit-at-grace clips.
const GRACE_ANIMS: std::ops::Range<i32> = 68000..69000;
/// Unstuck: hold L3 + R3 this long. Back to where the last fall Elden Ring calls lethal began, or, with none, die as Elden Ring
/// would have (respawn at the last grace). NR has no fall damage, so ER's death pits became softlocks [User].
const UNSTUCK_HOLD: Duration = Duration::from_millis(2000);
/// Where unstuck goes: Elden Ring's own last safe position (PlayerIns::safe_block_pos, what a save loads into), the latest one at
/// or above the top of the lethal drop. Own ground tracking failed twice: slides and old points [User, Run].
const SAFE_HISTORY: usize = 64;
const SAFE_ABOVE_TOP: f32 = 0.5;

/// Elden Ring's position bookkeeping for the player, read before sixth_sense borrows him.
#[derive(Clone, Copy)]
struct Places {
    at: BlockPosition,
    block: BlockId,
    safe: BlockPosition,
    safe_block: BlockId,
}

struct Gauge {
    value: f32,
    mean_hit: f32,
    hp: HashMap<usize, i32>,
}

impl Gauge {
    fn hit(&mut self, damage: i32) {
        let damage = damage as f32;
        self.mean_hit = if self.mean_hit > 0.0 { self.mean_hit * 0.9 + damage * 0.1 } else { damage };
        self.value = (self.value + GAUGE_PER_HIT * (damage / self.mean_hit).clamp(0.5, 2.5)).min(1.0);
        log(&format!("Gauge {:.0} % (hit {damage})", self.value * 100.0));
    }
}

#[derive(Default)]
struct Fall {
    last: Option<Instant>,
    hp: i32,
    /// Last HP above 1: what Sixth Sense gives back.
    hp_safe: i32,
    top: f32,
    /// Top of the last airborne stretch, kept after landing (the lethal drop can come 0.5-1.3 s later [Run]).
    last_top: f32,
    was_airborne: bool,
    /// Elden Ring's safe positions as they changed, oldest first.
    safe: Vec<(BlockPosition, BlockId)>,
    /// Ground before the last fall the engine made lethal (HP to 1 on landing, given back): where unstuck goes. Block positions:
    /// ChrIns::chunk_position is a coarse grid (a warp by it went 64 m under a cave [Run]); havok space may shift [Inferred].
    rescue: Option<(BlockPosition, BlockId)>,
    hold: Option<Instant>,
    /// Where he should be after the warp, checked twice later (log).
    check: Vec<(Instant, HavokPosition)>,
}

/// Returns whether he's resting at a grace or just came back from death, which also resets the Stake's cooldown.
fn sixth_sense(used: &mut bool, dead: &mut bool, invincible_until: &mut Option<Instant>, fall: &mut Fall, places: Places, player: &mut ChrIns) -> bool {
    if invincible_until.is_some_and(|t| Instant::now() >= t) {
        *invincible_until = None;
        player.chr_flags1c5.set_is_invincible(false);
    } else if invincible_until.is_some() {
        player.chr_flags1c5.set_is_invincible(true);
    }
    let Ok(debug) = (unsafe { WorldChrManDbgFlags::instance_mut() }) else { return false };
    if has_speffect(player, SPEFFECT_NIGHTFARER).is_none() {
        debug.player_no_dead = false;
        return false;
    }
    let (anim, _) = current_anim(player);
    let rested = GRACE_ANIMS.contains(&(anim % 1_000_000));
    if *used && rested && player.modules.data.hp > 1 {
        *used = false;
        log("Sixth Sense restored at a grace");
    }
    let mut revived = false;
    // NR has no fall damage. Killboxes are scripted deaths, not this.
    player.modules.material.disable_fall_damage = true;
    let held = BOTH_STICKS.iter().any(|b| b.load(Ordering::Relaxed));
    let unstuck = match (held, fall.hold) {
        (false, _) => { fall.hold = None; false }
        (true, None) => { fall.hold = Some(Instant::now()); false }
        (true, Some(t)) if t.elapsed() >= UNSTUCK_HOLD => { fall.hold = Some(Instant::now() + Duration::from_secs(3600)); true }
        _ => false,
    };
    if let Some(&(t, to)) = fall.check.first().filter(|(t, _)| Instant::now() >= *t) {
        let h = player.modules.physics.position;
        log(&format!("Unstuck: later at {:.1} {:.1} {:.1} (goal {:.1} {:.1} {:.1}), {} ms past check", h.0, h.1, h.2, to.0, to.1, to.2, t.elapsed().as_millis()));
        fall.check.remove(0);
    }
    let fall_timer = player.modules.fall.fall_timer;
    let fall_death = player.chr_flags1c8.request_falldeath_camera();
    if fall_timer >= FALL_NO_SAVE_AIR || fall_death {
        fall.last = Some(Instant::now());
    }
    let after_fall = fall.last.is_some_and(|t| t.elapsed() < FALL_NO_SAVE_AFTER);
    let landing = fall.last.is_some_and(|t| t.elapsed() < FALL_LANDING);
    // Only a long time in the air counts (the killbox rule above). Any airborne moment (SpEffect 145) did before: a hit that knocked
    // him up left him at 1 HP with Sixth Sense skipped, and the Grafted Scion's death scene played [Run, user].
    let falling = fall_timer >= FALL_NO_SAVE_AIR || after_fall;
    let y = position(player).1;
    fall.top = if fall_timer > 0.0 { fall.top.max(y) } else { y };
    if fall_timer > 0.0 {
        fall.last_top = if fall.was_airborne { fall.last_top.max(y) } else { y };
    }
    fall.was_airborne = fall_timer > 0.0;
    if fall.safe.last().is_none_or(|&(p, b)| p != places.safe || b != places.safe_block) {
        if fall.safe.len() >= SAFE_HISTORY {
            fall.safe.remove(0);
        }
        fall.safe.push((places.safe, places.safe_block));
    }
    let mut hp = player.modules.data.hp;
    // After a fall, HP lost on touching the ground is fall damage and is given back; HP gone in the air is a killbox.
    // Later, up to FALL_LANDING, only a lethal drop on the ground is the fall's; other hits count as usual.
    let mut killbox = false;
    let physics = &player.modules.physics;
    let grounded = physics.is_touching_ground || physics.standing_on_solid_ground || physics.touching_solid_ground;
    let here = physics.position;
    // Block position y of the drop's top: havok and block space differ by a shift within one block.
    let top_block_y = places.at.y + fall.last_top - here.1;
    if hp < fall.hp && (after_fall || (landing && hp <= 1 && grounded)) {
        let since = fall.last.map_or(0, |t| t.elapsed().as_millis());
        log(&format!("Fall: hp {} -> {hp}, fell {:.1} m, timer {fall_timer:.2}, {since} ms after, grounded {grounded}, falling {}, fall death {fall_death}, anim {anim}",
                     fall.hp, fall.top - y, physics.is_falling));
        if after_fall && hp <= 1 && (fall_death || !grounded) {
            killbox = true;
            hp = 0;
            player.modules.data.hp = 0;
        } else if grounded {
            if hp <= 1 {
                fall.rescue = fall.safe.iter().rev().find(|&&(p, b)| b == places.block && p.y >= top_block_y - SAFE_ABOVE_TOP).copied();
                let recent: Vec<String> = fall.safe.iter().rev().take(4).map(|(p, b)| format!("{:.1} {:.1} {:.1} {}", p.x, p.y, p.z, b.0)).collect();
                log(&format!("Fall: lethal in Elden Ring at block {:.1} {:.1} {:.1} {}, drop top y {top_block_y:.1}, unstuck goes to {:?}; ER safe newest first: {}",
                             places.at.x, places.at.y, places.at.z, places.block.0, fall.rescue.map(|(p, _)| (p.x, p.y, p.z)), recent.join(" | ")));
            }
            hp = fall.hp;
            player.modules.data.hp = hp;
        }
    }
    if unstuck {
        if let Some((to, _)) = fall.rescue.take().filter(|&(_, b)| b == places.block) {
            let goal = HavokPosition(here.0 + to.x - places.at.x, here.1 + to.y - places.at.y, here.2 + to.z - places.at.z, here.3);
            log(&format!("Unstuck: block {:.1} {:.1} {:.1} -> {:.1} {:.1} {:.1}, havok {:.1} {:.1} {:.1} -> {:.1} {:.1} {:.1}",
                         places.at.x, places.at.y, places.at.z, to.x, to.y, to.z, here.0, here.1, here.2, goal.0, goal.1, goal.2));
            let ph = &mut player.modules.physics;
            ph.position = goal;
            ph.chr_proxy_pos_update_requested = true;
            let now = Instant::now();
            fall.check = vec![(now + Duration::from_millis(100), goal), (now + Duration::from_millis(1000), goal)];
        } else if hp > 0 {
            log("Unstuck: no lethal fall to undo, dying as Elden Ring would");
            killbox = true;
            hp = 0;
            player.modules.data.hp = 0;
        }
    }
    fall.hp = hp;
    if hp > 1 {
        fall.hp_safe = hp;
    }
    // Dying restores it too, once he's back.
    if hp <= 0 {
        *dead = true;
    } else if *dead {
        *dead = false;
        *used = false;
        revived = true;
        fall.rescue = None;
        log("Sixth Sense restored by death");
    }
    if !*used && hp == 1 && !falling && !rested {
        *used = true;
        log(&format!("Sixth Sense: fall timer {fall_timer:.2}, anim {anim}"));
        player.apply_speffect(SPEFFECT_SIXTH_DODGE, true);
        *invincible_until = Some(Instant::now() + SIXTH_INVINCIBLE);
        // He dodges it, so the hit takes nothing (user): the last HP above 1.
        if fall.hp_safe > 1 {
            player.modules.data.hp = fall.hp_safe;
            fall.hp = fall.hp_safe;
        }
        log(&format!("Sixth Sense: cheated death, hp {} kept", fall.hp_safe));
    }
    // Still protected through the dodge's hit frame, then ordinary damage applies.
    let dodging = has_speffect(player, SPEFFECT_SIXTH_DODGE).is_some();
    // Once dead, nothing holds him up until he's back.
    debug.player_no_dead = !*dead && (dodging || (!killbox && (landing || (!*used && !falling))));
    rested || revived
}

/// The fire scales with Strength + Dexterity like Wylder's sword: the base at his starting 16 + 12, +3.5 % per point above (user: less spammable than an FP skill, so it should reward levels).
/// Flat attack values don't scale by themselves in Elden Ring.
const STAKE_FIRE: [(u32, f32); 2] = [(1700000901, 450.0), (1700000902, 290.0)];
const STAKE_FIRE_BASE_STATS: f32 = 28.0;
const STAKE_FIRE_PER_POINT: f32 = 0.035;

fn scale_stake_fire(strength: u32, dexterity: u32) {
    let Ok(params) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    let factor = 1.0 + STAKE_FIRE_PER_POINT * ((strength + dexterity) as f32 - STAKE_FIRE_BASE_STATS).max(0.0);
    for (id, base) in STAKE_FIRE {
        if let Some(row) = params.get_mut::<AtkParam_Pc>(id) {
            row.set_atk_fire((base * factor) as u16);
        }
    }
    log(&format!("Stake fire x{factor:.2} (Str {strength}, Dex {dexterity})"));
}

fn claw_hit(player: &ChrIns, target: &mut ChrIns) {
    match spawn_claw_hit(player, target) {
        Ok(()) => log("  claw hit bullet spawned"),
        Err(e) => {
            log(&format!("  claw hit bullet NOT spawned (error {e}); mark only"));
            target.apply_speffect(SPEFFECT_CLAW_MARK, true);
        }
    }
}

/// Horizontal facing (x, z) from the XYZW orientation: model -Z rotated (measured in game: +Z points behind).
fn facing(q: &eldenring::rotation::Quaternion) -> (f32, f32) {
    (-2.0 * (q.0 * q.2 + q.3 * q.1), 2.0 * (q.0 * q.0 + q.1 * q.1) - 1.0)
}

/// Nightreign's engine finds what the claw hooks; here: the locked-on enemy, else the nearest hostile the aim line really
/// passes close to, with nothing solid in between (a wide cone stole shots aimed at terrain, user).
fn pick_target(candidates: &[*mut ChrIns], player: &ChrIns, ins: &PlayerIns) -> Option<(*mut ChrIns, f32)> {
    let aim = aim_direction(ins);
    let p = position(player);
    let q = &player.modules.physics.orientation;
    let (fx, fz) = facing(q);
    let lock = player.is_locked_on.then_some(player.lock_on_target_position);
    let mut best: Option<(*mut ChrIns, f32, f32)> = None; // (chr, distance, score)
    for &ptr in candidates {
        let chr = unsafe { &*ptr };
        if std::ptr::eq(ptr, player) || FRIENDLY_TEAMS.contains(&chr.team_type) || chr.modules.data.hp <= 0 {
            continue;
        }
        let c = position(chr);
        let d = [c.0 - p.0, c.1 - p.1, c.2 - p.2];
        let dist = (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt();
        let radius = chr.modules.physics.hit_radius;
        if dist - radius > CLAW_RANGE {
            continue;
        }
        let score = if let Some(l) = &lock {
            // Only the locked-on character: its lock-on point (often high up, e.g. a rider) is above its body.
            let e = (c.0 - l.0).hypot(c.2 - l.2);
            if e > radius + LOCK_ON_SLACK {
                continue;
            }
            e
        } else {
            let a = aim.unwrap_or([fx, 0.0, fz]);
            let chest = [d[0], d[1] + chr.modules.physics.hit_height * 0.5 - CLAW_ORIGIN_HEIGHT, d[2]];
            let along = chest[0] * a[0] + chest[1] * a[1] + chest[2] * a[2];
            let square = chest[0] * chest[0] + chest[1] * chest[1] + chest[2] * chest[2];
            let off_line = (square - along * along).max(0.0).sqrt();
            if along <= 0.0 || off_line > radius + AIM_SLACK || !clear_line(ins, chest, along) {
                continue;
            }
            dist
        };
        if best.is_none_or(|b| score < b.2) {
            best = Some((ptr, dist, score));
        }
    }
    best.map(|(c, d, _)| (c, d))
}

/// Diagnostics for a miss: the 6 nearest characters as pick_target sees them.
fn log_nearest(candidates: &[*mut ChrIns], player: &ChrIns) {
    let p = position(player);
    let q = &player.modules.physics.orientation;
    let (fx, fz) = facing(q);
    log(&format!("  player pos {:.1} {:.1} {:.1} facing {fx:.2} {fz:.2} lock {:?}", p.0, p.1, p.2,
                 player.lock_on_target_position));
    let mut rows: Vec<(f32, String)> = candidates.iter().filter(|&&c| !std::ptr::eq(c, player)).map(|&c| {
        let chr = unsafe { &*c };
        let e = position(chr);
        let d = [e.0 - p.0, e.1 - p.1, e.2 - p.2];
        let dist = (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt();
        let flat = (d[0] * d[0] + d[2] * d[2]).sqrt().max(0.01);
        (dist, format!("  chr dist {dist:.1} cos {:.2} team {} hp {}/{} radius {:.2} ride {:?}", (d[0] * fx + d[2] * fz) / flat,
                       chr.team_type, chr.modules.data.hp, chr.modules.data.max_hp, chr.modules.physics.hit_radius,
                       ride_info(chr)))
    }).collect();
    rows.sort_by(|a, b| a.0.total_cmp(&b.0));
    for (_, line) in rows.iter().take(6) {
        log(line);
    }
}

enum Claw {
    Idle,
    /// Released: waiting for the claw's mark on a target.
    Watching { since: Instant },
    /// Hooked terrain: drag the player to `goal`.
    Terrain { goal: HavokPosition, since: Instant },
    /// Hooked: pull the target in (small) or drag the player to it (large).
    Moving { target: usize, pull: bool, since: Instant },
}

struct State {
    claw: Claw,
    stats: (u32, u32),
    aiming: bool,
    gauge: Gauge,
    stake_air: StakeAir,
    dead: bool,
    sixth_used: bool,
    invincible_until: Option<Instant>,
    stake: Stake,
    last_frame: Instant,
    fall: Fall,
    runes_file: Option<std::path::PathBuf>,
    claws: ClawCharges,
}

fn frame(state: &mut State) {
    let now = Instant::now();
    let dt = now.duration_since(state.last_frame).as_secs_f32().min(0.1);
    state.last_frame = now;
    let skill = SKILL.swap(false, Ordering::Relaxed);
    let ultimate = ULTIMATE.swap(false, Ordering::Relaxed);
    let released = SKILL_RELEASED.swap(false, Ordering::Relaxed);
    let Ok(world_chr_man) = (unsafe { WorldChrMan::instance_mut() }) else {
        hud::hide();
        return;
    };
    let Some(ref mut player) = world_chr_man.main_player else {
        hud::hide();
        return;
    };
    let player_ptr: *mut ChrIns = &mut player.chr_ins;
    let player_ins: *mut PlayerIns = &mut **player;
    #[cfg(feature = "rig")]
    if rig::recording() {
        let mut others = Vec::new();
        for chr_set in world_chr_man.chr_sets.iter().flatten() {
            for chr in chr_set.characters() {
                let ptr: *mut ChrIns = chr;
                if !std::ptr::eq(ptr, player_ptr) {
                    others.push(ptr);
                }
            }
        }
        rig::record(unsafe { &*player_ptr }, &others);
    }
    stake_fire_frame(&mut state.stake, unsafe { &*player_ptr });
    stake_air(&mut state.stake_air, unsafe { &mut *player_ins });
    let places = {
        let p = unsafe { &*player_ins };
        Places { at: p.block_position, block: p.current_block_id, safe: p.safe_block_pos, safe_block: p.safe_block_id }
    };
    if sixth_sense(&mut state.sixth_used, &mut state.dead, &mut state.invincible_until, &mut state.fall, places, unsafe { &mut *player_ptr }) && state.gauge.value < 1.0 {
        state.gauge.value = 1.0;
        log("Stake: gauge refilled");
    }
    let handle = player.chr_ins.field_ins_handle;
    let at = position(&player.chr_ins);
    let stake_playing = STAKE_ANIMS.contains(&current_anim(&player.chr_ins).0);
    for chr_set in world_chr_man.chr_sets.iter().flatten() {
        for chr in chr_set.characters() {
            let ptr: *mut ChrIns = chr;
            if std::ptr::eq(ptr, player_ptr) {
                continue;
            }
            let chr = unsafe { &*ptr };
            let hp = chr.modules.data.hp;
            let before = state.gauge.hp.insert(ptr as usize, hp).unwrap_or(hp);
            if hp >= before {
                continue;
            }
            if stake_playing {
                log(&format!("Stake hit: {} hp, Str {} Dex {}", before - hp, state.stats.0, state.stats.1));
                continue;
            }
            // last_hit_by only named him on kills [User, Run]; a hostile losing HP close to him counts as his hit too.
            let e = position(chr);
            let dist = ((e.0 - at.0).powi(2) + (e.1 - at.1).powi(2) + (e.2 - at.2).powi(2)).sqrt();
            let his = chr.last_hit_by == handle;
            if his || (!FRIENDLY_TEAMS.contains(&chr.team_type) && dist <= GAUGE_NEAR) {
                log(&format!("Gauge hit: {} hp, {dist:.1} m, last_hit_by him {his}", before - hp));
                state.gauge.hit(before - hp);
            }
        }
    }
    if has_speffect(&player.chr_ins, SPEFFECT_NIGHTFARER).is_some() {
        let claw_left = has_speffect(&player.chr_ins, SPEFFECT_SKILL_COOLDOWN).filter(|_| state.claws.ready < state.claws.max);
        let refill = claw_left.map_or(1.0, |t| (1.0 - t / CLAW_COOLDOWN).clamp(0.0, 1.0));
        hud::show(state.gauge.value, refill, state.claws.ready, state.claws.max, !state.sixth_used);
    } else {
        hud::hide();
    }
    // Test aid: native/give_runes.txt holds an amount, given once and then deleted.
    if let Some(file) = state.runes_file.take() {
        if let Some(amount) = std::fs::read_to_string(&file).ok().and_then(|t| t.trim().parse::<u32>().ok()) {
            unsafe { player.player_game_data.as_mut() }.rune_count = amount;
            let _ = std::fs::remove_file(&file);
            log(&format!("Gave {amount} runes"));
        }
    }
    let stats = unsafe { player.player_game_data.as_ref() };
    let stats = (stats.strength, stats.dexterity);
    if stats != state.stats {
        state.stats = stats;
        scale_stake_fire(stats.0, stats.1);
    }
    let cooling = has_speffect(&player.chr_ins, SPEFFECT_SKILL_COOLDOWN).is_some();
    // NR's 8 s run from the press, not from the shot: its closest shots are 7.9 s apart, and aiming doesn't add to the wait.
    if state.claws.frame(player, cooling, skill) {
        state.aiming = true;
        player.apply_speffect(SPEFFECT_SKILL, true);
        log("skill (Y + LT)");
    }
    state.claws.confirm(player, released);
    if SKILL_HELD.load(Ordering::Relaxed) && state.aiming {
        player.apply_speffect(SPEFFECT_SKILL_HELD, true);
    }
    if CROUCH.swap(false, Ordering::Relaxed) {
        player.apply_speffect(SPEFFECT_CROUCH, true);
        log("crouch (Y + L3)");
    }
    if ULTIMATE_HELD.load(Ordering::Relaxed) {
        player.apply_speffect(SPEFFECT_ULTIMATE_HELD, true);
    }
    if ultimate && state.gauge.value >= 1.0 {
        player.apply_speffect(SPEFFECT_ULTIMATE, true);
        log("ultimate (Y + RT)");
    }
    // The gauge is spent when the Stake really plays, so a press the script refused costs nothing.
    if STAKE_START_ANIMS.contains(&current_anim(&player.chr_ins).0) && state.gauge.value >= 1.0 {
        state.gauge.value = 0.0;
        log("Stake: gauge spent");
    }
    if released && state.aiming && matches!(state.claw, Claw::Idle) {
        state.aiming = false;
        state.claw = Claw::Watching { since: now };
        state_seen().clear();
        log("Claw Shot released");
    }
    match state.claw {
        Claw::Idle => {}
        Claw::Watching { since } => {
            log_new_anims_and_bullets(state_seen(), &player.chr_ins);
            if now.duration_since(since) > HOOK_WINDOW {
                state.claw = Claw::Idle;
                log("Claw Shot: no hook");
                return;
            }
            // The claw flies when the fire animation reaches its attack frame.
            let firing = player.chr_ins.modules.time_act.anim_queue.iter()
                .any(|a| FIRE_ANIMS.contains(&a.anim_id) && a.play_time >= FIRE_TIME);
            if !firing {
                return;
            }
            let mut candidates = Vec::new();
            for chr_set in world_chr_man.chr_sets.iter().flatten() {
                for chr in chr_set.characters() {
                    let ptr: *mut ChrIns = chr;
                    candidates.push(ptr);
                }
            }
            let player = unsafe { &mut *player_ptr };
            let Some((target, dist)) = pick_target(&candidates, player, unsafe { &*player_ins }) else {
                // No enemy: terrain along the camera's aim drags Wylder to it (NR hit types 11 and 1).
                if let Some(goal) = terrain_hook(unsafe { &*player_ins }) {
                    face_toward(player, [goal.0, goal.1, goal.2]);
                    let p = position(player);
                    let dist = ((goal.0 - p.0).powi(2) + (goal.1 - p.1).powi(2) + (goal.2 - p.2).powi(2)).sqrt();
                    player.apply_speffect(SPEFFECT_HOOK_MOVE, true);
                    log(&format!("Claw Shot hooked terrain at {dist:.1} m"));
                    state.claw = Claw::Terrain { goal, since: now };
                    return;
                }
                state.claw = Claw::Idle;
                log(&format!("Claw Shot: missed (no enemy or terrain; {} characters, locked on {})",
                             candidates.len(), player.is_locked_on));
                log_nearest(&candidates, player);
                return;
            };
            let target_chr = unsafe { &mut *target };
            let radius = target_chr.modules.physics.hit_radius;
            let (drag, why) = claw_drags(target_chr);
            let pull = !drag;
            let e = drag_goal(target_chr);
            if !pull {
                face_toward(player, [e.0, e.1, e.2]);
            }
            claw_hit(player, target_chr);
            player.apply_speffect(if pull { SPEFFECT_HOOK_PULL } else { SPEFFECT_HOOK_MOVE }, true);
            log(&format!("Claw Shot hooked a target at {dist:.1} m (npc {}, radius {radius:.2}, team {}, ride {:?}): {} ({why})",
                         target_chr.npc_param_id, target_chr.team_type, ride_info(target_chr), if pull { "pull" } else { "move" }));
            state.claw = Claw::Moving { target: target as usize, pull, since: now };
        }
        Claw::Terrain { goal, since } => {
            let player = unsafe { &mut *player_ptr };
            if path_blocked(unsafe { &*player_ins }, goal, DRAG_SPEED * dt) {
                state.claw = Claw::Idle;
                log("Claw Shot: terrain drag stopped before a surface");
                return;
            }
            let dist = step_toward(player, goal, DRAG_SPEED * dt, TERRAIN_STOP);
            keep_above_floor(unsafe { &mut *player_ins });
            if dist <= TERRAIN_STOP || now.duration_since(since) > DRAG_TIME {
                state.claw = Claw::Idle;
                log(&format!("Claw Shot: terrain drag done at {dist:.1} m"));
            }
        }
        Claw::Moving { target, pull, since } => {
            let (player, target) = unsafe { (&mut *player_ptr, &mut *(target as *mut ChrIns)) };
            let dist = if pull {
                step_toward(target, position(player), PULL_SPEED * dt, STOP_DISTANCE)
            } else {
                step_toward(player, drag_goal(target), DRAG_SPEED * dt, STOP_DISTANCE)
            };
            if dist <= STOP_DISTANCE || now.duration_since(since) > if pull { MOVE_TIME } else { DRAG_TIME } {
                state.claw = Claw::Idle;
                log(&format!("Claw Shot: {} done at {dist:.1} m", if pull { "pull" } else { "move" }));
            }
        }
    }
}

/// # Safety
/// Called by the loader. Do not call this yourself.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn DllMain(hmodule: *const c_void, reason: u32) -> bool {
    if reason != 1 {
        return true;
    }
    let mut path = [0u8; 520];
    let n = unsafe { GetModuleFileNameA(hmodule, path.as_mut_ptr(), path.len() as u32) } as usize;
    let log_path = std::path::Path::new(std::str::from_utf8(&path[..n]).unwrap_or("")).with_extension("log");
    if let Ok(file) = std::fs::File::create(log_path) {
        *LOG.lock().unwrap() = Some(file);
    }
    log("nightfarers_native loaded");
    let dll = std::path::PathBuf::from(std::str::from_utf8(&path[..n]).unwrap_or(""));
    load_claw_targets(&dll.with_file_name("claw_targets.txt"));

    let module = hmodule as usize;
    std::thread::spawn(move || {
        // Wait for the game's task system (not from DllMain's thread: singletons resolve after boot).
        let cs_task = CSTaskImp::wait_for_instance(Duration::MAX).unwrap();
        match unsafe { patch_xinput_import() } {
            Ok(n) => log(&format!("XInputGetState import patched ({n} slot)")),
            Err(e) => log(&format!("XInputGetState import NOT patched: {e}")),
        }
        #[cfg(feature = "rig")]
        pad_script::start(dll.parent().map(|d| d.to_path_buf()).unwrap_or_default());
        let overlay = hud::Hud { icons_dir: dll.parent().map(|d| d.join("icons")).unwrap_or_default(), sprites: [None; 4] };
        let module = hudhook::windows::Win32::Foundation::HINSTANCE(module as *mut _);
        if let Err(e) = hudhook::Hudhook::builder().with::<hudhook::hooks::dx12::ImguiDx12Hooks>(overlay).with_hmodule(module).build().apply() {
            log(&format!("HUD: overlay not hooked: {e:?}"));
        }
        let state = Mutex::new(State { claw: Claw::Idle, stats: (0, 0), aiming: false, gauge: Gauge { value: 1.0, mean_hit: 0.0, hp: HashMap::new() }, stake_air: StakeAir::default(), dead: false, sixth_used: false, invincible_until: None, stake: Stake::default(), last_frame: Instant::now(), fall: Fall::default(), runes_file: dll.parent().map(|d| d.join("give_runes.txt")), claws: {
            let max = if dll.parent().is_some_and(|d| d.join(TWO_CLAWS_FILE).exists()) { 2 } else { 1 };
            log(&format!("Claw Shot charges: {max}"));
            ClawCharges { max, ready: max, refilling: false, seen: false, unconfirmed: None }
        } });
        cs_task.run_recurring(
            move |_: &FD4TaskData| {
                if let Ok(mut state) = state.lock() {
                    frame(&mut state);
                }
            },
            CSTaskGroupIndex::FrameBegin,
        );
    });
    true
}
