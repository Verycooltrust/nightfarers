"""Stage 3: append the behaviour names the graft added to Elden Ring's action/*nameid.txt lists.

  python add_nameids.py <er action dir> <graft names.json> <out action dir>
Lines look like `2759 = "W_Name"` (id padded to 4) under a `Num  = <count>` line. The header bytes are kept as is.
"""
import json
import re
import sys
from pathlib import Path

LISTS = {"events": "eventnameid.txt", "states": "statenameid.txt", "variables": "variablenameid.txt"}


def main(src, names_json, out):
    added = json.load(open(names_json))
    Path(out).mkdir(parents=True, exist_ok=True)
    for kind, fname in LISTS.items():
        data = (Path(src) / fname).read_bytes()
        existing = set(re.findall(rb'= "([^"]*)"', data))
        num = int(re.search(rb"^Num  = (\d+)$", data, re.M).group(1))
        new = [n for n in added[kind] if n.encode() not in existing]
        lines = b"".join(f'{num + 1 + i:<4} = "{n}"\n'.encode() for i, n in enumerate(new))
        data = re.sub(rb"^Num  = \d+$", f"Num  = {num + len(new)}".encode(), data, count=1, flags=re.M)
        if not data.endswith(b"\n"):
            data += b"\n"
        (Path(out) / fname).write_bytes(data + lines)
        print(f"{fname}: +{len(new)} {new}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
