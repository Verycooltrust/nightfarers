#!/usr/bin/env bash
# Is the package still what it was? Rebuilds it and compares hashes with a reference made by `check_same.sh save <dir>`.
#   check_same.sh save <dir>     rebuild, record package + decrypted params + texts
#   check_same.sh compare <dir>  rebuild, list differences (regulation.bin's encryption differs each build, so params count)
set -euo pipefail
cd "$(dirname "$0")/.."
mode=$1; dir=$2
mkdir -p "$dir"
bash src/build_wylder_data.sh > "$dir/build.log" 2>&1
bash src/build_movement.sh >> "$dir/build.log" 2>&1
bash src/build_sfx.sh >> "$dir/build.log" 2>&1
hashes() {
  (cd package && find . -type f ! -name regulation.bin -print0 | sort -z | xargs -0 sha256sum)
  (cd work/s2/build && sha256sum regulation-bin/*.param item/*.fmg menu/*.fmg)
}
if [ "$mode" = save ]; then
  hashes > "$dir/reference.sha"
  wc -l < "$dir/reference.sha"
else
  hashes > "$dir/now.sha"
  diff "$dir/reference.sha" "$dir/now.sha" && echo "SAME: $(wc -l < "$dir/now.sha") files"
fi
