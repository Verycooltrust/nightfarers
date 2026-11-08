"""Stages 1-4: add Wylder's gear, starting class, movement SpEffects and greatsword moveset rows to Elden Ring's params and texts.

Reads WitchyBND XML unpacked from the user's own game files (never shipped) and writes edited copies:
  python build_wylder_params.py <pristine regulation-bin dir> <out regulation-bin dir>
      <pristine item msgbnd dir> <out item msgbnd dir> <pristine menu msgbnd dir> <out menu msgbnd dir>
      <pristine Nightreign regulation-bin dir>

Only adds rows; no existing row is changed. In the menu texts it fills one empty (%null%) class slot.
"""
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hero  # noqa: E402

# Hero data: heroes/<name>.toml (src/hero.py).
HERO = hero.load()
ARMOR = HERO["armor"]
WEAPONS = HERO["weapon"]
CLASS = HERO["class"]
ABSORP = HERO["absorp"]
MOVESET, SKILL = HERO["moveset"], HERO["skill"]
# Stage 3 SpEffects. Nightreign's sprint markers (set by its TAE, read by c0000.hks) are moved to 9102xxx because
# Elden Ring uses 1020xx for physick tears (build_hks.py and the TAE graft use the same map). Rows are rebuilt from
# Elden Ring's 100002 "[HKS] Dashing" (identical in both games) plus every field where NR's row differs from NR 100002.
SPEFFECT_BASE = 100002
SPRINT_SPEFFECTS = {102000: 9102000, 102001: 9102001, 102010: 9102010, 102022: 9102022, 102030: 9102030}
NIGHTFARER_SPEFFECT = 9102900  # resident on nightfarer armor; enables Surge Sprint in c0000.hks
# BehaviorParam_PC id = prefix * 1e6 + variation * 1000 + judge. NR_VARIATIONS: the hero variation (last) wins.
NR_VARIATIONS, VARIATION, ATK_OFFSET = tuple(MOVESET["nr_variations"]), MOVESET["variation"], MOVESET["attack_offset"]
SKILL_VARIATION_OFFSET = SKILL["variation_offset"]
BULLET_REMAP = dict(map(tuple, SKILL["bullet_remap"]))
BULLET_REFS = ("HitBulletID", "intervalCreateBulletId")
SPEFFECT_REFS = ("cycleOccurrenceSpEffectId", "replaceSpEffectId", "spEffectIdOnHit")
ATK_OVERRIDES = {o["id"]: o["fields"] for o in SKILL["attack_overrides"]}
CRIT_MARK_NR = 350510
CRIT_MARKS_ER = {350510: 350501, 350610: 350601}
BLADE_OF_MERCY = 20382301
BULLET_OVERRIDES = {o["id"]: o["fields"] for o in SKILL["bullet_overrides"]}
FLAT_ATTACK_TEMPLATE = 878800000  # NR's claw hit


def load(path):
    tree = ET.parse(path)
    rows = tree.getroot().find("rows")
    return tree, rows, {r.get("id"): r for r in rows}


def add_row(rows, by_id, new_id, template_id, **overrides):
    if str(new_id) in by_id:
        raise SystemExit(f"row {new_id} already exists")
    row = ET.Element("row", dict(by_id[str(template_id)].attrib))
    row.set("id", str(new_id))
    for k, v in overrides.items():
        row.set(k, str(v))
    # keep ids sorted: insert before the first larger id
    idx = next((i for i, r in enumerate(rows) if int(r.get("id")) > new_id), len(rows))
    rows.insert(idx, row)
    by_id[str(new_id)] = row


def add_nr_row(rows, by_id, fields, new_id, attrib, **overrides):
    """Add a row from a Nightreign row: its (non-default) fields that Elden Ring's layout has."""
    if str(new_id) in by_id:
        raise SystemExit(f"row {new_id} already exists")
    row = ET.Element("row", {k: v for k, v in attrib.items() if k in fields})
    row.set("id", str(new_id))
    for k, v in overrides.items():
        row.set(k, str(v))
    idx = next((i for i, r in enumerate(rows) if int(r.get("id")) > new_id), len(rows))
    rows.insert(idx, row)
    by_id[str(new_id)] = row


def add_wylder_moveset(reg_out, nr_reg):
    _, _, nr_beh = load(nr_reg / "BehaviorParam_PC.param.xml")
    _, _, nr_atk = load(nr_reg / "AtkParam_Pc.param.xml")
    _, _, nr_sp = load(nr_reg / "SpEffectParam.param.xml")
    nr_bul = {r.get("id"): r for r in ET.parse(nr_reg / "Bullet.dump.xml").getroot()}
    merged = {}  # (prefix, judge, Wylder variation) -> NR row; the hero variation (last) wins
    for nr_vars, var in ((NR_VARIATIONS, VARIATION),
                         ([v + SKILL_VARIATION_OFFSET for v in NR_VARIATIONS], VARIATION + SKILL_VARIATION_OFFSET)):
        for nr_var in nr_vars:
            for r in nr_beh.values():
                if r.get("variationId") == str(nr_var):
                    merged[(int(r.get("id")) // 1_000_000, int(r.get("behaviorJudgeId", "0")), var)] = r
    # The ultimate's rows: NR judge 7000 + n -> NR row base + n, as weapon-art rows 900000xxx (new judge 9xxx).
    ult = HERO["ultimate"]
    for nr_judge, judge in ult["judge_map"]:
        merged[(900, judge - 9000, 0)] = nr_beh[str(ult["nr_row_base"] + nr_judge - 7000)]
    atk_ids, bullets, speffects = set(), set(), set(SKILL["tae_speffects"]) | set(ult["tae_speffects"]) | set(HERO["passive"]["speffects"])
    sp_overrides = {o["id"]: o["fields"] for o in HERO["passive"]["speffect_overrides"]}
    path = reg_out / "BehaviorParam_PC.param.xml"
    tree, rows, by_id = load(path)
    fields = {k for r in rows for k in r.attrib}
    for (prefix, judge, var), r in sorted(merged.items()):
        # NR's skill-weapon behaviours (prefix 900) resolve through Wylder's sword in Elden Ring (prefix 100); the
        # claw's AttackBehavior events get source 0 instead of NR's 3 (build_movement.sh taesetsource).
        if var == VARIATION + SKILL_VARIATION_OFFSET and prefix == 900:
            prefix = 100
        ref = int(r.get("refId"))
        if r.get("refType", "0") == "1":
            bullets.add(ref)
            ref = BULLET_REMAP.get(ref, ref)
        else:
            atk_ids.add(ref)
            ref += ATK_OFFSET
        add_nr_row(rows, by_id, fields, prefix * 1_000_000 + var * 1000 + judge, r.attrib, variationId=var,
                   refId=ref, paramdexName=f"[Nightfarers] Wylder NR {r.get('id')}")
    save(tree, path)
    todo, done = list(bullets), set()  # bullets and the bullets they spawn
    while todo:
        b = todo.pop()
        if b in done or str(b) not in nr_bul:
            continue
        done.add(b)
        r = nr_bul[str(b)]
        todo += [int(r.get(f)) for f in BULLET_REFS if int(r.get(f, "-1")) > 0]
        if int(r.get("atkId_Bullet", "-1")) > 0:
            atk_ids.add(int(r.get("atkId_Bullet")))
        speffects |= {int(v) for k, v in r.attrib.items() if k.lower().startswith("speffectid") and int(v) > 0}
    path = reg_out / "Bullet.param.xml"
    tree, rows, by_id = load(path)
    fields = {k for r in rows for k in r.attrib}
    for hit in ult["fire_hits"]:
        add_nr_row(rows, by_id, fields, hit["bullet"], nr_bul[str(hit["template_bullet"])], atkId_Bullet=ATK_OFFSET + hit["attack"],
                   sfxId_Bullet=-1, HitBulletID=-1, paramdexName=f"[Nightfarers] Wylder Stake fire hit")
    for b in sorted(done):
        r = nr_bul[str(b)]
        refs = {f: BULLET_REMAP.get(int(r.get(f)), int(r.get(f))) for f in BULLET_REFS if f in r.attrib}
        atk = int(r.get("atkId_Bullet", "-1"))
        add_nr_row(rows, by_id, fields, BULLET_REMAP.get(b, b), r.attrib, paramdexName=f"[Nightfarers] Wylder NR {b}",
                   atkId_Bullet=ATK_OFFSET + atk if atk > 0 else atk, **{**refs, **BULLET_OVERRIDES.get(b, {})})
    save(tree, path)
    path = reg_out / "AtkParam_Pc.param.xml"
    tree, rows, by_id = load(path)
    fields = {k for r in rows for k in r.attrib}
    for i in sorted(atk_ids):
        a = nr_atk[str(i)].attrib
        crit = {}
        # NR's crit rows mark the hit with 350510/350610; ER's talismans listen for 350501 (Assassin's Crimson Dagger),
        # 350601 (Cerulean Dagger) and 20382301 (Blade of Mercy), as on ER's greatsword crits 300500.. [Source].
        slots = [f"spEffectId{n}" for n in range(5)]
        if any(a.get(s) == str(CRIT_MARK_NR) for s in slots):
            crit = {s: CRIT_MARKS_ER.get(int(a.get(s, "-1")), int(a.get(s, "-1"))) for s in slots}
            free = [s for s in slots if crit[s] <= 0]
            if free and BLADE_OF_MERCY not in crit.values():
                crit[free[0]] = BLADE_OF_MERCY
        add_nr_row(rows, by_id, fields, ATK_OFFSET + i, a,
                   paramdexName=f"[Nightfarers] Wylder NR {i}", **{**crit, **ATK_OVERRIDES.get(i, {})})
    # Fire-only hits: the claw's working flat attack row, no magic, no stagger of their own, no status.
    no_status = {f"spEffectId{i}": -1 for i in range(5) if f"spEffectId{i}" in fields}
    for hit in ult["fire_hits"]:
        add_nr_row(rows, by_id, fields, ATK_OFFSET + hit["attack"], nr_atk[str(FLAT_ATTACK_TEMPLATE)].attrib, atkMag=0,
                   atkFire=hit["fire"], atkStam=0, atkSuperArmor=0, dmgLevel=0, knockbackDist=0, **no_status,
                   paramdexName=f"[Nightfarers] Wylder Stake fire {hit['fire']}")
    save(tree, path)
    path = reg_out / "SpEffectParam.param.xml"
    tree, rows, by_id = load(path)
    fields = {k for r in rows for k in r.attrib}
    todo, added = list(speffects), []
    while todo:
        s = todo.pop()
        if str(s) in by_id or str(s) not in nr_sp:
            continue
        r = nr_sp[str(s)]
        add_nr_row(rows, by_id, fields, s, r.attrib, paramdexName=f"[Nightfarers] Wylder NR {s}", **sp_overrides.get(s, {}))
        added.append(s)
        todo += [int(r.get(f)) for f in SPEFFECT_REFS if int(r.get(f, "-1")) > 0]
    save(tree, path)
    print(f"Wylder moveset + Claw Shot: {len(merged)} behaviours, {len(done)} bullets, {len(atk_ids)} attacks, "
          f"{len(added)} SpEffects")


def save(tree, path):
    tree.write(path, encoding="utf-8", xml_declaration=True)


def add_texts(fmg_path, entries):
    tree = ET.parse(fmg_path)
    parent = tree.getroot().find("entries")
    existing = {t.get("id") for t in parent}
    for text_id, text in entries:
        if str(text_id) in existing:
            raise SystemExit(f"text {text_id} already exists in {fmg_path}")
        el = ET.SubElement(parent, "text", {"id": str(text_id)})
        el.text = text
    tree.write(fmg_path, encoding="utf-8", xml_declaration=True)


def fill_text(fmg_path, text_id, text):
    """Set an existing empty (%null%) text slot."""
    tree = ET.parse(fmg_path)
    el = next(t for t in tree.getroot().find("entries") if t.get("id") == str(text_id))
    if el.text != "%null%":
        raise SystemExit(f"text {text_id} in {fmg_path} is not empty: {el.text!r}")
    el.text = text
    tree.write(fmg_path, encoding="utf-8", xml_declaration=True)


def main(reg_src, reg_out, msg_src, msg_out, menu_src, menu_out, nr_reg):
    reg_src, reg_out, msg_src, msg_out, menu_src, menu_out, nr_reg = map(
        Path, (reg_src, reg_out, msg_src, msg_out, menu_src, menu_out, nr_reg))
    name = HERO["hero"]["name"]
    for src, out in ((reg_src, reg_out), (msg_src, msg_out), (menu_src, menu_out)):
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(src, out)

    path = reg_out / "EquipParamProtector.param.xml"
    tree, rows, by_id = load(path)
    for a in ARMOR:
        # equipModelGender (enum EQUIP_MODEL_GENDER): 0 None = no model drawn, 4 = _m/_f file by body type (vanilla
        # default), 1 Male = the _m file for everyone. Nightreign has male files only.
        extra = {"residentSpEffectId": NIGHTFARER_SPEFFECT} if a.get("nightfarer_marker") else {}
        add_row(rows, by_id, a["id"], a["template"], paramdexName=a["name"], equipModelId=a["model"], equipModelGender=1, **extra)
    save(tree, path)

    path = reg_out / "SpEffectParam.param.xml"
    tree, rows, by_id = load(path)
    _, _, nr_rows = load(nr_reg / "SpEffectParam.param.xml")
    nr_base = nr_rows[str(SPEFFECT_BASE)].attrib
    for nr_id, new_id in SPRINT_SPEFFECTS.items():
        diff = {k: v for k, v in nr_rows[str(nr_id)].attrib.items() if k not in ("id", "paramdexName") and nr_base.get(k) != v}
        add_row(rows, by_id, new_id, SPEFFECT_BASE, paramdexName=f"[Nightfarers] NR {nr_id} sprint", **diff)
    add_row(rows, by_id, NIGHTFARER_SPEFFECT, SPEFFECT_BASE, paramdexName="[Nightfarers] Nightfarer movement",
            effectEndurance=-1, stateInfo=266, fallDamageRate=0)  # 266 = NR resident 102401: c0000.hks lands without fall death or damage
    for m in HERO["markers"]:
        add_row(rows, by_id, m["id"], SPEFFECT_BASE, paramdexName=f"[Nightfarers] {m['what']}", effectEndurance=m["seconds"], **({"iconId": m["icon"]} if "icon" in m else {}), **m.get("fields", {}))
    save(tree, path)

    path = reg_out / "EquipParamWeapon.param.xml"
    tree, rows, by_id = load(path)
    # Affinities are their own rows, base id + 100 (Heavy) .. + 1200 (Occult), each with its own scaling and reinforceTypeId.
    # Without them an ash of war's affinity found no row and kept the base scaling (user: Keen showed D -> D).
    weapon_names = []
    for w in WEAPONS:
        tmpl = w["template"]
        tmpl_name = by_id[str(tmpl)].get("paramdexName")
        for k in range(0, 2500, 100):
            src = by_id.get(str(tmpl + k))
            if src is None:
                continue
            origin = {f: w["id"] + k for f, v in src.attrib.items() if f.startswith("originEquipWep") and v == str(tmpl + k)}
            label = src.get("paramdexName").replace(tmpl_name, w["name"])
            add_row(rows, by_id, w["id"] + k, tmpl + k, paramdexName=label, equipModelId=w["model"], **origin, **w["fields"])
            weapon_names.append((w["id"] + k, label))
    save(tree, path)
    add_wylder_moveset(reg_out, nr_reg)

    path = reg_out / "WepAbsorpPosParam.param.xml"
    tree, rows, by_id = load(path)
    add_row(rows, by_id, ABSORP["id"], ABSORP["template"], paramdexName="[Nightfarers] Wylder's Greatsword + claw", **ABSORP["fields"])
    save(tree, path)

    path = reg_out / "CharaInitParam.param.xml"
    tree, rows, by_id = load(path)
    add_row(rows, by_id, CLASS["row"], CLASS["template_class"], paramdexName=f"Class - {name}", **CLASS["fields"])
    for i in range(2):
        add_row(rows, by_id, CLASS["variant"] + i, CLASS["template_variant"] + i, **CLASS["fields"])
    save(tree, path)

    path = reg_out / "BaseChrSelectMenuParam.param.xml"
    tree, rows, by_id = load(path)
    # imageId 18 -> sprite MENU_Ch_13, added by build_wylder_portrait.py.
    add_row(rows, by_id, CLASS["menu_row"], CLASS["template_menu"], paramdexName=name, chrInitParam=CLASS["variant"],
            originChrInitParam=CLASS["row"], textId=CLASS["text"], imageId=CLASS["image_id"])
    save(tree, path)

    # Character creation "Origin" field: rows 1002xx, value = class row - 3000, caption = the class name slot.
    path = reg_out / "CharMakeMenuListItemParam.param.xml"
    tree, rows, by_id = load(path)
    add_row(rows, by_id, 100200 + CLASS["row"] - 3000, CLASS["template_list_item"], paramdexName=f"Class - {name}",
            value=CLASS["row"] - 3000, captionId=CLASS["slot_text"])
    save(tree, path)

    add_texts(msg_out / "ProtectorName.fmg.xml", [(a["id"], a["name"]) for a in ARMOR])
    add_texts(msg_out / "WeaponName.fmg.xml", weapon_names)
    add_texts(menu_out / "GR_MenuText.fmg.xml", [(CLASS["text"], name)])
    fill_text(menu_out / "GR_MenuText.fmg.xml", CLASS["slot_text"], name)
    fill_text(menu_out / "GR_LineHelp.fmg.xml", CLASS["slot_text"], HERO["hero"]["description"])


if __name__ == "__main__":
    main(*sys.argv[1:8])
