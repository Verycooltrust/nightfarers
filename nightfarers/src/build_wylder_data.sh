#!/usr/bin/env bash
# Stages 1-3: build Wylder's params and texts into package/ (regulation.bin, item and menu names).
# Needs the pristine WitchyBND unpacks from the user's own Elden Ring files:
#   work/s1/er/regulation.bin + regulation-bin/ (XML; WepAbsorpPosParam.param.xml too), work/s1/er/msg/item_dlc02*, work/s2/er-msg/menu_dlc02*.
set -euo pipefail
cd "$(dirname "$0")/.."
W=$(realpath tools/WitchyBND-3.0.1.0-win-x64/WitchyBND.exe)
B=$(realpath work/bin/flvertool/flvertool.exe)
PY="$APPDATA/uv/python/cpython-3.12.16-windows-x86_64-none/python.exe"
out=work/s2/build
mkdir -p "$out"

"$PY" -I src/build_wylder_params.py work/s1/er/regulation-bin "$out/regulation-bin" \
  work/s1/er/msg/item_dlc02-msgbnd-dcx "$out/item" work/s2/er-msg/menu_dlc02-msgbnd-dcx "$out/menu" \
  work/s1/nr/regulation-bin

params=(EquipParamProtector EquipParamWeapon CharaInitParam BaseChrSelectMenuParam CharMakeMenuListItemParam SpEffectParam
        BehaviorParam_PC AtkParam_Pc Bullet WepAbsorpPosParam)
(cd "$out/regulation-bin" && timeout 600 "$W" -s "${params[@]/%/.param.xml}" >/dev/null 2>&1 || true)
(cd "$out/item" && timeout 300 "$W" -s ProtectorName.fmg.xml WeaponName.fmg.xml >/dev/null 2>&1 || true)
(cd "$out/menu" && timeout 300 "$W" -s GR_MenuText.fmg.xml GR_LineHelp.fmg.xml >/dev/null 2>&1 || true)

files=(); for p in "${params[@]}"; do files+=("$out/regulation-bin/$p.param"); done
"$B" regpack work/s1/er/regulation.bin package/regulation.bin "${files[@]}"
"$B" bndpack work/s1/er/msg/item_dlc02.msgbnd.dcx package/msg/engus/item_dlc02.msgbnd.dcx \
  "$out/item/ProtectorName.fmg" "$out/item/WeaponName.fmg"
"$B" bndpack work/s2/er-msg/menu_dlc02.msgbnd.dcx package/msg/engus/menu_dlc02.msgbnd.dcx \
  "$out/menu/GR_MenuText.fmg" "$out/menu/GR_LineHelp.fmg"

# Class portrait (Nightreign art from work/s2/nr-art) -> menu/hi/01_common sprite atlas + layout.
tex="$out/menu-tex"
rm -rf "$tex" && mkdir -p "$tex" package/menu/hi
cp -r work/s2/er-menu/01_common-tpf-dcx work/s2/er-menu/01_common-sblytbnd-dcx "$tex/"
work/venv/Scripts/python.exe -I src/build_wylder_portrait.py \
  work/s2/nr-art/MENU_Character_49000-tpf-dcx/MENU_Character_49000.dds "$tex/01_common-tpf-dcx/SB_Preset_2.dds" \
  "$tex/01_common-sblytbnd-dcx/SB_Preset_2.layout" tools/texconv/texconv.exe
(cd "$tex" && timeout 900 "$W" -s 01_common-tpf-dcx 01_common-sblytbnd-dcx >/dev/null 2>&1 || true)
cp "$tex/01_common.tpf.dcx" "$tex/01_common.sblytbnd.dcx" package/menu/hi/
# The class screen shows portrait frame imageId-1 of sprite 93 and stops at its last frame (MENU_Ch_12), so the
# portrait needs its own frame there too: imageId 18 = frame 17 = MENU_Ch_13.
"$B" gfxaddframe work/er-game/menu/04_200_chrmake_basechrselect.gfx package/menu/04_200_chrmake_basechrselect.gfx \
  93 MENU_Ch_12 MENU_Ch_13
# The helper's HUD sprites, NR's (cut by src/build_hud_icons.py into work/s5/nrmenu/icons; NOTES "HUD").
mkdir -p native/icons && cp work/s5/nrmenu/icons/*.rgba native/icons/
# Claw Shot: which enemies drag Wylder instead of being pulled (NR NpcParam, WitchyBND-unpacked to XML).
"$PY" -I src/build_claw_targets.py work/s1/nr/regulation-bin/NpcParam.param.xml native/claw_targets.txt
