//! His HUD, drawn over the game by hudhook, where Nightreign's own HUD has it: NR's menu/01_000_fe.gfx, PlayerHUD/Ult and PlayerHUD/Skill,
//! on its 1920 x 1080 stage. Elden Ring's HUD has no such elements. Nothing here takes input. Sprites: native/icons (src/build_hud_icons.py).

use std::f32::consts::TAU;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};

use hudhook::imgui::{Context, DrawListMut, TextureId, Ui};
use hudhook::{ImguiRenderLoop, RenderContext};

use crate::log;

/// (centre x, centre y, size), from Frame in PlayerHUD/Ult and /Skill: 240 px frame x 0.47, and x 0.8 for the skill.
const ULT: [f32; 3] = [960.0, 996.7, 113.0];
const SKILL: [f32; 3] = [835.0, 997.6, 90.0];
/// Sixth Sense has no such place in NR, which shows it among its buffs: left of the skill, my choice.
const SIXTH: [f32; 3] = [746.0, 1008.0, 56.0];
const SPRITES: [&str; 4] = ["MENU_MenuIcon_41200", "MENU_MenuIcon_41150", "MENU_MenuIcon_41850", "MENU_Cmn_Circle_01"];
const DARK: [f32; 4] = [0.0, 0.0, 0.0, 0.65];
const GOLD: [f32; 4] = [1.0, 0.82, 0.45, 1.0];

static SHOWN: AtomicBool = AtomicBool::new(false);
static GAUGE: AtomicU32 = AtomicU32::new(0);
static CLAW: AtomicU32 = AtomicU32::new(0);
static SIXTH_READY: AtomicBool = AtomicBool::new(false);

pub fn hide() {
    SHOWN.store(false, Ordering::Relaxed);
}

/// `gauge` and `claw` from 0 to 1, 1 = ready.
pub fn show(gauge: f32, claw: f32, sixth_ready: bool) {
    GAUGE.store(gauge.to_bits(), Ordering::Relaxed);
    CLAW.store(claw.to_bits(), Ordering::Relaxed);
    SIXTH_READY.store(sixth_ready, Ordering::Relaxed);
    SHOWN.store(true, Ordering::Relaxed);
}

pub struct Hud {
    pub icons_dir: PathBuf,
    pub sprites: [Option<TextureId>; 4],
}

fn load(render: &mut dyn RenderContext, path: &PathBuf) -> Option<TextureId> {
    let data = std::fs::read(path).map_err(|e| log(&format!("HUD: {path:?}: {e}"))).ok()?;
    let width = u32::from_le_bytes(data.get(0..4)?.try_into().ok()?);
    let height = u32::from_le_bytes(data.get(4..8)?.try_into().ok()?);
    render.load_texture(&data[8..], width, height).map_err(|e| log(&format!("HUD: {path:?}: {e:?}"))).ok()
}

/// Darken the part of a round icon not yet recharged and draw the charged arc, clockwise from the top.
fn charge(list: &DrawListMut, c: [f32; 2], r: f32, s: f32, value: f32) {
    let at = |t: f32, r: f32| {
        let a = t * TAU;
        [c[0] + a.sin() * r, c[1] - a.cos() * r]
    };
    const STEPS: i32 = 64;
    let from = (value * STEPS as f32) as i32;
    for i in from..STEPS {
        let (a, b) = (i as f32 / STEPS as f32, (i + 1) as f32 / STEPS as f32);
        list.add_triangle(c, at(a, r * 0.92), at(b, r * 0.92), DARK).filled(true).build();
    }
    let arc: Vec<[f32; 2]> = (0..=from).map(|i| at(i as f32 / STEPS as f32, r * 0.96)).collect();
    if arc.len() > 1 {
        list.add_polyline(arc, GOLD).thickness(3.0 * s).build();
    }
}

impl ImguiRenderLoop for Hud {
    fn initialize<'a>(&'a mut self, _ctx: &mut Context, render: &'a mut dyn RenderContext) {
        for (slot, name) in self.sprites.iter_mut().zip(SPRITES) {
            *slot = load(render, &self.icons_dir.join(format!("{name}.rgba")));
        }
        log(&format!("HUD: drawing, sprites loaded {}/{}", self.sprites.iter().flatten().count(), SPRITES.len()));
    }

    fn render(&mut self, ui: &mut Ui) {
        if !SHOWN.load(Ordering::Relaxed) {
            return;
        }
        let [w, h] = ui.io().display_size;
        let s = h / 1080.0;
        let left = (w - 1920.0 * s) / 2.0;
        let place = |e: [f32; 3]| ([left + e[0] * s, e[1] * s], e[2] * s / 2.0);
        let list = ui.get_background_draw_list();
        let image = |sprite: usize, c: [f32; 2], r: f32| {
            if let Some(id) = self.sprites[sprite] {
                list.add_image(id, [c[0] - r, c[1] - r], [c[0] + r, c[1] + r]).build();
            }
        };
        let values = [f32::from_bits(GAUGE.load(Ordering::Relaxed)), f32::from_bits(CLAW.load(Ordering::Relaxed))];
        for (sprite, (element, value)) in [ULT, SKILL].into_iter().zip(values).enumerate() {
            let (c, r) = place(element);
            image(sprite, c, r);
            charge(&list, c, r, s, value);
            image(3, c, r);
        }
        if SIXTH_READY.load(Ordering::Relaxed) {
            let (c, r) = place(SIXTH);
            image(2, c, r);
        }
    }
}
