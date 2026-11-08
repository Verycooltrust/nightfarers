#!/usr/bin/env bash
# Stage 4: Wylder's Claw Shot effects -> package/sfx/sfxbnd_commoneffects.ffxbnd.dcx.
# Needs, from the user's own game files: WitchyBND unpacks of both games' sfx/sfxbnd_commoneffects.ffxbnd.dcx
#   (work/s4/sfx/{nr,er}_commoneffects-ffxbnd-dcx-wffxbnd).
# NR FXR = ER's format plus Armored Core 6 features; src/port_fxr.py converts them (rules and checks: NOTES "FFX").
# The textures and models they use are already in ER's bundle; ER's own copies of shared ids (450322 etc.) are kept.
set -euo pipefail
cd "$(dirname "$0")/.."
W=$(realpath tools/WitchyBND-3.0.1.0-win-x64/WitchyBND.exe)
B=$(realpath work/bin/flvertool/flvertool.exe)
PY=work/venv/Scripts/python.exe
export DOTNET_ROLL_FORWARD=Major
nr=work/s4/sfx/nr_commoneffects-ffxbnd-dcx-wffxbnd
er=work/s4/sfx/er_commoneffects-ffxbnd-dcx-wffxbnd
out=work/s4/build/sfx
# Claw Shot: hit/pull/drag bullets (sfxId 3344xx) and the fire animation's TAE effects. The hit bullet's 334400 is not
# used (build_wylder_params CLAW_BULLET_OVERRIDES: it shows a tornado NR doesn't).
seeds=$("$PY" -I src/hero.py "${NF_HERO:-heroes/wylder.toml}" skill.effects),$("$PY" -I src/hero.py "${NF_HERO:-heroes/wylder.toml}" ultimate.effects)
# The seeds, every effect they name, and the textures and models Elden Ring lacks.
mkdir -p work/s4/build
"$B" portsfx work/s4/sfx/nr_commoneffects.ffxbnd.dcx work/s4/sfx/er_commoneffects.ffxbnd.dcx "$seeds" work/s4/build/sfx_needs.txt
ids=$(sed -n 's/^effect //p' work/s4/build/sfx_needs.txt | tr -d '\r' | paste -sd' ')
sed -n 's/^model /NOT PORTED, NR model: /p' work/s4/build/sfx_needs.txt

rm -rf "$out" && mkdir -p "$out/xml" "$out/er"
for id in $ids; do
  [ -e "$er/effect/f$(printf %09d "$id").fxr" ] && { echo "Elden Ring already has effect $id"; exit 1; }
  "$B" fxrcheck -xml "$out/xml" "$nr/effect/f$(printf %09d "$id").fxr" | grep -q "byte4 01" || { echo "effect $id: not an NR FXR"; exit 1; }
  "$PY" -I src/port_fxr.py "$out/xml/f$(printf %09d "$id").fxr.b1.xml" "$out/xml/f$(printf %09d "$id").er.xml"
done
cp -r "$er" "$out/er/"
bnd="$out/er/${er##*/}"
args=""
for id in $ids; do
  args="$args $out/xml/f$(printf %09d "$id").er.xml $bnd/effect/f$(printf %09d "$id").fxr"
  cp "$nr/ResourceList/f$(printf %09d "$id").ffxreslist" "$bnd/ResourceList/"
done
"$B" fxrfromxml $args
# Every converted effect must read back as a plain Elden Ring FXR.
"$B" fxrcheck $(for id in $ids; do echo "$bnd/effect/f$(printf %09d "$id").fxr"; done) | grep -v "^FXRVersion" | grep -v "byte4 00 ver Sekiro" && exit 1
for tex in $(sed -n 's/^tex //p' work/s4/build/sfx_needs.txt | tr -d '\r'); do cp "$nr/tex/"*"$tex"* "$bnd/tex/"; done
(cd "$out/er" && timeout 1800 "$W" -s "${er##*/}" >/dev/null 2>&1 || true)
mkdir -p package/sfx
cp "$out/er/er_commoneffects.ffxbnd.dcx" package/sfx/sfxbnd_commoneffects.ffxbnd.dcx

# Sounds: NR's hero bank as its own bank, loaded by ERSoundBankLoader (merging it into cs_main never worked, NOTES "Sound").
hero=${NF_HERO:-heroes/wylder.toml}
get() { "$PY" -I src/hero.py "$hero" "$@"; }
bank_id=$(get sound.chr_bank_id)
mkdir -p package/sd/enus native/sound_loader
"$PY" -I src/port_sound.py rename "work/nr-game/sd/$(get sound.bank).bnk" "cs_c$bank_id" "package/sd/enus/cs_c$bank_id.bnk" "$(get sound.drop_object_types)"
cp "$PROGRAMFILES (x86)/Steam/steamapps/common/ELDEN RING/Game/Dll/ERSoundBankLoader/er_sound_bank_loader.dll" native/sound_loader/
sed "s#BANK_DIR#$(cygpath -w "$PWD/package/sd/enus" | sed 's#\\#\\\\#g')#; s#GROUP#$(get moveset.override_group)#; s#BANK_ID#$bank_id#" src/sound_loader.ini > native/sound_loader/ersoundbank_loader.ini
ls -la package/sfx
