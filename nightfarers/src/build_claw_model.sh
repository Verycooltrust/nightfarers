#!/usr/bin/env bash
# Stage 4: Wylder's Claw Shot claw + chain model -> package/parts/wp_a_5000{,_l}.partsbnd.dcx, package/material/.
# NR draws the claw with an engine-only event (TAE 1001 InvokeHeroSkill) on its hero skill model WP_A_5002 (331 bones,
# 4.2 m chain; its anibnd has the Claw Shot clips a900_500000..505010 under the character's animation ids). Elden Ring
# plays a weapon model's clip that matches the character's animation (bows, sheaths), so the claw becomes model 1 of
# Wylder's greatsword, laid out like ER's katana sheaths (wp_a_0550: WP_A_0550_1.flver id 201, WP_A_0550_1.anibnd
# id 401 with skeleton_1.hkx, WP_A_0550_1.compendium, aXXX_YYYYYY_1.hkx). Its textures (WP_A_5003_a/m/n, shared with
# the Onslaught Stake model) join the sword's tpf; its material P[WP_A_5003]_metal joins the package material bundle.
# Needs: work/s1/pk_000121/wp_a_5000{,_l}-partsbnd-dcx (converted sword, build_wylder_parts.sh), the user's NR
# parts/wp_a_5002{,_l}.partsbnd.dcx and wp_a_5003.partsbnd.dcx (work/nr-game), NR matbins (work/s1/nr/mat unpack).
set -euo pipefail
cd "$(dirname "$0")/.."
W=$(realpath tools/WitchyBND-3.0.1.0-win-x64/WitchyBND.exe)
B=$(realpath work/bin/flvertool/flvertool.exe)
PY=work/venv/Scripts/python.exe
export DOTNET_ROLL_FORWARD=Major
out=work/s4/build/claw
rm -rf "$out" && mkdir -p "$out/nr" "$out/pk"

for p in wp_a_5002 wp_a_5002_l wp_a_5003; do cp "work/nr-game/parts/$p.partsbnd.dcx" "$out/nr/"; done
(cd "$out/nr" && timeout 600 "$W" -s *.partsbnd.dcx >/dev/null 2>&1 || true)
(cd "$out/nr/wp_a_5003-partsbnd-dcx" && timeout 120 "$W" -s WP_A_5003.tpf >/dev/null 2>&1 || true)
tex="$out/nr/wp_a_5003-partsbnd-dcx/WP_A_5003-tpf"
[ -e "$tex/WP_A_5003_a.dds" ] || { echo "no claw textures"; exit 1; }

for L in "" _L; do
  l=${L,,}
  src="$out/nr/wp_a_5002$l-partsbnd-dcx"
  d="$out/pk/wp_a_5000$l-partsbnd-dcx"
  cp -r "work/s1/pk_000121/wp_a_5000$l-partsbnd-dcx" "$d"
  # Model 1 = the claw (FLVER converted to Elden Ring's layout).
  "$B" convert "$src/WP_A_5002$L.flver" "$d/WP_A_5000_1$L.flver" >/dev/null
  # Its animations, renamed the way ER names a second model's (the same anibnd in the main and _l archives).
  (cd "$src" && timeout 120 "$W" -s WP_A_5002.anibnd >/dev/null 2>&1 || true)
  a="$src/WP_A_5002-anibnd-wanibnd"
  # The sword (model 0) gets the same clips under the plain ids: ER's Uchigatana lists every sheath clip id
  # (a614_040050_1) in the main anibnd too (a614_040050). The claw skeleton shares no bone names with the sword.
  m0="$src/WP_A_5000-anibnd-wanibnd"; rm -rf "$m0"; cp -r "$a" "$m0"
  mv "$m0/WP_A_5002.compendium" "$m0/WP_A_5000.compendium"
  sed -i 's#<filename>WP_A_5002.anibnd#<filename>WP_A_5000.anibnd#; s#\\WP_A_5002\\hkx_compendium#\\WP_A_5000\\hkx_compendium#;
          s#<path>WP_A_5002.compendium#<path>WP_A_5000.compendium#' "$m0/_witchy-anibnd4.xml"
  (cd "$src" && rm -f WP_A_5000.anibnd && timeout 120 "$W" -s WP_A_5000-anibnd-wanibnd >/dev/null 2>&1 || true)
  [ -e "$src/WP_A_5000.anibnd" ] || { echo "sword anibnd not packed"; exit 1; }
  cp "$src/WP_A_5000.anibnd" "$d/"
  for f in "$a"/a*_*.hkx; do b=${f##*/}; mv "$f" "$a/${b%.hkx}_1.hkx"; done
  mv "$a/skeleton.hkx" "$a/skeleton_1.hkx"; mv "$a/WP_A_5002.compendium" "$a/WP_A_5000_1.compendium"
  sed -i 's#<filename>WP_A_5002.anibnd#<filename>WP_A_5000_1.anibnd#; s#\\WP_A_5002\\hkx_compendium#\\WP_A_5000\\hkx_compendium#;
          s#<path>skeleton.hkx#<path>skeleton_1.hkx#; s#<path>WP_A_5002.compendium#<path>WP_A_5000_1.compendium#' "$a/_witchy-anibnd4.xml"
  (cd "$src" && rm -f WP_A_5000_1.anibnd && mv WP_A_5002-anibnd-wanibnd WP_A_5000_1-anibnd-wanibnd \
     && timeout 120 "$W" -s WP_A_5000_1-anibnd-wanibnd >/dev/null 2>&1 || true)
  [ -e "$src/WP_A_5000_1.anibnd" ] || { echo "claw anibnd not packed"; exit 1; }
  cp "$src/WP_A_5000_1.anibnd" "$d/"
  # DIAG_SHEATH=1: model 1 = Elden Ring's own Uchigatana sheath (known good) instead of the claw: does a greatsword
  # show a model 1 at all?
  if [ "${DIAG_SHEATH:-0}" = 1 ]; then
    k="$out/er_0550$l"; mkdir -p "$k"; cp "work/er-game/parts/wp_a_0550$l.partsbnd.dcx" "$k/"
    (cd "$k" && timeout 120 "$W" -s "wp_a_0550$l.partsbnd.dcx" >/dev/null 2>&1 || true)
    kd="$k/wp_a_0550$l-partsbnd-dcx"
    cp "$kd/WP_A_0550_1$L.flver" "$d/WP_A_5000_1$L.flver"; cp "$kd/WP_A_0550_1.anibnd" "$d/WP_A_5000_1.anibnd"
    (cd "$kd" && timeout 120 "$W" -s "WP_A_0550$L.tpf" >/dev/null 2>&1 || true)
    tex="$kd/WP_A_0550$L-tpf"
  fi
  # Textures: the claw's three maps go into the sword's tpf.
  (cd "$d" && timeout 120 "$W" -s "WP_A_5000$L.tpf" >/dev/null 2>&1 || true)
  t="$d/WP_A_5000$L-tpf"
  cp "$tex"/*.dds "$t/"
  "$PY" -I - "$t/_witchy-tpf.xml" "$tex/_witchy-tpf.xml" <<'EOF'
import re, sys
dst, src = (open(p, encoding='utf-8-sig').read() for p in sys.argv[1:3])
new = re.findall(r'\s*<texture>.*?</texture>', src, re.S)
open(sys.argv[1], 'w', encoding='utf-8-sig').write(dst.replace('\n  </textures>', ''.join(new) + '\n  </textures>', 1))
EOF
  rm -f "$d/WP_A_5000$L.tpf"; (cd "$d" && timeout 120 "$W" -s "WP_A_5000$L-tpf" >/dev/null 2>&1 || true)
  [ -e "$d/WP_A_5000$L.tpf" ] || { echo "tpf not packed"; exit 1; }
  rm -rf "$t"
  # Binder entries, ids as in ER's wp_a_0550{,_l}.
  # DIAG_NOANIM=1: no anibnd for model 1 (the claw in its modelled pose): does the mesh itself render?
  [ "${DIAG_NOANIM:-0}" = 1 ] && rm -f "$d/WP_A_5000_1.anibnd" "$d/WP_A_5000.anibnd"
  "$PY" -I - "$d/_witchy-bnd4.xml" "$L" "${DIAG_NOANIM:-0}" <<'EOF'
import sys
p, L, noanim = sys.argv[1], sys.argv[2], sys.argv[3] == '1'
s = open(p, encoding='utf-8-sig').read()
add = ''.join(f'\n    <file>\n      <flags>Flag1</flags>\n      <id>{i}</id>\n      <path>{n}</path>\n    </file>'
              for i, n in ((201, f'WP_A_5000_1{L}.flver'), (400, 'WP_A_5000.anibnd'), (401, 'WP_A_5000_1.anibnd'))
              if i < 400 or not noanim)
open(p, 'w', encoding='utf-8-sig').write(s.replace('\n  </files>', add + '\n  </files>', 1))
EOF
done
(cd "$out/pk" && timeout 600 "$W" -s *-partsbnd-dcx >/dev/null 2>&1 || true)
for l in "" _l; do cp "$out/pk/wp_a_5000$l.partsbnd.dcx" package/parts/; done

# Material: NR's P[WP_A_5003]_metal with Elden Ring's full shader path, into the package bundle.
m="$out/mat"; mkdir -p "$m"
cp package/material/allmaterial.matbinbnd.dcx "$m/"
(cd "$m" && timeout 600 "$W" -s allmaterial.matbinbnd.dcx >/dev/null 2>&1 || true)
mx="$m/allmaterial-matbinbnd-dcx-wmatbinbnd/Parts/matxml"
cp "work/s1/nr/mat/allmaterial-matbinbnd-dcx-wmatbinbnd/Parts/matxml/P[WP_A_5003]_metal.matbin" "$m/"
(cd "$m" && timeout 60 "$W" -s "P[WP_A_5003]_metal.matbin" >/dev/null 2>&1 || true)
"$PY" -I src/set_shader_path.py "$m/P[WP_A_5003]_metal.matbin.xml"
rm "$m/P[WP_A_5003]_metal.matbin"; (cd "$m" && timeout 60 "$W" -s "P[WP_A_5003]_metal.matbin.xml" >/dev/null 2>&1 || true)
cp "$m/P[WP_A_5003]_metal.matbin" "$mx/"
rm "$m/allmaterial.matbinbnd.dcx"; (cd "$m" && timeout 600 "$W" -s allmaterial-matbinbnd-dcx-wmatbinbnd >/dev/null 2>&1 || true)
cp "$m/allmaterial.matbinbnd.dcx" package/material/
ls -la package/parts/wp_a_5000*.partsbnd.dcx package/material/allmaterial.matbinbnd.dcx
