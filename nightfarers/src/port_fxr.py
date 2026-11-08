# Convert a Nightreign FXR (as SoulsFormats FXR3 XML, from `flvertool fxrcheck -xml`) to Elden Ring's variant.
#   port_fxr.py <in.xml> <out.xml> [--drop-tex <id,...>]  (blank emitters drawing those textures)
# NR files are ER's FXR v5 layout with Armored Core 6 additions (header byte 4 = 1). Rules learned from 167 effect ids
# both games ship (work/s4/sfx/xs; NOTES "FFX"):
#  - curves: NR ComponentHermite ("UnkAc6": duration, per-component stop counts/min/max, per-component keys) -> ER
#    Hermite ("Curve2": stop count, min[c], max[c], times, values, tangents in/out); components with one stop are held.
#  - modifiers: TypeEnumB is a function of TypeEnumA in ER, NR writes 0.
#  - actions: Unk04 is fixed per action id in ER, NR writes 0; a few actions gained trailing fields (truncated to ER's
#    largest count; ER itself ships both counts of 603/604/405, so the engine reads the count from the file).
#  - action 10015 (model particle) was reordered in NR: remapped as ER's 26-field / 27-property variant.
import sys, copy, xml.etree.ElementTree as ET

XSI = 'http://www.w3.org/2001/XMLSchema-instance'
ET.register_namespace('xsi', XSI); ET.register_namespace('xsd', 'http://www.w3.org/2001/XMLSchema')
UNK04 = {15: 2, 34: 3, 36: 1, 46: 4, 60: 1, 64: 2, 65: 3, 83: 5, 84: 4, 105: 5, 106: 6, 120: 8, 122: 10, 301: 1,
         399: 2, 401: 1, 402: 2, 403: 3, 404: 4, 405: 5, 501: 1}
TYPE_B = {'57440': '8', '57443': '11', '61520': '16', '53376': '4', '53379': '7'}
MAX_FIELDS = {('10012', 'Fields2'): 41, ('10500', 'Fields1'): 10, ('133', 'Fields1'): 5, ('609', 'Fields2'): 33,
              ('10015', 'Fields2'): 38}
COMPONENTS = {'Scalar': 1, 'Vector2': 2, 'Vector3': 3, 'Color': 4}


def num(e):
    return float(e.get('Value')) if e.tag == 'Float' else int(e.get('Value'))


def field(tag, v):
    e = ET.Element(tag); e.set('Value', repr(float(v)) if tag == 'Float' else str(v)); return e


def hermite(prop):
    f = list(prop.find('Fields'))
    n = COMPONENTS[prop.get('PropertyType')]
    counts = [num(x) for x in f[1:1 + n]]
    pos, comps = 1 + 3 * n, []
    for c in counts:
        c = int(c)
        comps.append([[num(x) for x in f[pos + k * c:pos + (k + 1) * c]] for k in range(4)])  # times, values, tin, tout
        pos += 4 * c
    assert pos == len(f), (prop.get('PropertyType'), counts, len(f))
    multi = [k for k in comps if len(k[0]) > 1]
    times = multi[0][0] if multi else comps[0][0]
    if any(k[0] != times for k in multi):
        # Keys at different times per component: key every component at the union of times (values interpolated
        # linearly, tangents kept where a component had a key there). Approximate; rare (1 of 167 sampled ids).
        times = sorted({t for k in multi for t in k[0]})
        print("  approximated curve (component key times differ)", file=sys.stderr)
        def at(k, t):
            ts, vs = k[0], k[1]
            if t in ts: i = ts.index(t); return [t, vs[i], k[2][i], k[3][i]]
            if t <= ts[0]: return [t, vs[0], 0.0, 0.0]
            if t >= ts[-1]: return [t, vs[-1], 0.0, 0.0]
            i = next(i for i in range(len(ts)) if ts[i] > t)
            u = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
            return [t, vs[i - 1] + u * (vs[i] - vs[i - 1]), 0.0, 0.0]
        comps = [[list(c) for c in zip(*[at(k, t) for t in times])] if len(k[0]) > 1 else k for k in comps]
    m = len(times)
    ref = multi[0] if multi else comps[0]  # held components take the keyed one's tangents (as ER's own files do)
    def comp(k, j, i): return k[j][i] if len(k[0]) > 1 else (k[1][0] if j == 1 else ref[j][i] if len(ref[0]) > 1 else 0.0)
    out = [field('Int', m)] + [field('Float', min(k[1])) for k in comps] + [field('Float', max(k[1])) for k in comps]
    out += [field('Float', t) for t in times]
    for j in (1, 2, 3):
        out += [field('Float', comp(k, j, i)) for i in range(m) for k in comps]
    fe = prop.find('Fields'); fe.clear(); fe.extend(out)
    prop.set('InterpolationType', 'Curve2')


def action_10015(a):
    f1 = list(a.find('Fields1'))
    if len(f1) == 55:
        a.find('Fields1')[:] = f1[:25] + [f1[33]]
    p1 = list(a.find('Properties1'))
    if len(p1) == 44:
        zero = p1[16]
        assert zero.get('InterpolationType') == 'Zero', zero.attrib
        a.find('Properties1')[:] = p1[:23] + [copy.deepcopy(zero), p1[23], copy.deepcopy(zero), copy.deepcopy(p1[23])]
    a.find('UnkFieldLists').clear()


def convert(root):
    stats = {'curves': 0, 'modifiers': 0, 'actions': 0}
    for prop in root.iter('Property'):
        if prop.get('InterpolationType') == 'UnkAc6':
            hermite(prop); stats['curves'] += 1
    for m in root.iter('PropertyModifier'):
        m.set('TypeEnumB', TYPE_B[m.get('TypeEnumA')]); stats['modifiers'] += 1
    for a in root.iter('Action'):
        aid = a.get('Id'); stats['actions'] += 1
        a.find('Unk04').text = str(UNK04.get(int(aid), 0))
        if aid == '10015': action_10015(a)
        for t in ('Fields1', 'Fields2'):
            lim = MAX_FIELDS.get((aid, t))
            if lim is not None and len(a.find(t)) > lim: a.find(t)[:] = list(a.find(t))[:lim]
    return stats


def drop_tex(root, ids):
    """Blank the drawing action of every emitter that draws one of the texture ids: it becomes an empty action 0, like
    ER's own emitters that draw nothing. (Removing the emitters themselves crashed the game when the effect spawned.)"""
    n = 0
    for act in list(root.iter('Action')):
        if any(v.tag == 'Int' and int(v.get('Value')) in ids for v in act.iter()):
            act.set('Id', '0')
            for c in list(act): act.remove(c)
            for tag, text in (('Unk02', 'false'), ('Unk03', 'true'), ('Unk04', '0')):
                ET.SubElement(act, tag).text = text
            for tag in ('UnkFieldLists', 'Fields1', 'Fields2', 'Properties1', 'Properties2'): ET.SubElement(act, tag)
            n += 1
    return n


if __name__ == '__main__':
    tree = ET.parse(sys.argv[1])
    s = convert(tree.getroot())
    if '--drop-tex' in sys.argv:
        s['blanked emitters'] = drop_tex(tree.getroot(), {int(x) for x in sys.argv[sys.argv.index('--drop-tex') + 1].split(',')})
    tree.write(sys.argv[2], encoding='utf-8', xml_declaration=True)
    print(sys.argv[1].replace('\\', '/').split('/')[-1], s)
