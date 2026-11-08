//! Development test rig: scripted pad input and a run recorder. Idle unless the environment has NF_RIG (set only by
//! launch_test.bat), so a played game never runs it.
//!
//! Scripts: write `<dll dir>/rig/run.txt`; the rig renames it to run.active, runs it, writes run.done. One step per line:
//!   press a+rb 100       hold buttons for 100 ms, then release
//!   stick 0 1 2000       left stick x y (-1..1) for 2000 ms     cam 1 0 500    same for the right stick
//!   lt 300 / rt 300      trigger for 300 ms (with `hold` buttons kept down)
//!   hold y / release     keep buttons down across steps
//!   wait 1000            do nothing for 1000 ms
//!   rec <name> / stop    start or stop writing rig/<name>.jsonl
//! Buttons: a b x y lb rb ls rs up down left right start back.
//!
//! Shared by the Elden Ring helper (src/native) and the Nightreign recorder (src/nr_rig). Each provides log, proc_address,
//! patch_import, rec_start, rec_stop and an XInputState.
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicI16, AtomicU8, AtomicU16, AtomicUsize, Ordering};
use std::time::Duration;

pub static ACTIVE: AtomicBool = AtomicBool::new(false);
/// A script is running: only then the rig replaces pad 0. Otherwise the user's own pad passes through.
static RUNNING: AtomicBool = AtomicBool::new(false);
static REAL_PAD: AtomicU8 = AtomicU8::new(2);
pub static ALWAYS_CONNECTED: AtomicBool = AtomicBool::new(false);
static BUTTONS: AtomicU16 = AtomicU16::new(0);
static HELD: AtomicU16 = AtomicU16::new(0);
static TRIGGERS: [AtomicU8; 2] = [const { AtomicU8::new(0) }; 2];
static STICKS: [AtomicI16; 4] = [const { AtomicI16::new(0) }; 4];
static PACKET: AtomicUsize = AtomicUsize::new(1);
static SIGNATURE: AtomicUsize = AtomicUsize::new(0);

fn button(name: &str) -> u16 {
    match name {
        "up" => 0x0001, "down" => 0x0002, "left" => 0x0004, "right" => 0x0008,
        "start" => 0x0010, "back" => 0x0020, "ls" => 0x0040, "rs" => 0x0080,
        "lb" => 0x0100, "rb" => 0x0200, "a" => 0x1000, "b" => 0x2000, "x" => 0x4000, "y" => 0x8000,
        _ => 0,
    }
}

fn buttons(names: &str) -> u16 {
    names.split('+').map(button).fold(0, |a, b| a | b)
}

/// While the rig runs, it is pad 0: (buttons, triggers, sticks). Returns the XInput result to report.
pub fn feed(index: u32, state: *mut crate::XInputState, result: u32) -> u32 {
    if !ACTIVE.load(Ordering::Relaxed) || index != 0 || state.is_null() {
        return result;
    }
    let connected = (result == 0) as u8;
    if REAL_PAD.swap(connected, Ordering::Relaxed) != connected {
        crate::log(&format!("rig: real pad 0 connected = {connected}"));
    }
    if !RUNNING.load(Ordering::Relaxed) {
        if result != 0 && ALWAYS_CONNECTED.load(Ordering::Relaxed) {
            // Nightreign drops the pad device unless XInput answers (src/nr_rig/src/di.rs): the user's pad as read by
            // the launcher, else a connected, neutral pad.
            unsafe { *state = std::mem::zeroed() };
            if let Some((packet, b, lt, rt, sticks)) = crate::real_pad() {
                let s = unsafe { &mut *state };
                s.packet_number = packet;
                s.gamepad.buttons = b;
                s.gamepad.left_trigger = lt;
                s.gamepad.right_trigger = rt;
                s.gamepad.thumb_lx = sticks[0];
                s.gamepad.thumb_ly = sticks[1];
                s.gamepad.thumb_rx = sticks[2];
                s.gamepad.thumb_ry = sticks[3];
            }
            return 0;
        }
        return result;
    }
    let s = unsafe { &mut *state };
    s.gamepad.buttons = BUTTONS.load(Ordering::Relaxed) | HELD.load(Ordering::Relaxed);
    s.gamepad.left_trigger = TRIGGERS[0].load(Ordering::Relaxed);
    s.gamepad.right_trigger = TRIGGERS[1].load(Ordering::Relaxed);
    s.gamepad.thumb_lx = STICKS[0].load(Ordering::Relaxed);
    s.gamepad.thumb_ly = STICKS[1].load(Ordering::Relaxed);
    s.gamepad.thumb_rx = STICKS[2].load(Ordering::Relaxed);
    s.gamepad.thumb_ry = STICKS[3].load(Ordering::Relaxed);
    // Like a real pad, the packet number moves only when the state changes.
    let g = &s.gamepad;
    let sig = (g.buttons as usize) ^ ((g.left_trigger as usize) << 16) ^ ((g.right_trigger as usize) << 24)
        ^ ((g.thumb_lx as u16 as usize) << 32) ^ ((g.thumb_ly as u16 as usize) << 48) ^ (g.thumb_rx as u16 as usize).rotate_left(7) ^ (g.thumb_ry as u16 as usize).rotate_left(23);
    if SIGNATURE.swap(sig, Ordering::Relaxed) != sig {
        PACKET.fetch_add(1, Ordering::Relaxed);
    }
    s.packet_number = PACKET.load(Ordering::Relaxed) as u32;
    0
}

/// The script's pad right now: buttons, triggers, sticks.
#[allow(dead_code)]
pub fn snapshot() -> (u16, u8, u8, [i16; 4]) {
    if !RUNNING.load(Ordering::Relaxed) {
        return crate::real_pad().map_or((0, 0, 0, [0; 4]), |(_, b, lt, rt, s)| (b, lt, rt, s));
    }
    (BUTTONS.load(Ordering::Relaxed) | HELD.load(Ordering::Relaxed), TRIGGERS[0].load(Ordering::Relaxed), TRIGGERS[1].load(Ordering::Relaxed),
     [STICKS[0].load(Ordering::Relaxed), STICKS[1].load(Ordering::Relaxed), STICKS[2].load(Ordering::Relaxed), STICKS[3].load(Ordering::Relaxed)])
}

fn stick(i: usize, x: f32, y: f32) {
    STICKS[i].store((x.clamp(-1.0, 1.0) * 32767.0) as i16, Ordering::Relaxed);
    STICKS[i + 1].store((y.clamp(-1.0, 1.0) * 32767.0) as i16, Ordering::Relaxed);
}

fn run_script(dir: &std::path::Path, text: &str) {
    RUNNING.store(true, Ordering::Relaxed);
    let ms = |s: Option<&str>, d: u64| s.and_then(|v| v.parse().ok()).unwrap_or(d);
    let f = |s: Option<&str>| s.and_then(|v| v.parse::<f32>().ok()).unwrap_or(0.0);
    for line in text.lines() {
        let mut w = line.split_whitespace();
        let Some(cmd) = w.next() else { continue };
        crate::log(&format!("rig: {line}"));
        match cmd {
            "press" => {
                BUTTONS.store(buttons(w.next().unwrap_or("")), Ordering::Relaxed);
                std::thread::sleep(Duration::from_millis(ms(w.next(), 100)));
                BUTTONS.store(0, Ordering::Relaxed);
                std::thread::sleep(Duration::from_millis(60));
            }
            "hold" => HELD.store(buttons(w.next().unwrap_or("")), Ordering::Relaxed),
            "release" => HELD.store(0, Ordering::Relaxed),
            "stick" | "cam" => {
                let i = if cmd == "stick" { 0 } else { 2 };
                stick(i, f(w.next()), f(w.next()));
                std::thread::sleep(Duration::from_millis(ms(w.next(), 500)));
                stick(i, 0.0, 0.0);
            }
            "go" | "look" => stick(if cmd == "go" { 0 } else { 2 }, f(w.next()), f(w.next())),
            "lt" | "rt" => {
                let t = (cmd == "rt") as usize;
                TRIGGERS[t].store(255, Ordering::Relaxed);
                std::thread::sleep(Duration::from_millis(ms(w.next(), 100)));
                TRIGGERS[t].store(0, Ordering::Relaxed);
                std::thread::sleep(Duration::from_millis(60));
            }
            "wait" => std::thread::sleep(Duration::from_millis(ms(w.next(), 100))),
            "rec" => {
                crate::rec_start(dir.join(format!("{}.jsonl", w.next().unwrap_or("run"))));
            }
            "stop" => crate::rec_stop(),
            _ => crate::log(&format!("rig: unknown step {cmd}")),
        }
    }
    HELD.store(0, Ordering::Relaxed);
    BUTTONS.store(0, Ordering::Relaxed);
    RUNNING.store(false, Ordering::Relaxed);
}

/// Starts the script watcher when the rig is enabled. The rig also keeps the game running and reading input with its
/// window in the background, so tests don't take the keyboard or the screen from the user.
pub fn start(dll_dir: PathBuf) {
    let dir = dll_dir.join("rig");
    if std::env::var_os("NF_RIG").is_none() {
        return;
    }
    let _ = std::fs::create_dir_all(&dir);
    ACTIVE.store(true, Ordering::Relaxed);
    crate::log("rig enabled");
    std::thread::spawn(move || {
        unsafe { keep_focus() };
        loop {
            std::thread::sleep(Duration::from_millis(200));
            let (run, active) = (dir.join("run.txt"), dir.join("run.active"));
            if std::fs::rename(&run, &active).is_ok() {
                let text = std::fs::read_to_string(&active).unwrap_or_default();
                run_script(&dir, &text);
                let _ = std::fs::rename(&active, dir.join("run.done"));
            }
        }
    });
}

// Background running: same import trick as the XInput hook.
#[link(name = "user32")]
unsafe extern "system" {
    fn EnumWindows(cb: unsafe extern "system" fn(usize, isize) -> i32, param: isize) -> i32;
    fn GetWindowThreadProcessId(hwnd: usize, pid: *mut u32) -> u32;
    fn IsWindowVisible(hwnd: usize) -> i32;
    fn SetWindowLongPtrW(hwnd: usize, index: i32, value: isize) -> isize;
    fn SetWindowPos(hwnd: usize, after: usize, x: i32, y: i32, cx: i32, cy: i32, flags: u32) -> i32;
    fn GetWindowRect(hwnd: usize, rect: *mut i32) -> i32;
    fn GetSystemMetrics(index: i32) -> i32;
    fn CallWindowProcW(prev: isize, hwnd: usize, msg: u32, w: usize, l: isize) -> isize;
}
unsafe extern "system" {
    fn GetCurrentProcessId() -> u32;
}

static HWND: AtomicUsize = AtomicUsize::new(0);
static WNDPROC: AtomicUsize = AtomicUsize::new(0);

unsafe extern "system" fn find_window(hwnd: usize, _: isize) -> i32 {
    let mut pid = 0;
    unsafe { GetWindowThreadProcessId(hwnd, &mut pid) };
    if pid == unsafe { GetCurrentProcessId() } && unsafe { IsWindowVisible(hwnd) } != 0 {
        HWND.store(hwnd, Ordering::Relaxed);
        return 0;
    }
    1
}

// The game thinks it has focus, so it would keep holding the mouse while the user works elsewhere (user's rule: never
// lock the mouse). These pass through only when its window really is in front; otherwise the mouse stays the user's.
static CLIP_REAL: AtomicUsize = AtomicUsize::new(0);
static SETPOS_REAL: AtomicUsize = AtomicUsize::new(0);
static FOREGROUND_REAL: AtomicUsize = AtomicUsize::new(0);

fn really_in_front() -> bool {
    let f: unsafe extern "system" fn() -> usize = unsafe { std::mem::transmute(FOREGROUND_REAL.load(Ordering::Relaxed)) };
    unsafe { f() == HWND.load(Ordering::Relaxed) }
}

unsafe extern "system" fn clip_cursor(rect: *const i32) -> i32 {
    let f: unsafe extern "system" fn(*const i32) -> i32 = unsafe { std::mem::transmute(CLIP_REAL.load(Ordering::Relaxed)) };
    unsafe { f(if really_in_front() { rect } else { std::ptr::null() }) }
}

unsafe extern "system" fn set_cursor_pos(x: i32, y: i32) -> i32 {
    if !really_in_front() {
        return 1;
    }
    let f: unsafe extern "system" fn(i32, i32) -> i32 = unsafe { std::mem::transmute(SETPOS_REAL.load(Ordering::Relaxed)) };
    unsafe { f(x, y) }
}

unsafe extern "system" fn own_window() -> usize {
    HWND.load(Ordering::Relaxed)
}

unsafe extern "system" fn wndproc(hwnd: usize, msg: u32, w: usize, l: isize) -> isize {
    const WM_ACTIVATE: u32 = 0x0006;
    const WM_KILLFOCUS: u32 = 0x0008;
    const WM_ACTIVATEAPP: u32 = 0x001c;
    if msg == WM_KILLFOCUS || ((msg == WM_ACTIVATEAPP || msg == WM_ACTIVATE) && w & 0xffff == 0) {
        return 0;
    }
    unsafe { CallWindowProcW(WNDPROC.load(Ordering::Relaxed) as isize, hwnd, msg, w, l) }
}

/// The game believes its window stays in front: focus queries answer with its own window and losing focus is ignored.
unsafe fn keep_focus() {
    for _ in 0..600 {
        unsafe { EnumWindows(find_window, 0) };
        if HWND.load(Ordering::Relaxed) != 0 {
            break;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    let hwnd = HWND.load(Ordering::Relaxed);
    if hwnd == 0 {
        crate::log("rig: no game window");
        return;
    }
    // Primary screen (user's rule): its top-left corner is 0,0. The game fits its window to a monitor well after the
    // window appears (a single early move didn't hold in Nightreign), so keep checking through startup.
    std::thread::spawn(move || {
        for _ in 0..240 {
            let mut r = [0i32; 4];
            if unsafe { GetWindowRect(hwnd, r.as_mut_ptr()) } != 0 && (r[0] != 0 || r[1] != 0) {
                let (w, h) = unsafe { (GetSystemMetrics(0), GetSystemMetrics(1)) };
                // SWP_NOZORDER | SWP_NOACTIVATE
                unsafe { SetWindowPos(hwnd, 0, 0, 0, w, h, 0x0004 | 0x0010) };
                crate::log(&format!("rig: window moved from {},{} to the primary screen", r[0], r[1]));
            }
            std::thread::sleep(Duration::from_millis(500));
        }
    });
    let (clip, setpos) = unsafe { (crate::proc_address(c"user32.dll", c"ClipCursor"), crate::proc_address(c"user32.dll", c"SetCursorPos")) };
    FOREGROUND_REAL.store(unsafe { crate::proc_address(c"user32.dll", c"GetForegroundWindow") }, Ordering::Relaxed);
    CLIP_REAL.store(clip, Ordering::Relaxed);
    SETPOS_REAL.store(setpos, Ordering::Relaxed);
    let guard = unsafe { crate::patch_import(clip, clip_cursor as *const () as usize) + crate::patch_import(setpos, set_cursor_pos as *const () as usize) };
    crate::log(&format!("rig: mouse guard ({guard} import slots)"));
    // A clip set before the user left the window would otherwise stay.
    std::thread::spawn(|| {
        loop {
            if !really_in_front() {
                let f: unsafe extern "system" fn(*const i32) -> i32 = unsafe { std::mem::transmute(CLIP_REAL.load(Ordering::Relaxed)) };
                unsafe { f(std::ptr::null()) };
            }
            std::thread::sleep(Duration::from_millis(200));
        }
    });
    let mut n = 0;
    for name in [c"GetForegroundWindow", c"GetActiveWindow", c"GetFocus"] {
        let target = unsafe { crate::proc_address(c"user32.dll", name) };
        n += unsafe { crate::patch_import(target, own_window as *const () as usize) };
    }
    const GWLP_WNDPROC: i32 = -4;
    let old = unsafe { SetWindowLongPtrW(hwnd, GWLP_WNDPROC, wndproc as *const () as isize) };
    WNDPROC.store(old as usize, Ordering::Relaxed);
    crate::log(&format!("rig: focus kept ({n} import slots, window {hwnd:#x})"));
}
