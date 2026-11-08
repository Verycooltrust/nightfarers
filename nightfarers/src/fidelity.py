"""Read a recording (src/native rig or src/nr_rig) and list what happened per skill or ultimate clip; compare two recordings.

  python fidelity.py show <recording.jsonl> <NR regulation-bin dir>
  python fidelity.py compare <reference.jsonl> <run.jsonl> [--tolerance 0.1]

NR recordings log each new bullet's candidate ints (bullet_raw); ids are the ones that exist in NR's Bullet param, and the
offset most of them share is reported, so a wrong match is visible. SpEffects are kept only if NR's param has them.
Evidence: what a recording shows is [Run] (or [User] where the user played); the limits in `compare` are chosen here.
"""
import collections
import json
import sys
import xml.etree.ElementTree as ET


def load(path):
    return [json.loads(line) for line in open(path) if line.strip()]


def param_ids(path):
    root = ET.parse(path).getroot()
    rows = root.find("rows")
    return {int(r.get("id")) for r in (rows if rows is not None else root)}


def resolve(rows, reg):
    """Turn bullet_raw into bullet ids; drop SpEffects NR doesn't have."""
    bullets, sps = param_ids(f"{reg}/Bullet.dump.xml"), param_ids(f"{reg}/SpEffectParam.param.xml")
    offsets = collections.Counter()
    for r in rows:
        for o, v in r.get("bullet_raw", []):
            if v in bullets:
                offsets[o] += 1
    best = offsets.most_common(3)
    print("bullet id offsets:", best)
    out = []
    for r in rows:
        if "bullet_raw" in r:
            ids = {v for o, v in r["bullet_raw"] if v in bullets and (not best or o in dict(best))}
            out += [{"t": r["t"], "bullet": i} for i in sorted(ids)]
        elif ("sp" in r and r["sp"] not in sps) or ("sp_end" in r and r["sp_end"] not in sps):
            continue
        else:
            out.append(r)
    return out


def is_kit(a):
    return a >= 900_000_000


def show(rows):
    ev = [r for r in rows if "pos" not in r]
    print("kit clips:", sorted(collections.Counter(r["anim"] for r in ev if is_kit(r.get("anim", 0))).items()))
    print("bullets:", collections.Counter(r["bullet"] for r in ev if "bullet" in r).most_common(80))
    print("speffects:", collections.Counter(r["sp"] for r in ev if "sp" in r).most_common(80))
    seen = set()
    for i, r in enumerate(ev):
        a = r.get("anim", 0)
        if not is_kit(a) or a in seen:
            continue
        seen.add(a)
        print(f"--- {a} at {r['t']:.2f}")
        for q in ev[i + 1:]:
            dt = q["t"] - r["t"]
            if dt > 4 or (is_kit(q.get("anim", 0)) and q["anim"] // 1000 != a // 1000):
                break
            if "anim" in q and q["anim"] % 1_000_000 < 500_000 and dt > 0.5:
                break
            print(f"   {dt:6.3f}", {k: v for k, v in q.items() if k not in ("t", "play")})


def timeline(rows):
    """First occurrence of each kit clip: following clips with times, and the distance moved."""
    out, seen = {}, set()
    pos = [r for r in rows if "pos" in r]
    ev = [r for r in rows if "anim" in r]
    for i, r in enumerate(ev):
        a = r["anim"]
        if not is_kit(a) or a in seen:
            continue
        seen.add(a)
        follow = [(q["anim"], round(q["t"] - r["t"], 3)) for q in ev[i + 1:i + 4] if q["t"] - r["t"] < 4]
        before = next((p["pos"] for p in reversed(pos) if p["t"] <= r["t"]), None)
        after = next((p["pos"] for p in pos if p["t"] >= r["t"] + 1), None)
        moved = None
        if before and after:
            moved = round(sum((x - y) ** 2 for x, y in zip(before, after)) ** 0.5, 2)
        out[a] = dict(follow=follow, moved=moved)
    return out


def compare(ref, run, tol):
    a, b = timeline(ref), timeline(run)
    bad = 0
    for clip in sorted(a):
        if clip not in b:
            print(f"MISSING {clip}")
            bad += 1
            continue
        notes = []
        for (x, tx), (y, ty) in zip(a[clip]["follow"], b[clip]["follow"]):
            if x % 1_000_000 != y % 1_000_000:
                notes.append(f"next clip {x} vs {y}")
            elif abs(tx - ty) > tol:
                notes.append(f"{x} after {tx} vs {ty} s")
        print(("DIFF " if notes else "ok   ") + str(clip), "; ".join(notes), f"moved {a[clip]['moved']} vs {b[clip]['moved']} m")
        bad += bool(notes)
    print(f"{bad} of {len(a)} kit clips differ (tolerance {tol} s)")
    return bad


if __name__ == "__main__":
    if sys.argv[1] == "show":
        show(resolve(load(sys.argv[2]), sys.argv[3]))
    else:
        tol = float(sys.argv[sys.argv.index("--tolerance") + 1]) if "--tolerance" in sys.argv else 0.1
        sys.exit(1 if compare(load(sys.argv[2]), load(sys.argv[3]), tol) else 0)
