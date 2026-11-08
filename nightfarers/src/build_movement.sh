#!/usr/bin/env bash
# Stages 3-4: Nightreign's Surge Sprint, sprint jump, roll-to-move and Wylder's greatsword moveset -> package/ (player script, behaviour graph, animations, TAE, name lists).
# Params (SpEffects, armor) are built by build_wylder_data.sh. Needs, from the user's own game files:
#   work/s3/hks/er_c0000.lua (DSLuaDecompiler of ER action/script/c0000.hks)
#   work/s3/beh/{nr,er}_beh.xml (HKLib XML of each game's chr/c0000.behbnd.dcx Behaviors/c0000.hkx)
#   work/s3/beh/er_c0000-behbnd-dcx, work/s3/anim/{nr,er}_c0000{,_a00_hi,_a0x,_a1x}-anibnd-dcx-wanibnd (WitchyBND)
#   work/s4/anim/nr_c0000_a2x-anibnd-dcx-wanibnd, work/s4/anim/er_c0000_a9x-anibnd-dcx-wanibnd (WitchyBND)
set -euo pipefail
cd "$(dirname "$0")/.."
W=$(realpath tools/WitchyBND-3.0.1.0-win-x64/WitchyBND.exe)
B=$(realpath work/bin/flvertool/flvertool.exe)
HK=$(realpath tools/hklib-0.1.2/net7.0/HKLib.CLI.exe)
PY="$APPDATA/uv/python/cpython-3.12.16-windows-x86_64-none/python.exe"
export DOTNET_ROLL_FORWARD=Major  # HKLib targets .NET 7; only newer runtimes are installed
HERO=${NF_HERO:-heroes/wylder.toml}
get() { "$PY" -I src/hero.py "$HERO" "$@"; }
out=work/s3/build
anim=work/s3/anim
mkdir -p "$out" package/action/script package/chr

# Player script and name lists.
"$PY" -I src/build_hks.py work/s3/hks/er_c0000.lua package/action/script/c0000.hks work/s3/hks/nr_c0000.lua

# Behaviour graph: graft NR's sprint nodes, back to HKX, into ER's behbnd.
"$PY" -I src/graft_behavior.py work/s3/beh/nr_beh.xml work/s3/beh/er_beh.xml "$out/c0000_beh.xml" "$out/graft_names.json" \
  work/s4/anim/nr_c0000_a2x-anibnd-dcx-wanibnd
(cd "$out" && rm -f c0000_beh.hkx && "$HK" c0000_beh.xml >/dev/null)
"$PY" -I src/add_nameids.py work/er-game/action "$out/graft_names.json" package/action
rm -rf "$out/beh" && mkdir -p "$out/beh" && cp -r work/s3/beh/er_c0000-behbnd-dcx "$out/beh/"
cp "$out/c0000_beh.hkx" "$out/beh/er_c0000-behbnd-dcx/Behaviors/c0000.hkx"
(cd "$out/beh" && timeout 600 "$W" -s er_c0000-behbnd-dcx >/dev/null 2>&1 || true)
cp "$out/beh/er_c0000.behbnd.dcx" package/chr/c0000.behbnd.dcx

# Animations: NR's sprint, sprint-jump and roll-to-move clips (same skeleton and compendiums as ER) into ER's archives.
ids="020300 020301 020302 020310 020320 020330 022300 026260 053000 053004 053005 053006 053007 053008 202050 202145 202150 202155 202156 202165 202166 202175 202176"
rm -rf "$out/anim" && mkdir -p "$out/anim"
for a in c0000_a00_hi c0000_a0x c0000_a1x; do
  cp -r "$anim/er_$a-anibnd-dcx-wanibnd" "$out/anim/"
  n=0
  for id in $ids; do
    for f in $(find "$anim/nr_$a-anibnd-dcx-wanibnd/Target" -name "a0??_$id.hkx"); do
      rel=${f#"$anim/nr_$a-anibnd-dcx-wanibnd/Target/"}
      dst="$out/anim/er_$a-anibnd-dcx-wanibnd/$rel"
      [ -e "$dst" ] && { echo "ER already has $rel"; exit 1; }
      cp "$f" "$dst"; n=$((n + 1))
    done
  done
  echo "$a: +$n sprint animations"
  # DIAG_ER_JUMP=1: the sprint jump plays ER's own dash-jump clip (does the NR clip or the state fail to lift off?).
  if [ "${DIAG_ER_JUMP:-0}" = 1 ]; then
    for f in $(find "$out/anim/er_$a-anibnd-dcx-wanibnd" -name "a0??_202050.hkx"); do cp "${f%202050.hkx}202030.hkx" "$f"; done
  fi
done
# Sixth Sense's dodge: NR's a000 clips its TAE imports, where Elden Ring lacks them.
sixth_a00="$out/anim/er_c0000_a00_hi-anibnd-dcx-wanibnd/INTERROOT_win64/chr/c0000/hkx/a00_hi_compendium"
for id in $(get passive.clip_ids " "); do
  [ -e "$sixth_a00/a000_$id.hkx" ] || cp "$anim/nr_c0000_a00_hi-anibnd-dcx-wanibnd/Target/INTERROOT_win64/chr/c0000/hkx/a00_hi_compendium/a000_$id.hkx" "$sixth_a00/"
done
# TAE (events per animation) for every weapon-stance group that has the clips.
cp -r "$anim/er_c0000-anibnd-dcx-wanibnd" "$out/anim/"
map=102000=9102000,102001=9102001,102010=9102010,102022=9102022,102030=9102030,102020=0,8450001=0,8450101=0
tae_ids=20300,20301,20302,20310,20320,20330,22300,26260,53000,53004,53005,53006,53007,53008,202050,202145,202150,202155,202156,202165,202166,202175,202176
nt="$anim/nr_c0000-anibnd-dcx-wanibnd/Target/INTERROOT_win64/chr/c0000/tae"
et="$out/anim/er_c0000-anibnd-dcx-wanibnd/INTERROOT_win64/chr/c0000/tae"
for t in a00 a02 a03 a10 a12 a13 a14 a15 a16; do
  "$B" taegraft "$nt/$t.tae" "$et/$t.tae" "$et/$t.tae" $tae_ids $map 10150 | tail -1
  # NR clips lack ER's engine events for jumps (JumpTable 27 / 138 airborne, type 605 on every jump/land clip):
  # copy them from ER's dash jump (202030), landing (202130) and land-to-dash (202125).
  # The sprint jump takes all of ER's dash-jump events: with NR's own set (extra JumpTables, types 150/225/530/700/907)
  # it played but stayed on the ground at sprint speed.
  "$B" taeaddevents "$et/$t.tae" "$et/$t.tae" 202030 202050 "*"
  for id in 202145 202150; do "$B" taeaddevents "$et/$t.tae" "$et/$t.tae" 202130 $id 605; done
  for id in 202155 202156 202165 202166 202175 202176; do "$B" taeaddevents "$et/$t.tae" "$et/$t.tae" 202125 $id 605; done
done
"$B" taegraft "$nt/a00.tae" "$et/a00.tae" "$et/a00.tae" "$(get passive.tae_ids)" "$(get passive.tae_drop_speffects =0,)=0" 10150 | tail -1
# Wylder's greatsword (Stage 4): NR's greatsword clips (a025) and TAE (a25) as override group a290 (his sword's
# spAtkcategory). The clips go into ER's a9x archive: NR's a2x compendium is byte-identical to ER's a9x one.
# NR-only SpEffects (relic/hero hooks, missing or different in ER) and NR-only event type 10150 are dropped.
cp -r work/s4/anim/er_c0000_a9x-anibnd-dcx-wanibnd "$out/anim/"
a9="$out/anim/er_c0000_a9x-anibnd-dcx-wanibnd/INTERROOT_win64/chr/c0000/hkx/a9x_compendium"
n=0
nr_group=$(get moveset.nr_clip_group); group=$(get moveset.override_group)
nr_prefix=a$(printf %03d "$nr_group"); prefix=a$(printf %03d "$group")
for f in work/s4/anim/nr_c0000_a2x-anibnd-dcx-wanibnd/Target/INTERROOT_win64/chr/c0000/hkx/a2x_compendium/"$nr_prefix"_*.hkx; do
  b=${f##*/}; cp "$f" "$a9/${prefix}_${b#"$nr_prefix"_}"; n=$((n + 1))
done
# Wylder's own swings (NR weapon heroMovesetOverrideID) replace the generic greatsword's for the ids they have.
hero_group=$(get moveset.hero_clip_group); hero_prefix=a$(printf %03d "$hero_group")
hero_ids=""
for f in work/s4/anim/nr_c0000_a9x-anibnd-dcx-wanibnd/Target/INTERROOT_win64/chr/c0000/hkx/a9x_compendium/"$hero_prefix"_*.hkx; do
  b=${f##*/}; b=${b#"$hero_prefix"_}
  [ -e "$a9/${prefix}_$b" ] || { echo "$hero_prefix clip $b has no twin in the graph"; exit 1; }
  cp "$f" "$a9/${prefix}_$b"
  id=${b%.hkx}; id=$(echo "$id" | sed 's/^0*//'); hero_ids="$hero_ids,$id"
done
hero_ids=${hero_ids#,}
echo "$hero_prefix -> $prefix: $(echo "$hero_ids" | tr ',' '\n' | wc -l) of $n clips are Wylder's own"
# Claw Shot (a900_500000-509001; Elden Ring's a900 only has 40000-40006).
n=0
for f in work/s4/anim/nr_c0000_a9x-anibnd-dcx-wanibnd/Target/INTERROOT_win64/chr/c0000/hkx/a9x_compendium/$(get skill.clip_glob); do
  cp "$f" "$a9/"; n=$((n + 1))
done
for f in work/s4/anim/nr_c0000_a9x-anibnd-dcx-wanibnd/Target/INTERROOT_win64/chr/c0000/hkx/a9x_compendium/$(get ultimate.clip_glob); do
  cp "$f" "$a9/"; n=$((n + 1))
done
echo "c0000_a9x: +$n Claw Shot and Onslaught Stake animations"
claw_ids=$(get skill.tae_ids)
"$B" taegraft "$nt/a900.tae" "$et/a900.tae" "$et/a900.tae" $claw_ids 0=0 10150 | tail -1
# NR fires the claw from its hidden skill weapon (AttackBehavior source 3); Elden Ring has no such source, so the
# events use the default source (Wylder's sword, variation 390 -> 396 rows with prefix 100, see build_wylder_params).
"$B" taesetsource "$et/a900.tae" "$et/a900.tae" $claw_ids 3 0
# Onslaught Stake: same, plus the bullets fire from Wylder's body dummy instead of NR's device weapon.
ult_ids=$(get ultimate.tae_ids)
"$B" taegraft "$nt/a900.tae" "$et/a900.tae" "$et/a900.tae" "$ult_ids" 0=0 "$(get ultimate.tae_drop_types)" | tail -1
"$B" taesetbullet "$et/a900.tae" "$et/a900.tae" "$ult_ids" 4 0 "$(get ultimate.device_dummy)" "$(get ultimate.body_dummy)" "$(get ultimate.judge_map)"
# NR's whole-clip "Ultimate IFrames" flag (146) as Elden Ring's own invincibility flag.
"$B" taesetflag "$et/a900.tae" "$et/a900.tae" "$ult_ids" $(get ultimate.iframe_flag_map " ")
# NR effects spawn at NR's dummy polys (the hero devices at 450-454): add the ones Elden Ring's player model lacks.
"$B" adddummies work/er-game/chr/c0000.chrbnd.dcx work/nr-game/chr/c0000.chrbnd.dcx package/chr/c0000.chrbnd.dcx
nr_only=$(get moveset.tae_drop_speffects =0,)=0
# Only ids with an NR clip keep a290 timing: the rest fall back to ER's a025 clip AND a25 timing (NR events on ER's
# clip made moving jump attacks restart mid-swing; NR ships no a025_031040 etc.).
keep=$(cd "$a9" && ls "$prefix"_*.hkx | sed "s/${prefix}_0*//; s/\.hkx\$//" | paste -sd,)
keep=$(echo "$keep" | tr ',' '\n' | grep -vxFf <(echo "$hero_ids" | tr ',' '\n') | paste -sd,)
"$B" taeclone "$nt/a$nr_group.tae" "$et/a$group.tae" "$nr_group" "$group" "$nr_only" 10150 "$keep"
"$B" taegraft "$nt/a$hero_group.tae" "$et/a$group.tae" "$et/a$group.tae" "$hero_ids" "$nr_only" 10150 | tail -1
(cd "$out/anim" && timeout 1800 "$W" -s er_c0000-anibnd-dcx-wanibnd er_c0000_a00_hi-anibnd-dcx-wanibnd \
  er_c0000_a0x-anibnd-dcx-wanibnd er_c0000_a1x-anibnd-dcx-wanibnd er_c0000_a9x-anibnd-dcx-wanibnd >/dev/null 2>&1 || true)
for a in c0000 c0000_a00_hi c0000_a0x c0000_a1x c0000_a9x; do cp "$out/anim/er_$a.anibnd.dcx" "package/chr/$a.anibnd.dcx"; done
ls -la package/chr package/action/script
