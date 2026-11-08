#!/usr/bin/env bash
# Stage 1: convert Wylder's Nightreign parts and repack them for Elden Ring.
#   build_wylder_parts.sh            -> work/s1/pk/*.partsbnd.dcx (ids 5000/5001, for the new items)
#   build_wylder_parts.sh swap       -> also work/s1/swapN/: the same models under the Samurai starting gear's
#                                       ids (look test without param edits)
# Needs work/s1/nr/parts/*-partsbnd-dcx (WitchyBND unpack of the user's own Nightreign files) and work/s1/stub1.
set -euo pipefail
cd "$(dirname "$0")/../work/s1"
W=$(realpath ../../tools/WitchyBND-3.0.1.0-win-x64/WitchyBND.exe)
B=$(realpath ../bin/flvertool/flvertool.exe)

stamp=$(date +%H%M%S)
pk=pk_$stamp
mkdir -p "$pk"
for p in bd_m_5000 bd_m_5000_l wp_a_5000 wp_a_5000_l wp_a_5001 wp_a_5001_l; do
  cp -r "nr/parts/$p-partsbnd-dcx" "$pk/"
  for f in "$pk/$p-partsbnd-dcx"/*.flver; do "$B" convert "$f" "$f.new" >/dev/null; mv "$f.new" "$f"; done
done
(cd "$pk" && timeout 600 "$W" -s *-partsbnd-dcx >/dev/null 2>&1 || true)
echo "converted parts in work/s1/$pk"

[ "${1:-}" = swap ] || exit 0
sw=swap_$stamp
mkdir -p "$sw"
# copy <src dir> <old internal name> <new internal name> <new archive base name>
swap() {
  local dst="$sw/$4-partsbnd-dcx"
  cp -r "$1" "$dst"
  for f in "$dst"/*"$2"*; do mv "$f" "${f//$2/$3}"; done
  sed -i "s/$2/$3/g; s#<filename>[a-z_0-9]*\.partsbnd#<filename>$4.partsbnd#" "$dst/_witchy-bnd4.xml"
}
for l in "" _l; do
  for body in 1360 1361; do swap "$pk/bd_m_5000$l-partsbnd-dcx" BD_M_5000 "BD_M_$body" "bd_m_$body$l"; done
  swap "$pk/wp_a_5000$l-partsbnd-dcx" WP_A_5000 WP_A_0550 "wp_a_0550$l"
  swap "$pk/wp_a_5001$l-partsbnd-dcx" WP_A_5001 WP_A_2108 "wp_a_2108$l"
  for k in hd am lg; do K=${k^^}; swap "stub1/${k}_m_5000$l-partsbnd-dcx" "${K}_M_5000" "${K}_M_1360" "${k}_m_1360$l"; done
done
(cd "$sw" && timeout 600 "$W" -s *-partsbnd-dcx >/dev/null 2>&1 || true)
echo "swap parts in work/s1/$sw"
