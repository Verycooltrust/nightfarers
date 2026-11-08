"""Claw Shot pull/drag table for the native helper: which enemies drag Wylder to them instead of being pulled.

Nightreign marks those enemies with SpEffect 700500 in one of NpcParam's resident spEffectID slots (Smithbox names it
"[Grapple] Not pulled, pull hero to target instead"); size alone does not decide it (Crucible Knights: radius 0.5, marked).
Elden Ring's rows have no such mark, so the helper looks a target up by its NpcParam id: the exact Nightreign row, else
the majority of that model's rows (id // 10000), else its hit radius (src/native/src/lib.rs).

Output lines: "m <model> <0|1>" for every Nightreign model, "r <row> <0|1>" for rows that differ from their model.
Usage: build_claw_targets.py <NR NpcParam.param.xml> <out.txt>
"""
import re
import sys
from collections import defaultdict

NO_PULL = "700500"


def main(src, out):
    rows = {}
    for line in open(src, encoding="utf-8-sig"):
        if line.startswith("<row "):
            fields = dict(re.findall(r'(\w+)="([^"]*)"', line))
            rows[int(fields["id"])] = any(k.lower().startswith("speffectid") and v == NO_PULL for k, v in fields.items())
    models = defaultdict(list)
    for row, drag in rows.items():
        models[row // 10000].append(drag)
    model_drag = {m: sum(v) * 2 > len(v) for m, v in models.items()}
    with open(out, "w", newline="\n") as f:
        for m in sorted(model_drag):
            f.write(f"m {m} {int(model_drag[m])}\n")
        for row in sorted(rows):
            if rows[row] != model_drag[row // 10000]:
                f.write(f"r {row} {int(rows[row])}\n")
    print(f"claw targets: {len(rows)} rows, {len(models)} models, {sum(model_drag.values())} models drag")


if __name__ == "__main__":
    main(*sys.argv[1:3])
