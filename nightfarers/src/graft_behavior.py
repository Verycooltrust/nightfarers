"""Stage 3: graft Nightreign behaviour-graph nodes into Elden Ring's player graph (HKLib XML, Havok 2018.1).

  python graft_behavior.py <nr beh.xml> <er beh.xml> <out beh.xml> <out names.json> [<NR clips dir for CLIP_GROUP_CLONES>]

Copies the GRAFTS below (with everything they point to) from NR into ER and remaps what is graph-specific:
  - type ids (matched by name/version/template parameters),
  - variable indices, event ids and animation ids (matched by name; missing ones are appended with NR's info),
  - state ids (copied states get new ids in their ER state machine; transitions are matched by state name),
  - fields ER's type lacks (CustomManualSelectorGenerator.isBasePoseAnim) are dropped.
Transitions into the copied states (wildcard or from same-named states) are copied too. Writes the names it added
to <out names.json> for the action/*nameid.txt lists.
"""
import copy
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hero  # noqa: E402

HERO = hero.load()
# (NR node name, how it is attached in ER): shared nightfarer nodes, then the hero's from its manifest.
GRAFTS = [
    # Surge Sprint: speed level 3 (sprint) and 4 (sprint start) of the upper-body move selector.
    ("SprintFrontWeight_Upper_Selector", ("generator", "MoveFront_Upper_Selector")),
    ("SprintStartFrontWeight_Upper_Selector", ("generator", "MoveFront_Upper_Selector")),
    # The full-body and root-motion move selectors need the sprint branch too (without it index 3 shows dash).
    ("SprintFrontWeight_Selector", ("generator", "MoveFront_Selector")),
    ("SprintFrontWeight_motion_Selector", ("generator", "MoveFront_motion_Selector")),
    ("SprintStart", ("state", "Master_SM")),
    ("Sprint180", ("state", "Stop_SM")),
    ("SprintStop", ("state", "Stop_SM")),
    # Sprint-jump landings; rolls that go on into run / dash / sprint. (The sprint jump itself is a branch of
    # Jump_D, see SELECTOR_WRAPS: ER's engine only lifts off in the jump states it knows by state id.)
    ("Jump_Land_S", ("state", "NewJump StateMachine")),
    ("Jump_Land_To_Sprint", ("state", "NewJump StateMachine")),
    ("Rolling_To_Run", ("state", "Evasion_SM")),
    ("Rolling_To_Dash", ("state", "Evasion_SM")),
    ("Rolling_To_Sprint", ("state", "Evasion_SM")),
]
GRAFTS += [(g["node"], (g["kind"], g["parent"])) for g in HERO["graph"]["grafts"]]
# ER clamps MoveSpeedIndex to 0..2 (walk/run/dash); NR allows 0..4 (3 sprint, 4 sprint start). Take NR's bounds.
WIDEN_BOUNDS = ["MoveSpeedIndex"]
# (new selector, ER selector it wraps, NR generator added as option 1, new int variable, ER variable it is cloned from)
# The new selector replaces the ER one in its parent; the variable (0/1) picks ER's generator or NR's.
# (ER group, new group): every ER clip generator playing a<ER group>_<id> for an id NR's graph also has gets a twin
# playing a<new group>_<id> in the same selectors. A weapon with spAtkcategory = new group then plays those clips.
CLIP_GROUP_CLONES = [tuple(c) for c in HERO["graph"]["clip_group_clones"]]
SELECTOR_WRAPS = [("NF_Jump_D_Sprint_MSG", "Jump_D_Direction_MSG", "Jump_S_Direction_MSG00", "NFSprintJump",
                   "JumpAttack_HandCondition")]
SELECTOR_WRAPS += [tuple(w) for w in HERO["graph"]["selector_wraps"]]
NR_ANIM_PREFIX, ER_ANIM_PREFIX = "..\\..\\..\\..\\..\\Model\\", "..\\..\\..\\..\\Model\\"


class Graph:
    def __init__(self, path):
        self.tree = ET.parse(path)
        self.root = self.tree.getroot()
        self.types = {t.get("id"): t for t in self.root.iter("type")}
        self.objs = {o.get("id"): o for o in self.root.iter("object")}
        self.tname = {i: (t.find("name").get("value") if t.find("name") is not None else "") for i, t in self.types.items()}
        self._sig = {}
        self.data = self.one("hkbBehaviorGraphData")
        self.strings = self.one("hkbBehaviorGraphStringData")
        self.values = self.obj(self.ptr(self.data, "variableInitialValues"))
        self.events = self.strs(self.strings, "eventNames")
        self.variables = self.strs(self.strings, "variableNames")
        self.anims = self.strs(self.strings, "animationNames")
        self.next_id = max(int(i[6:]) for i in self.objs) + 1

    def one(self, tname):
        found = [o for o in self.objs.values() if self.tname[o.get("typeid")] == tname]
        assert len(found) == 1, tname
        return found[0]

    def obj(self, oid):
        return self.objs[oid]

    @staticmethod
    def field(o, name):
        rec = o.find("record") if o.tag == "object" else o
        return rec.find(f"field[@name='{name}']")

    def ptr(self, o, name):
        return self.field(o, name).find("pointer").get("id")

    def strs(self, o, name):
        return [s.get("value") for s in self.field(o, name).find("array").findall("string")]

    def sig(self, tid):
        """Structural type signature, comparable across files."""
        if tid in self._sig:
            return self._sig[tid]
        self._sig[tid] = "<recursive>"
        t = self.types[tid]
        parts = [self.tname[tid], (t.find("version").get("value") if t.find("version") is not None else "")]
        params = t.find("parameters")
        if params is not None:
            for p in params:
                parts.append(self.sig(p.get("id")) if p.tag == "typeparam" else f"={p.get('value')}")
        if not self.tname[tid] and t.find("subtype") is not None:
            parts.append("sub:" + self.sig(t.find("subtype").get("id")))
        self._sig[tid] = "|".join(parts)
        return self._sig[tid]

    def fields_of(self, tid):
        out, t = [], self.types[tid]
        while t is not None:
            fs = t.find("fields")
            if fs is not None:
                out = [f.get("name") for f in fs] + out
            p = t.find("parent")
            t = self.types.get(p.get("id")) if p is not None else None
        return out

    def by_name(self, name, tname=None):
        found = [o for o in self.objs.values() if (n := self.field(o, "name")) is not None
                 and n.find("string") is not None and n.find("string").get("value") == name
                 and (tname is None or self.tname[o.get("typeid")] == tname)]
        assert len(found) == 1, (name, len(found))
        return found[0]

    def name_of(self, o):
        n = self.field(o, "name")
        return n.find("string").get("value") if n is not None and n.find("string") is not None else None

    def states(self, sm):
        """stateId -> StateInfo object of a state machine."""
        return {int(self.field(self.obj(p.get("id")), "stateId").find("integer").get("value")): self.obj(p.get("id"))
                for p in self.field(sm, "states").find("array").findall("pointer")}

    def parent_sm(self, state):
        sid = state.get("id")
        for o in self.objs.values():
            if self.tname[o.get("typeid")] == "hkbStateMachine" and any(
                    p.get("id") == sid for p in self.field(o, "states").find("array").findall("pointer")):
                return o
        raise KeyError(sid)


def append_ptr(g, o, field, oid):
    arr = g.field(o, field).find("array")
    ET.SubElement(arr, "pointer", {"id": oid})
    arr.set("count", str(len(arr.findall("pointer"))))


class Grafter:
    def __init__(self, nr, er):
        self.nr, self.er = nr, er
        er_sigs = {}
        for tid in er.types:
            er_sigs.setdefault(er.sig(tid), tid)
        self.tmap = {}
        for tid in nr.types:
            s = nr.sig(tid)
            if s in er_sigs:
                self.tmap[tid] = er_sigs[s]
        self.omap = {"object0": "object0"}
        self.added = {"events": [], "variables": [], "states": []}
        self.new_objs = []
        self.state_ids = {}  # NR StateInfo id -> new ER stateId

    def map_type(self, tid):
        if tid not in self.tmap:
            raise SystemExit(f"NR type {self.nr.sig(tid)} has no ER equivalent")
        return self.tmap[tid]

    # ---- name-indexed tables ---------------------------------------------------------------------------
    def event(self, nr_id):
        if nr_id < 0:
            return nr_id
        name = self.nr.events[nr_id]
        if name not in self.er.events:
            self.er.events.append(name)
            arr = self.er.field(self.er.strings, "eventNames").find("array")
            ET.SubElement(arr, "string", {"value": name})
            arr.set("count", str(len(self.er.events)))
            info = self.nr.field(self.nr.data, "eventInfos").find("array")[nr_id]
            dst = self.er.field(self.er.data, "eventInfos").find("array")
            dst.append(copy.deepcopy(info))
            dst.set("count", str(len(dst)))
            self.added["events"].append(name)
        return self.er.events.index(name)

    def variable(self, nr_idx):
        name = self.nr.variables[nr_idx]
        if name not in self.er.variables:
            info = self.nr.field(self.nr.data, "variableInfos").find("array")[nr_idx]
            vtype = int(info.find(".//field[@name='type']/integer").get("value"))
            if vtype > 5:  # quad / pointer variables live in other value arrays
                raise SystemExit(f"variable {name} has type {vtype}; not supported")
            self.er.variables.append(name)
            for g_obj, fname, src in ((self.er.strings, "variableNames", None),
                                      (self.er.data, "variableInfos", info),
                                      (self.er.data, "variableBounds",
                                       self.nr.field(self.nr.data, "variableBounds").find("array")[nr_idx]),
                                      (self.er.values, "wordVariableValues",
                                       self.nr.field(self.nr.values, "wordVariableValues").find("array")[nr_idx])):
                arr = self.er.field(g_obj, fname).find("array")
                arr.append(ET.Element("string", {"value": name}) if src is None else copy.deepcopy(src))
                arr.set("count", str(len(arr)))
            self.added["variables"].append(name)
        return self.er.variables.index(name)

    def anim(self, nr_idx):
        path = self.nr.anims[nr_idx]
        assert path.startswith(NR_ANIM_PREFIX), path
        path = ER_ANIM_PREFIX + path[len(NR_ANIM_PREFIX):]
        if path not in self.er.anims:
            self.er.anims.append(path)
            arr = self.er.field(self.er.strings, "animationNames").find("array")
            ET.SubElement(arr, "string", {"value": path})
            arr.set("count", str(len(self.er.anims)))
        return self.er.anims.index(path)

    # ---- object copy -----------------------------------------------------------------------------------
    def copy_obj(self, nr_id):
        if nr_id in self.omap:
            return self.omap[nr_id]
        new_id = f"object{self.er.next_id}"
        self.er.next_id += 1
        self.omap[nr_id] = new_id
        src = self.nr.obj(nr_id)
        o = copy.deepcopy(src)
        o.set("id", new_id)
        o.set("typeid", self.map_type(src.get("typeid")))
        keep = set(self.er.fields_of(o.get("typeid")))
        rec = o.find("record")
        for f in list(rec.findall("field")):
            if f.get("name") not in keep:
                rec.remove(f)
        missing = keep - {f.get("name") for f in rec.findall("field")}
        if missing:
            raise SystemExit(f"{self.nr.tname[src.get('typeid')]} lacks ER fields {missing}")
        self.new_objs.append(o)
        self.remap(o, src.get("typeid"))
        return new_id

    def remap(self, o, nr_tid):
        tname = self.nr.tname[nr_tid]
        for el in o.iter():
            if "elementtypeid" in el.attrib:
                el.set("elementtypeid", self.map_type(el.get("elementtypeid")))
        for el in list(o.iter("pointer")):
            el.set("id", self.copy_obj(el.get("id")))
        for rec in o.iter("record"):
            names = {f.get("name"): f for f in rec.findall("field")}
            for fname, f in names.items():
                iv = f.find("integer")
                if iv is None:
                    continue
                v = int(iv.get("value"))
                if fname in ("eventId", "enterEventId", "exitEventId") or (fname == "id" and "payload" in names):
                    iv.set("value", str(self.event(v)))
                elif fname == "variableIndex" and int(names["bindingType"].find("integer").get("value")) == 0:
                    iv.set("value", str(self.variable(v)))
                elif fname == "animationInternalId":
                    iv.set("value", str(self.anim(v)))
                elif fname in ("syncVariableIndex",) and v >= 0:
                    raise SystemExit(f"unhandled {fname} in {tname}")
        # Nested state machines are copied whole (their states, ids and transitions stay consistent among
        # themselves); event and variable ids inside them are remapped above like everywhere else.

    # ---- transitions ------------------------------------------------------------------------------------
    def fix_transitions(self, arr_obj, nr_sm, er_sm):
        """Remap toStateId of the transition entries in a copied TransitionInfoArray; drop ones ER can't reach."""
        nr_states, er_states = self.nr.states(nr_sm), self.er.states(er_sm)
        er_by_name = {self.er.name_of(s): sid for sid, s in er_states.items()}
        arr = self.er.field(arr_obj, "transitions").find("array")
        for t in list(arr):
            to = t.find("field[@name='toStateId']/integer")
            target = self.nr_state_target(nr_states, int(to.get("value")), er_by_name)
            if target is None:
                print("  drop transition to", self.nr.name_of(nr_states[int(to.get("value"))]))
                arr.remove(t)
            else:
                to.set("value", str(target))
            for nested in ("fromNestedStateId", "toNestedStateId"):
                assert t.find(f"field[@name='{nested}']/integer").get("value") == "0"
        arr.set("count", str(len(arr)))

    def nr_state_target(self, nr_states, nr_sid, er_by_name):
        st = nr_states[nr_sid]
        if st.get("id") in self.state_ids:
            return self.state_ids[st.get("id")]
        return er_by_name.get(self.nr.name_of(st))

    def copy_entry(self, entry):
        """Copy one NR transition entry record (its pointers and event ids remapped) for an ER array."""
        e = copy.deepcopy(entry)
        holder = ET.Element("object", {"id": "tmp", "typeid": "x"})
        holder.append(e)
        for el in list(e.iter("pointer")):
            el.set("id", self.copy_obj(el.get("id")))
        for el in e.iter():
            if "elementtypeid" in el.attrib:
                el.set("elementtypeid", self.map_type(el.get("elementtypeid")))
        for rec in e.iter("record"):  # includes e itself
            for f in rec.findall("field"):
                if f.get("name") in ("eventId", "enterEventId", "exitEventId") and f.find("integer") is not None:
                    iv = f.find("integer")
                    iv.set("value", str(self.event(int(iv.get("value")))))
        return e

    def incoming(self, nr_sm, er_sm, nr_state):
        """Copy transitions that lead into a grafted state: wildcard ones and those of same-named states."""
        nr_sid = int(self.nr.field(nr_state, "stateId").find("integer").get("value"))
        er_sid = self.state_ids[nr_state.get("id")]
        sources = [(self.nr.ptr(nr_sm, "wildcardTransitions"), er_sm, "wildcardTransitions")]
        er_by_name = {self.er.name_of(s): s for s in self.er.states(er_sm).values()}
        for st in self.nr.states(nr_sm).values():
            if st.get("id") in self.state_ids or self.nr.ptr(st, "transitions") == "object0":
                continue
            if self.nr.name_of(st) in er_by_name:
                sources.append((self.nr.ptr(st, "transitions"), er_by_name[self.nr.name_of(st)], "transitions"))
        for nr_arr, er_owner, fname in sources:
            if nr_arr == "object0":
                continue
            for entry in self.nr.field(self.nr.obj(nr_arr), "transitions").find("array"):
                if int(entry.find("field[@name='toStateId']/integer").get("value")) != nr_sid:
                    continue
                er_arr_id = self.er.ptr(er_owner, fname)
                if er_arr_id == "object0":
                    print(f"  skip: ER {self.er.name_of(er_owner)} has no {fname} array")
                    continue
                e = self.copy_entry(entry)
                e.find("field[@name='toStateId']/integer").set("value", str(er_sid))
                arr = self.er.field(self.er.obj(er_arr_id), "transitions").find("array")
                arr.append(e)
                arr.set("count", str(len(arr)))
                print(f"  transition into {self.nr.name_of(nr_state)} from {self.er.name_of(er_owner) or 'wildcard'}"
                      f" on {self.nr.events[int(entry.find('field[@name=\"eventId\"]/integer').get('value'))]}")

    # ---- main ----------------------------------------------------------------------------------------------
    def run(self):
        pending = []
        for name, (kind, target) in GRAFTS:
            if kind == "blend_child":
                src = self.nr.by_name(name)
                child = next(o for o in self.nr.objs.values() if self.nr.tname[o.get("typeid")] == "hkbBlenderGeneratorChild"
                             and self.nr.ptr(o, "generator") == src.get("id"))
                append_ptr(self.er, self.er.by_name(target), "children", self.copy_obj(child.get("id")))
                print(f"{name} -> {target} (blender child)")
                continue
            if kind == "generator":
                src = self.nr.by_name(name)
                dst = self.er.by_name(target)
                nr_parent = self.nr.by_name(target)
                nr_slot = [p.get("id") for p in self.nr.field(nr_parent, "generators").find("array")].index(src.get("id"))
                er_count = len(self.er.field(dst, "generators").find("array"))
                assert er_count == nr_slot, f"{name}: NR slot {nr_slot}, ER has {er_count} generators"
                append_ptr(self.er, dst, "generators", self.copy_obj(src.get("id")))
                print(f"{name} -> {target}[{nr_slot}]")
            else:
                src = self.nr.by_name(name, "hkbStateMachine::StateInfo")
                nr_sm = self.nr.parent_sm(src)
                er_sm = self.er.by_name(target, "hkbStateMachine")
                assert self.nr.name_of(nr_sm) == target
                sid = max(self.er.states(er_sm)) + 1
                self.state_ids[src.get("id")] = sid
                new = self.copy_obj(src.get("id"))
                self.er.objs[new] = self.new_objs[-1] if self.new_objs[-1].get("id") == new else \
                    next(o for o in self.new_objs if o.get("id") == new)
                self.er.field(self.er.objs[new], "stateId").find("integer").set("value", str(sid))
                append_ptr(self.er, er_sm, "states", new)
                self.added["states"].append(name)
                pending.append((src, nr_sm, er_sm))
                print(f"{name} -> {target} stateId {sid}")
        for o in self.new_objs:
            self.er.objs.setdefault(o.get("id"), o)
        for src, nr_sm, er_sm in pending:
            tr = self.nr.ptr(src, "transitions")
            if tr != "object0":
                self.fix_transitions(self.er.obj(self.omap[tr]), nr_sm, er_sm)
            self.incoming(nr_sm, er_sm, src)
        for o in self.new_objs:
            self.er.objs.setdefault(o.get("id"), o)
            if o not in list(self.er.root):
                self.er.root.append(o)
        for wrap in SELECTOR_WRAPS:
            self.wrap_selector(*wrap)
        for old, new in CLIP_GROUP_CLONES:
            self.clone_clip_group(old, new)

    def clone_clip_group(self, old, new):
        tag_old, tag_new = f"a{old:03d}", f"a{new:03d}"
        nr_ids = {p.rsplit("\\", 1)[1][5:-4] for p in self.nr.anims if f"\\{tag_old}\\{tag_old}_" in p}
        if self.clips_root:  # only clips NR actually ships
            nr_ids &= {f.stem[5:] for f in Path(self.clips_root).rglob(f"{tag_old}_*.hkx")}
        parents = {}
        for o in list(self.er.objs.values()):
            f = self.er.field(o, "generators")
            if f is not None and f.find("array") is not None:
                for p in f.find("array").findall("pointer"):
                    parents.setdefault(p.get("id"), []).append(o)
        clips = [o for o in list(self.er.objs.values()) if self.er.tname[o.get("typeid")] == "hkbClipGenerator"
                 and self.er.field(o, "animationName").find("string").get("value").startswith(tag_old + "_")
                 and self.er.field(o, "animationName").find("string").get("value")[5:] in nr_ids]
        for c in clips:
            anim_id = self.er.field(c, "animationName").find("string").get("value")[5:]
            path = f"{ER_ANIM_PREFIX}chr\\c0000\\hkx\\{tag_new}\\{tag_new}_{anim_id}.hkx"
            if path not in self.er.anims:
                self.er.anims.append(path)
                arr = self.er.field(self.er.strings, "animationNames").find("array")
                ET.SubElement(arr, "string", {"value": path})
                arr.set("count", str(len(self.er.anims)))
            twin = self.er_clone(c.get("id"))
            self.er.field(twin, "animationName").find("string").set("value", f"{tag_new}_{anim_id}")
            name = self.er.field(twin, "name").find("string")
            name.set("value", tag_new + name.get("value")[4:])
            self.er.field(twin, "animationInternalId").find("integer").set("value", str(self.er.anims.index(path)))
            for parent in parents.get(c.get("id"), []):
                append_ptr(self.er, parent, "generators", twin.get("id"))
        print(f"clip group {tag_old} -> {tag_new}: {len(clips)} clip generators for {len(nr_ids)} NR clip ids")

    def er_clone(self, oid):
        o = copy.deepcopy(self.er.obj(oid))
        o.set("id", f"object{self.er.next_id}")
        self.er.next_id += 1
        self.er.objs[o.get("id")] = o
        self.er.root.append(o)
        return o

    def add_er_variable(self, name, like):
        """Append an ER variable named `name` with the info, bounds and initial value of ER variable `like`."""
        if name in self.er.variables:  # shared by several wraps
            return self.er.variables.index(name)
        i = self.er.variables.index(like)
        self.er.variables.append(name)
        for g_obj, fname in ((self.er.strings, "variableNames"), (self.er.data, "variableInfos"),
                             (self.er.data, "variableBounds"), (self.er.values, "wordVariableValues")):
            arr = self.er.field(g_obj, fname).find("array")
            arr.append(ET.Element("string", {"value": name}) if fname == "variableNames" else copy.deepcopy(arr[i]))
            arr.set("count", str(len(arr)))
        self.added["variables"].append(name)
        return len(self.er.variables) - 1

    def wrap_selector(self, new_name, er_name, nr_name, var, like):
        er_sel = self.er.by_name(er_name)
        nr_sel = self.copy_obj(self.nr.by_name(nr_name).get("id"))
        for o in self.new_objs:
            self.er.objs.setdefault(o.get("id"), o)
            if o not in list(self.er.root):
                self.er.root.append(o)
        parents = [o for o in self.er.objs.values() if o.find(".//field[@name='generator']/pointer") is not None
                   and o.find(".//field[@name='generator']/pointer").get("id") == er_sel.get("id")]
        # Or a selector listing it among its generators (the roll's CMSG).
        lists = [o for o in self.er.objs.values() if (f := self.er.field(o, "generators")) is not None and f.find("array") is not None
                 and any(q.get("id") == er_sel.get("id") for q in f.find("array").findall("pointer"))] if not parents else []
        assert len(parents) + len(lists) == 1, (er_name, len(parents), len(lists))
        w = self.er_clone(er_sel.get("id"))
        self.er.field(w, "name").find("string").set("value", new_name)
        arr = self.er.field(w, "generators").find("array")
        for p in list(arr):
            arr.remove(p)
        for oid in (er_sel.get("id"), nr_sel):
            ET.SubElement(arr, "pointer", {"id": oid})
        arr.set("count", "2")
        b = self.er_clone(self.er.ptr(er_sel, "variableBindingSet"))
        self.er.field(w, "variableBindingSet").find("pointer").set("id", b.get("id"))
        recs = self.er.field(b, "bindings").find("array")
        assert len(recs) == 1
        recs[0].find("field[@name='variableIndex']/integer").set("value", str(self.add_er_variable(var, like)))
        if parents:
            parents[0].find(".//field[@name='generator']/pointer").set("id", w.get("id"))
        else:
            for q in self.er.field(lists[0], "generators").find("array").findall("pointer"):
                if q.get("id") == er_sel.get("id"):
                    q.set("id", w.get("id"))
        print(f"{new_name}: [{er_name}, NR {nr_name}] by {var}, in {self.er.tname[(parents or lists)[0].get('typeid')]}")


def main(nr_xml, er_xml, out_xml, out_names, clips_root=None):
    nr, er = Graph(nr_xml), Graph(er_xml)
    g = Grafter(nr, er)
    g.clips_root = clips_root
    g.run()
    nr_bounds = nr.field(nr.data, "variableBounds").find("array")
    er_bounds = er.field(er.data, "variableBounds").find("array")
    for name in WIDEN_BOUNDS:
        i, j = nr.variables.index(name), er.variables.index(name)
        old = [x.get("value") for x in er_bounds[j].iter("integer")]
        er_bounds[j] = copy.deepcopy(nr_bounds[i])
        print(f"bounds {name}: {old} -> {[x.get('value') for x in er_bounds[j].iter('integer')]}")
    for o in g.new_objs:
        if o not in list(er.root):
            er.root.append(o)
    er.tree.write(out_xml, encoding="utf-8", xml_declaration=True)
    json.dump(g.added, open(out_names, "w"), indent=1)
    print(f"{len(g.new_objs)} objects added; events {g.added['events']}; variables {g.added['variables']}")


if __name__ == "__main__":
    main(*sys.argv[1:6])
