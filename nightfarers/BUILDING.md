# Building Nightfarers

There are two parts:

1. **The DLL** (`nightfarers_native.dll`): built from this repository alone, with one command.
2. **The game data** (`package/`, including `regulation.bin`): converted from your own copies of Elden Ring and
   Elden Ring Nightreign. That data can't be shared as source, so this part needs both games installed.

## 1. The DLL

### Needs

- Windows 10 or 11, x64.
- [Rust](https://rustup.rs/) with the MSVC toolchain (`x86_64-pc-windows-msvc`), version 1.85 or newer (the crate uses
  edition 2024). Tested with rustc 1.99.1.
- [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with "Desktop development with
  C++" (Dear ImGui's C++ code is compiled by hudhook's dependencies).
- Git, and internet access on the first build: Cargo downloads fromsoftware-rs and hudhook from GitHub at the commits
  pinned in `src/native/Cargo.toml`, and the other crates at the versions in `Cargo.lock`.

### Build

```
git clone https://github.com/Verycooltrust/nightfarers
cd nightfarers/nightfarers/src/native
cargo build --release --locked
```

The DLL is `src/native/target/release/nightfarers_native.dll`. Put it in the mod's `native/` folder.

Development builds with the test rig: `cargo build --release --features rig`. Released DLLs never include it.

### Checking a released DLL

Every release on GitHub is built by `.github/workflows/build.yml` on GitHub's own Windows runner, from the tagged commit,
and published with `nightfarers_native.dll.sha256`. The DLL in the Nexus Mods download is that same file. Compare:

```
certutil -hashfile nightfarers_native.dll SHA256
```

Builds on other PCs won't be byte-identical, because Rust and MSVC embed build paths and timestamps, so compare the
hash against the GitHub release rather than against your own build.

## 2. The game data

These are the converters the author runs. They're a working pipeline, not a polished installer, so expect to read the
scripts. Each script's header lists the files it needs.

### Needs

- Both games installed on Steam (Elden Ring App Ver. 1.17.2 / exe 2.7.2.0 and Nightreign exe 1.3.3.0 were used).
- Python 3.12 with Pillow (`pip install pillow`; scripts run as `python -I`), Git Bash, and the .NET 10 SDK.
- These tools, unpacked into `tools/` (not included here, each under its own licence):
  - [Nuxe](https://github.com/JKAnderson/Nuxe) 1.2.1: unpacks both games' archives into `work/er-game` and `work/nr-game`.
  - [WitchyBND](https://github.com/ividyon/WitchyBND) 3.0.1.0: params, texts, binders, animations and effects to XML and back.
  - [Smithbox](https://github.com/vawser/Smithbox) 2.2.6: its `Andre.SoulsFormats.dll` and paramdefs (used by `src/flvertool`).
  - [HKLib](https://github.com/The12thAvenger/HKLib) 0.1.2 (Elden Ring) and 0.1.3 (Nightreign): behaviour graphs to XML.
  - [DSLuaDecompiler](https://github.com/vawser/DSLuaDecompiler): the player scripts (`c0000.hks`).
  - [texconv](https://github.com/microsoft/DirectXTex): textures for the HUD icons.
- The scripts set `PY=` near the top to a Python 3.12 path (a `work/venv` or uv's); point it at yours.
- Build `src/flvertool` with `dotnet build -c Release -o work/bin/flvertool` (it binds and packs FromSoftware formats).

### Inputs

Unpack with Nuxe, then WitchyBND, into `work/` as each script's header says. In short:

| Folder | From |
|---|---|
| `work/s1/{er,nr}/regulation-bin/` | both games' `regulation.bin` (WitchyBND XML) |
| `work/s1/er/msg`, `work/s2/er-msg` | Elden Ring's `item_dlc02` / `menu_dlc02` text binders |
| `work/s2/nr-art`, `work/s5/nrmenu` | Nightreign's class portrait and menu atlases |
| `work/s3/hks`, `work/s3/beh`, `work/s3/anim`, `work/s4/anim` | both games' `c0000` script, behaviour graph and animation binders |
| `work/s4/sfx` | both games' `sfxbnd_commoneffects.ffxbnd.dcx` |

### Build

```
bash src/build_wylder_data.sh && bash src/build_movement.sh && bash src/build_sfx.sh
```

This writes `package/` (regulation, texts, menu art, player script, behaviour graph, animations, effects, sounds) and
`native/claw_targets.txt` and `native/icons/`. Then copy `dist/launch_nightfarers.bat`, `dist/README.md`, `package/` and
`native/` into one folder: that folder is the mod.
