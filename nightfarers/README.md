# Nightfarers

Play Elden Ring Nightreign's heroes in Elden Ring. Version 0.1 has Wylder: a 13th starting class with his skill
(Claw Shot), ultimate (Onslaught Stake), passive (Sixth Sense), Nightreign's movement and his HUD icons.

Only Elden Ring runs. It's single-player and offline only, loaded through [me3](https://github.com/garyttierney/me3).
Players: download the mod from Nexus Mods and follow [dist/README.md](dist/README.md). This repository is the source code.

## What's here

| Path | What it is |
|---|---|
| `src/native/` | `nightfarers_native.dll`, the only program code that runs in the game (Rust). |
| `src/*.py`, `src/*.sh`, `src/flvertool/` | Offline converters that turn Nightreign data into Elden Ring data. They run on the modder's PC, never in the game. |
| `heroes/wylder.toml` | Wylder's data that the converters read. |
| `dist/` | The launcher and player README that ship in the Nexus zip. |
| `.github/workflows/build.yml` | Builds the DLL on GitHub from this code and publishes it with its SHA-256. |

No game files are in this repository. The converters need your own copies of both games; see [BUILDING.md](BUILDING.md).

## What the DLL does

me3 loads it into Elden Ring at startup. It:

- **Reads the controller** by redirecting Elden Ring's own import of `XInputGetState`. When Y is held with a trigger
  (Nightreign's skill and ultimate buttons), it hides those buttons from the game and tells the player script instead.
  It doesn't send any input of its own.
- **Draws the skill and ultimate icons** with [hudhook](https://github.com/veeenu/hudhook), a Dear ImGui overlay on
  the game's DirectX 12 output. It takes no input.
- **Reads and changes game state** through [fromsoftware-rs](https://github.com/vswarte/fromsoftware-rs): what the claw
  hits (ray casts and the nearest enemy), pulls, the ultimate's gauge and damage, Sixth Sense, and the "unstuck" warp.
- **Files:** it reads `claw_targets.txt` and `icons/` next to itself, and writes `nightfarers_native.log` there. It
  also reads `give_runes.txt` if present (a test aid that gives runes once, then deletes the file).

It has no network code, starts no processes, doesn't touch the registry, and never goes near Easy Anti-Cheat: me3
starts the game with EAC off, and the launcher always starts offline with a separate save (`NF0000.sl2`).

`src/native/src/rig.rs` and `pad_script.rs` are a test rig for development (scripted pad input and run recording).
They're behind the `rig` cargo feature, which is off by default and never in released builds. The tools used to
measure Nightreign itself during development (referred to as `src/nr_rig` in a comment) aren't part of the mod and
aren't included.

## Building the DLL

```
cd src/native
cargo build --release
```

Output: `src/native/target/release/nightfarers_native.dll`. Details, and how to build the game data, are in
[BUILDING.md](BUILDING.md).

## Licence

MIT for the code here ([LICENSE](LICENSE)). The DLL also contains third-party libraries; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). fromsoftware-rs's licence forbids using it for AI training.

Elden Ring and Elden Ring Nightreign belong to FromSoftware / Bandai Namco. This is a fan project, not affiliated with them.
Made with AI assistance (Claude) for the code and converters.
