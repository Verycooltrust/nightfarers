"""Which objects of a Nightreign bank does Elden Ring's Wwise refuse? With the game running and the sound loader retrying its bank,
this swaps test versions of the bank file and reads the loader's log. It never touches the game: only the file and the log.

  python bank_bisect.py <hero bank> <bank file the loader reads> <loader log> <bank name> [seconds per try]

Each try drops one or more HIRC object types. Stops at the first version that loads, and leaves that file in place.
"""
import struct
import sys
import time
from pathlib import Path

TYPES = {2: "sound", 3: "action", 4: "event", 5: "random/sequence", 6: "switch", 7: "actor-mixer", 9: "layer", 14: "attenuation",
         17: "FX custom", 22: "time mod"}
TRIES = [[22], [17], [14], [9], [6], [22, 17], [22, 17, 14], [22, 17, 14, 9], [22, 17, 14, 9, 6], [7], [5], [2, 3, 4, 5, 6, 7, 9, 14, 17, 22]]
ER_PROJECT_ID = 0x772


def fnv(name):
    h = 2166136261
    for c in name.lower().encode():
        h = ((h * 16777619) & 0xffffffff) ^ c
    return h


def sections(b):
    o, out = 0, []
    while o + 8 <= len(b):
        tag, n = b[o:o + 4], struct.unpack_from("<I", b, o + 4)[0]
        out.append((tag, bytes(b[o + 8:o + 8 + n])))
        o += 8 + n
    return out


def variant(raw, name, drop):
    out = bytearray()
    for tag, body in sections(raw):
        if tag == b"BKHD":
            body = bytearray(body)
            struct.pack_into("<I", body, 4, fnv(name))
            struct.pack_into("<I", body, 16, ER_PROJECT_ID)
        elif tag == b"HIRC":
            kept, p = [], 4
            for _ in range(struct.unpack_from("<I", body, 0)[0]):
                t, sz = struct.unpack_from("<BI", body, p)
                if t not in drop:
                    kept.append(body[p:p + 5 + sz])
                p += 5 + sz
            body = struct.pack("<I", len(kept)) + b"".join(kept)
        out += tag + struct.pack("<I", len(body)) + body
    return bytes(out)


def main(hero, target, log, name, seconds="4"):
    raw, target, log = Path(hero).read_bytes(), Path(target), Path(log)
    original = target.read_bytes()
    print("sizes in the log tell which version the loader read")
    for drop in TRIES:
        data = variant(raw, name, set(drop))
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        start = log.stat().st_size
        time.sleep(float(seconds))
        new = log.read_bytes()[start:].decode("utf-8", "replace").splitlines()
        tagged = [l for l in new if f"size={len(data)} " in l and "failed" in l]
        other = [l for l in new if "failed" not in l and "player conditions" not in l]
        print(f"drop {[TYPES[t] for t in drop]}: size {len(data)}, failures {len(tagged)}, other lines: {other[:2]}")
        if other or (new and not tagged):
            print("LOADED or changed: this version stays in place")
            return
    target.write_bytes(original)
    print("no version loaded; original restored")


if __name__ == "__main__":
    main(*sys.argv[1:])
