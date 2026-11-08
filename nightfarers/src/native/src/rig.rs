//! Run recorder for the Elden Ring helper, driven by the pad script (pad_script.rs). One JSON object per line: anim id on
//! change, bullet param ids, player SpEffects added and removed, enemy HP changes, and position, stamina and HP at 10 Hz.
//! `src/fidelity.py` compares recordings.
use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Instant;

use eldenring::cs::{CSBulletManager, ChrIns};
use fromsoftware_shared::FromStatic;

use crate::{current_anim, pad_script, position};

static REC: Mutex<Option<Recorder>> = Mutex::new(None);

pub fn start(path: PathBuf) {
    if let Ok(file) = std::fs::File::create(path) {
        *REC.lock().unwrap() = Some(Recorder::new(file));
    }
}

pub fn stop() {
    *REC.lock().unwrap() = None;
}

pub fn recording() -> bool {
    pad_script::ACTIVE.load(std::sync::atomic::Ordering::Relaxed) && REC.lock().unwrap().is_some()
}

struct Recorder {
    file: std::fs::File,
    start: Instant,
    anim: i32,
    last_pos: f32,
    bullets: Vec<i32>,
    speffects: Vec<i32>,
    hp: Vec<(usize, i32)>,
}

impl Recorder {
    fn new(file: std::fs::File) -> Self {
        Recorder { file, start: Instant::now(), anim: 0, last_pos: -1.0, bullets: Vec::new(), speffects: Vec::new(), hp: Vec::new() }
    }

    fn line(&mut self, t: f32, body: String) {
        let _ = writeln!(self.file, "{{\"t\":{t:.3},{body}}}");
    }
}

/// Once a frame from the game's task, when recording.
pub fn record(player: &ChrIns, others: &[*mut ChrIns]) {
    let mut guard = REC.lock().unwrap();
    let Some(r) = guard.as_mut() else { return };
    let t = r.start.elapsed().as_secs_f32();
    let (anim, play) = current_anim(player);
    if anim != r.anim {
        r.anim = anim;
        r.line(t, format!("\"anim\":{anim},\"play\":{play:.3}"));
    }
    if t - r.last_pos >= 0.1 {
        r.last_pos = t;
        let p = position(player);
        let d = &player.modules.data;
        r.line(t, format!("\"pos\":[{:.3},{:.3},{:.3}],\"hp\":{},\"fp\":{},\"sta\":{}", p.0, p.1, p.2, d.hp, d.fp, d.stamina));
    }
    if let Ok(bullets) = unsafe { CSBulletManager::instance() } {
        let mut now = Vec::new();
        for b in bullets.bullets() {
            for s in [&b.wait_state.base.param, &b.fly_state.base.param, &b.exp_state.base.param] {
                if s.param_id > 0 && !now.contains(&s.param_id) {
                    now.push(s.param_id);
                }
            }
        }
        for id in &now {
            if !r.bullets.contains(id) {
                r.line(t, format!("\"bullet\":{id}"));
            }
        }
        r.bullets = now;
    }
    let now: Vec<i32> = player.special_effect.entries().map(|e| e.param_id).collect();
    for id in &now {
        if !r.speffects.contains(id) {
            r.line(t, format!("\"sp\":{id}"));
        }
    }
    for id in r.speffects.clone() {
        if !now.contains(&id) {
            r.line(t, format!("\"sp_end\":{id}"));
        }
    }
    r.speffects = now;
    for &c in others {
        let chr = unsafe { &*c };
        let key = c as usize;
        let hp = chr.modules.data.hp;
        match r.hp.iter().position(|x| x.0 == key) {
            Some(i) => {
                let old = r.hp[i].1;
                if hp != old {
                    r.hp[i].1 = hp;
                    r.line(t, format!("\"enemy\":{},\"team\":{},\"hp\":{hp},\"delta\":{}", key, chr.team_type, hp - old));
                }
            }
            None => r.hp.push((key, hp)),
        }
    }
    let _ = r.file.flush();
}

