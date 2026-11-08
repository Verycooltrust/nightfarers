"""Hero port report: for each nightfarer, list what Nightreign's data needs in Elden Ring, before anything is built.

  python hero_report.py <repo root> <out dir>

Reads the user's own unpacked files under work/ (never shipped) and writes <out dir>/<hero>.md, summary.md and
report.json. Everything here is read from files: evidence level [Source]. It sizes the job; it can't prove a move works.

Each hero's skill and ultimate live in clip group a90<n> (n = hero id - 1) with clip ids 5<n>xxxx and 6<n>xxxx. Items:
  auto    existing tools carry it (clip copy, TAE graft, param rows, FXR conversion, graph graft)
  check   carried, but a known difference needs a look (id collision, NR-only source, NR-only condition)
  module  needs native code: NR-only engine queries and engine-only TAE events
"""
import collections
import json
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERO_TYPES = ["NONE", "BALANCE", "TANK", "SHOOTER", "SPEED", "POWER", "NECROMANCER", "MAGIC", "TECHNICAL", "BUFFER", "ATTACKER"]
# What each NR-only env query is, as far as known. Anything else: "unknown", to read in NR before planning a module.
ENV_KNOWN = {
    371: ("hero type", "rebuilt"), 1122: ("button hold time", "rebuilt"),
    411: ("Claw Shot break", "rebuilt"), 412: ("Claw Shot hit type", "rebuilt"), 413: ("Claw Shot target distance", "rebuilt"),
    710: ("wall height", "planned: rays"), 711: ("wall", "planned: rays"), 2012: ("wall contact", "planned: rays"),
    389: ("ultimate", "planned: DLL"), 1011: ("ultimate gauge", "planned: DLL"), 1012: ("ultimate / damage", "planned: DLL"),
    376: ("summon", "hero module"), 380: ("summon", "hero module"), 381: ("summon", "hero module"),
    423: ("blink stake", "hero module"), 424: ("blink stake", "hero module"), 425: ("blink stake", "hero module"),
}
# TAE types with engine-only meaning in NR (no parameters to port).
TAE_ENGINE = {1001: "InvokeHeroSkill: shows the hero's skill model", 10150: "NR-only, dropped so far"}
TAE_ATTACK, TAE_BULLET, TAE_SOUND = 1, 2, 129
TAE_SPEFFECTS = (66, 67)
SOUND_LETTERS = {1: "c", 5: "s"}  # the two seen so far (NOTES "SOUND")


def ints(hex_params):
    b = bytes.fromhex(hex_params)
    return [struct.unpack_from("<i", b, i)[0] for i in range(0, len(b) - 3, 4)]


def rows(path):
    root = ET.parse(path).getroot()
    found = root.find("rows")
    return {r.get("id"): r.attrib for r in (found if found is not None else root)}


def layout(path):
    """Param field names of an ER WitchyBND XML."""
    return {f.get("name") for f in ET.parse(path).getroot().find("fields")}


def fnv(name):
    h = 2166136261
    for c in name.lower().encode():
        h = ((h * 16777619) & 0xffffffff) ^ c
    return h


def bank_events(path):
    """Wwise event ids (HIRC type 4) of a bank."""
    if not path.exists():
        return set()
    b, o, out = path.read_bytes(), 0, set()
    while o + 8 <= len(b):
        tag, n = b[o:o + 4], struct.unpack_from("<I", b, o + 4)[0]
        if tag == b"HIRC":
            p = o + 12
            for _ in range(struct.unpack_from("<I", b, o + 8)[0]):
                t, sz, i = struct.unpack_from("<BII", b, p)
                if t == 4:
                    out.add(i)
                p += 5 + sz
        o += 8 + n
    return out


def lua_functions(text):
    """name -> body of every top-level function, in both forms the decompiler writes."""
    funcs, name, body, pending = {}, None, [], None
    for line in text.split("\n"):
        if name is None:
            if m := re.match(r"function (\w+)\(", line):
                name, body = m.group(1), []
            elif line.startswith("f0_local0 = function ("):
                name, body = "f0_local0", []
            elif pending is not None and (m := re.fullmatch(r"(\w+) = f0_local0", line)):
                funcs[m.group(1)] = pending
                pending = None
        elif line == "end":
            if name == "f0_local0":
                pending = "\n".join(body)
            else:
                funcs[name] = "\n".join(body)
            name = None
        else:
            body.append(line)
    return funcs


def hero_blocks(body, const):
    """Text inside `if ... HERO_X` branches of a function shared between heroes."""
    lines, out, i = body.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        if re.search(rf"== HERO_{const}\b", line):
            indent = len(line) - len(line.lstrip())
            i += 1
            while i < len(lines) and not (len(lines[i]) - len(lines[i].lstrip()) == indent and
                                          re.match(r"\s*(else|elseif|end)\b", lines[i])):
                out.append(lines[i])
                i += 1
        i += 1
    return "\n".join(out)


class Clips:
    """group -> clip id -> file, over the unpacked animation archives of one game; compendium hashes."""

    def __init__(self, dirs):
        self.files = collections.defaultdict(dict)
        self.compendiums = {}
        for d in dirs:
            for f in d.rglob("*"):
                if m := re.fullmatch(r"a(\d{3})_(\d{6})\.hkx", f.name):
                    self.files[int(m.group(1))].setdefault(int(m.group(2)), f)
                elif f.suffix == ".compendium":
                    self.compendiums[f.name.lower() + "@" + d.name] = f.read_bytes()


def graph_index(path):
    nodes = json.load(open(path))
    parents = collections.defaultdict(list)
    for i, n in nodes.items():
        for k in n["kids"]:
            parents[k].append(i)
    states = {i for i, n in nodes.items() if n["type"] == "hkbStateMachine::StateInfo"}
    return nodes, parents, states


def state_of_clip(cid, nodes, parents, states):
    """Nearest states above a graph node."""
    seen, todo, out = {cid}, [cid], set()
    while todo:
        for p in parents[todo.pop()]:
            if p in seen:
                continue
            seen.add(p)
            if p in states:
                out.add(p)
            else:
                todo.append(p)
    return out


def descendants(sid, nodes):
    seen, todo = {sid}, [sid]
    while todo:
        for k in nodes.get(todo.pop(), {"kids": []})["kids"]:
            if k not in seen:
                seen.add(k)
                todo.append(k)
    return seen


def main(root, out):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    w = root / "work"
    nr_reg, er_reg = w / "s1/nr/regulation-bin", w / "s1/er/regulation-bin"
    tool = root / "work/bin/flvertool/flvertool.exe"
    scratch = w / "report"
    scratch.mkdir(exist_ok=True)

    print("params")
    hero = rows(nr_reg / "HeroParam.param.xml")
    init = rows(nr_reg / "CharaInitParam.param.xml")
    weapons = rows(nr_reg / "EquipParamWeapon.param.xml")
    beh = rows(nr_reg / "BehaviorParam_PC.param.xml")
    atk = rows(nr_reg / "AtkParam_Pc.param.xml")
    sp = rows(nr_reg / "SpEffectParam.param.xml")
    bul = rows(nr_reg / "Bullet.dump.xml")
    er_beh, er_atk, er_sp, er_bul = (rows(er_reg / f"{n}.param.xml") for n in ("BehaviorParam_PC", "AtkParam_Pc", "SpEffectParam", "Bullet"))
    er_state_infos = {r.get("stateInfo") for r in er_sp.values()}
    sp_fields, bul_fields, atk_fields = (layout(er_reg / f"{n}.param.xml") for n in ("SpEffectParam", "Bullet", "AtkParam_Pc"))
    names = {}
    for f in (w / "s2/nr-msg").rglob("*.fmg.xml"):
        for t in ET.parse(f).getroot().find("entries"):
            if t.text and t.text != "%null%":
                names.setdefault(t.get("id"), t.text)

    print("TAE")
    nr_tae = w / "s3/anim/nr_c0000-anibnd-dcx-wanibnd/Target/INTERROOT_win64/chr/c0000/tae"
    er_tae = w / "s3/anim/er_c0000-anibnd-dcx-wanibnd/INTERROOT_win64/chr/c0000/tae"
    if not er_tae.exists():
        er_tae = next(iter((w / "s3/anim/er_c0000-anibnd-dcx-wanibnd").rglob("tae")))
    tsv = {}
    for label, d in (("nr", nr_tae), ("er", er_tae)):
        path = scratch / f"{label}_tae.tsv"
        if not path.exists():
            subprocess.run([str(tool), "taetsv", str(path.resolve()), str(d.resolve())], check=True)
        table = collections.defaultdict(lambda: collections.defaultdict(list))
        with open(path) as fh:
            for line in fh:
                g, a, t, s, e, h = line.rstrip("\n").split("\t")
                if t == "-1":
                    table[int(g)][int(a)]
                else:
                    table[int(g)][int(a)].append((int(t), float(s), float(e), h))
        tsv[label] = table
    er_types = {e[0] for g in tsv["er"].values() for a in g.values() for e in a}

    print("clips")
    nr_clips = Clips([d for s in ("s3/anim", "s4/anim") for d in (w / s).glob("nr_*-wanibnd")])
    er_clips = Clips([d for s in ("s3/anim", "s4/anim") for d in (w / s).glob("er_*-wanibnd")])
    er_compendiums = set(map(hash, er_clips.compendiums.values()))
    compendium_ok = {k.split("@")[1]: hash(v) in er_compendiums for k, v in nr_clips.compendiums.items()}

    print("graph")
    nodes, parents, states = graph_index(w / "s3/beh/nr_graph.json")
    er_nodes, _, er_states = graph_index(w / "s3/beh/er_graph.json")
    er_state_names = {er_nodes[s].get("name") for s in er_states}
    er_node_types = {n["type"] for n in er_nodes.values()}
    clip_node = collections.defaultdict(list)
    for i, n in nodes.items():
        if n["type"] == "hkbClipGenerator" and (m := re.match(r"a(\d{3})_(\d{6})", n.get("name", ""))):
            clip_node[(int(m.group(1)), int(m.group(2)))].append(i)
    state_by_name = collections.defaultdict(list)
    for s in states:
        state_by_name[nodes[s].get("name")].append(s)

    print("script")
    nr_lua = (w / "s3/hks/nr_c0000.lua").read_text(encoding="utf-8-sig")
    er_lua = (w / "s3/hks/er_c0000.lua").read_text(encoding="utf-8-sig")
    funcs = lua_functions(nr_lua)
    er_funcs = lua_functions(er_lua)
    env_re, act_re = re.compile(r"\benv\((\d+)"), re.compile(r"\bact\((\d+)")
    er_env, er_act = set(map(int, env_re.findall(er_lua))), set(map(int, act_re.findall(er_lua)))
    callers = collections.defaultdict(set)
    for f, body in funcs.items():
        for c in set(re.findall(r"\b([A-Z]\w+)\(", body)):
            if c in funcs and c != f:
                callers[c].add(f)

    print("effects, sounds")
    fx_dir = {g: w / f"s4/sfx/{g}_commoneffects-ffxbnd-dcx-wffxbnd" for g in ("nr", "er")}
    fx_names = {g: {f.stem for f in (d / "effect").glob("*.fxr")} for g, d in fx_dir.items()}
    tex_names = {g: {f.stem.lower() for f in (d / "tex").glob("*")} for g, d in fx_dir.items()}
    model_names = {g: {f.stem.lower() for f in (d / "model").glob("*")} for g, d in fx_dir.items()}
    er_main = bank_events(w / "er-game/sd/enus/cs_main.bnk") | bank_events(w / "er-game/sd/cs_main.bnk")
    nr_main = bank_events(w / "nr-game/sd/cs_main.bnk") | bank_events(w / "nr-game/sd/enus/cs_main.bnk")
    parts = {f.name.split(".")[0] for f in (w / "nr-game/parts").glob("wp_a_50*.partsbnd.dcx") if re.fullmatch(r"wp_a_\d+", f.name.split(".")[0])}

    def fx_closure(seeds):
        seen, todo, tex, models = set(), [i for i in seeds if f"f{i:09d}" in fx_names["nr"]], set(), set()
        in_er = set()
        while todo:
            i = todo.pop()
            name = f"f{i:09d}"
            if i in seen:
                continue
            if name in fx_names["er"]:
                in_er.add(i)
                continue
            seen.add(i)
            b = (fx_dir["nr"] / "effect" / f"{name}.fxr").read_bytes()
            for k in range(0, len(b) - 3, 4):
                v = struct.unpack_from("<i", b, k)[0]
                if 10000 <= v < 1_000_000_000 and f"f{v:09d}" in fx_names["nr"] and v not in seen:
                    todo.append(v)
            res = fx_dir["nr"] / "ResourceList" / f"{name}.ffxreslist"
            if res.exists():
                for r in res.read_bytes().decode("ascii", "ignore").split("\n"):
                    stem = Path(r.strip().replace("\\", "/")).stem.lower()
                    if stem in tex_names["nr"] and stem not in tex_names["er"]:
                        tex.add(stem)
                    if stem in model_names["nr"] and stem not in model_names["er"]:
                        models.add(stem)
        return seen, in_er, tex, models

    summary = []
    report = {}
    for hid in sorted(map(int, hero)):
        h = hero[str(hid)]
        idx = hid - 1
        const = HERO_TYPES[hid]
        group = 900 + idx
        name = names.get(h.get("characterNameId"), f"hero {hid}") or f"hero {hid}"
        print(name)
        # EquipParamWeapon rows on the hero's model range: starting weapons have ids ending in 750000 (Wylder's 3750000
        # and 30750000); 60xx0000 rows are the skill and ultimate devices, which the engine shows.
        model_range = range(5000 + idx * 10, 5010 + idx * 10)
        on_range = [r for r in weapons.values() if int(r.get("equipModelId", "0")) in model_range]
        hero_weapons = sorted((r for r in on_range if int(r["id"]) % 1_000_000 == 750000), key=lambda r: int(r["id"]))
        devices = sorted((r for r in on_range if 60_000_000 <= int(r["id"]) < 61_000_000), key=lambda r: int(r["id"]))
        hero_parts = sorted(p for p in parts if int(p[5:]) in model_range)
        vars_ = set()
        cats = set()
        for r in hero_weapons:
            v, hv = int(r.get("behaviorVariationId", "0")), int(r.get("heroBehaviorVariationID", "0"))
            vars_ |= {x for x in (v, hv) if x > 0}
            cats.add(int(r.get("wepmotionCategory", "0")))
            override = int(r.get("heroMovesetOverrideID", "0"))
            if override > 0:
                cats.add(override)  # the hero's own swings, e.g. Wylder's a270 over the greatsword's a025
        # Clips: the hero group, plus the motion groups of the starting weapons.
        own = nr_clips.files.get(group, {})
        own_tae = tsv["nr"].get(group, {})
        ids = set(own) | set(own_tae)
        event_rows = [(group, a, e) for a in ids for e in own_tae.get(a, [])]
        weapon_clips = {"same": 0, "changed": 0, "nr_only": 0}
        for c in cats:
            for a, f in nr_clips.files.get(c, {}).items():
                other = er_clips.files.get(c, {}).get(a)
                key = "nr_only" if other is None else "same" if other.read_bytes() == f.read_bytes() else "changed"
                weapon_clips[key] += 1
            for a, ev in tsv["nr"].get(c, {}).items():
                event_rows += [(c, a, e) for e in ev]
        # Archives the hero's own clips come from; a compendium ER lacks has to ship too.
        archives = {next(p for p in f.parts if p.endswith("-wanibnd")) for f in own.values()}
        bad_comp = sorted(a for a in archives if not compendium_ok.get(a, False))

        # Graph: states holding the hero's clips, and those the hero script fires.
        hero_states = set()
        for a in own:
            for c in clip_node.get((group, a), []):
                hero_states |= state_of_clip(c, nodes, parents, states)
        # Script: functions only this hero runs, then branches inside shared ones.
        guarded = {f for f, b in funcs.items() if re.search(rf"env\(371\) ~= HERO_{const}\b.*\n\s*return", b)}
        state_funcs = set()
        for s in hero_states:
            sn = nodes[s].get("name", "")
            state_funcs |= {f for f in funcs if f == sn or f.startswith(sn + "_on")}
        hero_funcs = guarded | state_funcs
        grew = True
        while grew:
            grew = False
            for f in list(hero_funcs):
                for c in set(re.findall(r"\b([A-Z]\w+)\(", funcs[f])):
                    if c in funcs and c not in hero_funcs and c not in er_funcs and callers[c] <= hero_funcs:
                        hero_funcs.add(c)
                        grew = True
        text = "\n".join(funcs[f] for f in hero_funcs)
        branch = "\n".join(hero_blocks(b, const) for b in funcs.values() if f"HERO_{const}" in b)
        script = text + "\n" + branch
        fired = set(re.findall(r'"(W_\w+)"', script))
        for ev in fired:
            for s in state_by_name.get(ev[2:], []):
                hero_states.add(s)
        state_names = sorted({nodes[s].get("name") for s in hero_states})
        new_states = [s for s in state_names if s not in er_state_names]
        node_types = collections.Counter()
        for s in hero_states:
            if nodes[s].get("name") in er_state_names:
                continue
            for d in descendants(s, nodes):
                node_types[nodes[d]["type"]] += 1
        nr_only_nodes = sorted(t for t in node_types if t not in er_node_types)
        env_ids = sorted(set(map(int, env_re.findall(script))) - er_env)
        act_ids = sorted(set(map(int, act_re.findall(script))) - er_act)
        script_sp = sorted(set(map(int, re.findall(r"env\(1116, (\d+)\)", script))))
        new_funcs = sorted(f for f in hero_funcs if f not in er_funcs)

        # TAE events of the hero's own clips, and what they name.
        types = collections.Counter(e[0] for _, _, e in event_rows)
        engine = {t: n for t, n in types.items() if t not in er_types or t in TAE_ENGINE}
        own_types = collections.Counter(e[0] for a in ids for e in own_tae.get(a, []))
        sources = collections.Counter()
        judges = set()
        sound_ids = set()
        tae_sp = set()
        all_ints = set()
        for _, _, e in event_rows:
            v = ints(e[3])
            all_ints |= set(v)
            if e[0] in (TAE_ATTACK, TAE_BULLET) and len(v) > 2:
                judges.add(v[2])
                b = bytes.fromhex(e[3])
                if len(b) > 13:
                    sources[b[13]] += 1
            elif e[0] == TAE_SOUND and len(v) > 1:
                sound_ids.add((v[0], v[1]))
            elif e[0] in TAE_SPEFFECTS and v and v[0] > 0:
                tae_sp.add(v[0])
        # Behaviour rows: id = prefix * 1e6 + variation * 1000 + judge. Judges 1000 and up land on variation + n.
        by_key = collections.defaultdict(list)
        for i, r in beh.items():
            by_key[int(i) % 1_000_000].append(r)
        resolved, unresolved = [], []
        for j in sorted(judges):
            hits = [r for v in vars_ for r in by_key.get(v * 1000 + j, [])]
            (resolved if hits else unresolved).append(j)
            resolved_rows = hits
            for r in resolved_rows:
                r.setdefault("_hero", "")
        rows_used = [r for j in resolved for v in vars_ for r in by_key.get(v * 1000 + j, [])]
        atks, bullets = set(), set()
        for r in rows_used:
            (bullets if r.get("refType", "0") == "1" else atks).add(int(r.get("refId", "0")))
        speffects, sfx = set(tae_sp) | {s for s in script_sp if str(s) in sp}, set()
        todo, done = list(bullets - {0}), set()
        while todo:
            b = todo.pop()
            if b in done or str(b) not in bul:
                continue
            done.add(b)
            r = bul[str(b)]
            todo += [int(r[f]) for f in ("HitBulletID", "intervalCreateBulletId") if int(r.get(f, "-1")) > 0]
            if int(r.get("atkId_Bullet", "-1")) > 0:
                atks.add(int(r["atkId_Bullet"]))
            speffects |= {int(v) for k, v in r.items() if k.lower().startswith("speffectid") and int(v) > 0}
            sfx |= {int(v) for k, v in r.items() if k.lower().startswith("sfxid") and int(v) > 0}
        atks.discard(0)
        todo, sp_done = list(speffects), set()
        while todo:
            s = todo.pop()
            if s in sp_done or str(s) not in sp:
                continue
            sp_done.add(s)
            r = sp[str(s)]
            todo += [int(r[f]) for f in ("cycleOccurrenceSpEffectId", "replaceSpEffectId", "spEffectIdOnHit") if int(r.get(f, "-1")) > 0]
        sp_collide = sorted(s for s in sp_done if str(s) in er_sp and any(er_sp[str(s)].get(k) != v for k, v in sp[str(s)].items() if k in sp_fields and k != "paramdexName"))
        sp_new_state = sorted(s for s in sp_done if sp[str(s)].get("stateInfo") not in er_state_infos)
        bul_collide = sorted(b for b in done if str(b) in er_bul)
        atk_missing = sorted(a for a in atks if str(a) not in atk)
        lost = collections.Counter()
        for table, ids_, fields, master in ((bul, done, bul_fields, "bullet"), (atk, atks, atk_fields, "attack"), (sp, sp_done, sp_fields, "SpEffect")):
            for i in ids_:
                for k, v in table.get(str(i), {}).items():
                    if k not in fields and k not in ("id", "paramdexName", "_hero") and v not in ("0", "-1", "0.0", "1", "1.0"):
                        lost[f"{master}.{k}"] += 1

        fx, fx_in_er, tex, models = fx_closure(sorted(sfx | {i for i in all_ints if 10000 <= i < 1_000_000_000}))

        bank = bank_events(w / f"nr-game/sd/hero{hid:02d}.bnk")
        snd = collections.Counter()
        for kind, sid in sound_ids:
            letter = SOUND_LETTERS.get(kind)
            if letter is None or sid <= 0:
                snd["other kinds (ids unmapped)"] += 1
                continue
            e = fnv(f"Play_{letter}{sid:09d}")
            snd["in ER's cs_main" if e in er_main else f"in hero{hid:02d}.bnk" if e in bank else "in NR's cs_main" if e in nr_main else "not found"] += 1

        # Modules: NR-only env (unknown ones flagged), engine-only events, engine-driven models.
        env_rows = [(e, *ENV_KNOWN.get(e, ("unknown", "read in NR first"))) for e in env_ids]
        extra_parts = [f"wp_a_{r['equipModelId']} ({r['id']})" for r in devices]
        counts = dict(
            clips_own=len(own), clips_weapon=sum(weapon_clips.values()), tae_events=len(event_rows),
            behaviours=len(rows_used), bullets=len(done), attacks=len(atks), speffects=len(sp_done), effects=len(fx),
            new_states=len(new_states))
        auto = sum(counts.values())
        check = len(sp_collide) + len(sp_new_state) + len(bul_collide) + len(unresolved) + len(atk_missing) + len(bad_comp) + sum(sources[s] for s in (3, 4))
        unknown_env = [e for e, _, st in env_rows if st == "read in NR first"]
        report[hid] = dict(name=name, type=const, counts=counts, check=check, env_only=env_ids, unknown_env=unknown_env, act_only=act_ids,
                           engine_tae=sorted(engine), new_states=new_states, unresolved_judges=unresolved, weapon_clips=weapon_clips,
                           sound=dict(snd), lost_fields=dict(lost), models=extra_parts, textures=len(tex), fx_models=sorted(models))

        lines = [f"# {name} (hero {hid}, HERO_{const})", "",
                 "Evidence: **[Source]** only: read from the unpacked files of the installed games; nothing here was run.", "",
                 f"- Skill: {names.get(h.get('characterSkillTitleId'), '?')}; cooldown {h.get('characterAbilityCooldown')} s",
                 f"- Ultimate: {names.get(h.get('ultimateArtTitleId'), '?')}; gauge row value {h.get('ultimateArtCharge')}",
                 f"- Passive: {names.get(h.get('passiveAbilityTitleId'), '?')}",
                 f"- Clip group a{group}, weapon motion groups {sorted(cats)}, behaviour variations {sorted(vars_)}",
                 f"- Starting weapons: {[int(r['id']) for r in hero_weapons][:8]}; hero parts {hero_parts}", "",
                 "## Data existing tools carry (auto)", "",
                 "| Item | Count |", "|---|---|"]
        lines += [f"| Own clips (a{group}) | {counts['clips_own']} |",
                  f"| Weapon clips | {counts['clips_weapon']}: {weapon_clips['same']} same as ER, {weapon_clips['changed']} changed, {weapon_clips['nr_only']} NR-only |",
                  f"| TAE events on those | {counts['tae_events']} |", f"| Behaviour rows | {counts['behaviours']} |", f"| Bullets | {counts['bullets']} |",
                  f"| Attack rows | {counts['attacks']} |", f"| SpEffects | {counts['speffects']} |",
                  f"| Effects to convert (FXR, with nested) | {counts['effects']}, {len(fx_in_er)} more shared with ER |",
                  f"| Effect textures ER lacks | {len(tex)} |", f"| New graph states | {counts['new_states']} |", ""]
        lines += ["## Needs a look (check)", ""]
        lines += [f"- SpEffect ids colliding with different ER rows: {sp_collide or 'none'}",
                  f"- SpEffects whose condition (stateInfo) ER's data never uses: {sp_new_state or 'none'}",
                  f"- Bullet ids colliding: {bul_collide or 'none'}",
                  f"- TAE judges with no behaviour row found: {unresolved or 'none'}",
                  f"- Attack rows missing in NR: {atk_missing or 'none'}",
                  f"- Attack/bullet events on source byte: {dict(sources)} (3 and 4 don't exist in ER; 0 works after the variation remap)",
                  f"- Archives whose compendium ER lacks: {bad_comp or 'none'}",
                  f"- NR-only param fields set on these rows (lost in ER): {dict(lost) or 'none'}",
                  f"- Graph node types ER lacks: {nr_only_nodes or 'none'}",
                  f"- Sounds used by the hero TAE: {dict(snd)}. Merged banks are rejected so far; see NOTES.",
                  f"- FXR models ER lacks (NR FLVER): {sorted(models) or 'none'}", ""]
        lines += ["## Needs native code (module)", "", "| NR-only env | Meaning | State |", "|---|---|---|"]
        lines += [f"| {e} | {m} | {st} |" for e, m, st in env_rows] or ["| none | | |"]
        lines += ["", f"- NR-only `act` ids: {act_ids or 'none'}",
                  f"- TAE types ER's data never uses: {[f'{t} x{n} ({TAE_ENGINE.get(t, chr(63))})' for t, n in sorted(engine.items())] or 'none'}",
                  f"- Skill and ultimate devices (weapon rows 60xx0000), probably engine-driven: {extra_parts or 'none'}", "",
                  "## Graph and script", "",
                  f"New states: {', '.join(new_states) or 'none'}", "",
                  f"States shared with ER: {', '.join(s for s in state_names if s not in new_states) or 'none'}", "",
                  f"NR-only script functions to port by name ({len(new_funcs)}): {', '.join(new_funcs) or 'none'}", "",
                  f"Events the hero script fires: {', '.join(sorted(fired)) or 'none'}", ""]
        (out / f"{re.sub(r'\W+', '_', name).lower()}.md").write_text("\n".join(lines), encoding="utf-8")
        summary.append((hid, name, const, counts, check, env_ids, unknown_env, act_ids, engine, extra_parts, new_states, snd))

    head = ["# Hero port report: summary", "",
            "Generated by `src/hero_report.py` from the installed games' files. **[Source]**: nothing here was run in a game.",
            "`auto` counts data items existing tools carry. It sizes the data job only: one module can outweigh every other count.", "",
            "| Hero | Type | auto items | check | NR-only env (unknown) | NR-only act | Engine TAE types | Skill objects | New states |",
            "|---|---|---|---|---|---|---|---|---|"]
    for hid, name, const, counts, check, env_ids, unknown_env, act_ids, engine, extra_parts, new_states, snd in summary:
        head.append(f"| {name} | {const} | {sum(counts.values())} | {check} | {len(env_ids)} ({len(unknown_env)}) | {len(act_ids)} | {sorted(engine)} | {len(extra_parts)} | {len(new_states)} |")
    (out / "summary.md").write_text("\n".join(head) + "\n", encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:3])
