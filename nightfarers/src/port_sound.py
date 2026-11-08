# Nightreign Wwise banks -> Elden Ring (both Wwise bank version 135, same init.bnk bus ids).
#   port_sound.py rename <nr_bank.bnk> <name> <out.bnk> [drop object types,]: the same bank under another name (header bank id = FNV-1 of
#     the name), e.g. NR hero01.bnk -> sd/cs_c0000.bnk, which ER loads for the player (exe: cs_c%04d per character).
#   port_sound.py <er_bank.bnk> <nr_bank.bnk> <out.bnk> [--stream <wem dir>] [--media <nr_bank.bnk>...]: merge (below),
#     e.g. hero01 into ER's sd/enus/cs_main.bnk. With the clips embedded (+1 MB) ER dropped all of cs_main (tests 1, 2, 4,
#     even sorted and aligned); likely a sound memory cap -> --stream keeps the bank +12 KB.
#     (ER does not load a cs_c0000 bank for the player: the renamed hero bank stayed silent.)
# Appends every HIRC object (sounds, containers, actions, events...) of the NR bank whose id the ER bank lacks, and the
# embedded audio (DIDX/DATA) they need. Used for Wylder's hero01.bnk (Claw Shot sounds Play_c000107000-107006) ->
# ER sd/enus/cs_main.bnk, which ER always has loaded. hero01's objects only reference their own audio, two clips
# ER's cs_main already has, and one shared parent/bus id ER has too (checked; NOTES "Sound").
import os, sys, struct


ER_PROJECT_ID = 0x772


def sections(b):
    o, out = 0, []
    while o + 8 <= len(b):
        tag, n = b[o:o + 4], struct.unpack_from('<I', b, o + 4)[0]
        out.append([tag, bytearray(b[o + 8:o + 8 + n])]); o += 8 + n
    assert o == len(b), 'trailing bytes'
    return out


def objects(hirc):
    cnt, p, out = struct.unpack_from('<I', hirc, 0)[0], 4, []
    for _ in range(cnt):
        t, sz, i = struct.unpack_from('<BII', hirc, p)
        out.append((t, i, bytes(hirc[p:p + 5 + sz]))); p += 5 + sz
    assert p == len(hirc)
    return out


def media(secs):
    d = dict((t, s) for t, s in secs)
    didx, data = d.get(b'DIDX', b''), d.get(b'DATA', b'')
    out = {}
    for k in range(0, len(didx), 12):
        i, off, sz = struct.unpack_from('<III', didx, k); out[i] = bytes(data[off:off + sz])
    return out


def fnv(name):
    h = 2166136261
    for c in name.lower().encode(): h = ((h * 16777619) & 0xffffffff) ^ c
    return h


def rename(nr, name, drop=()):
    secs = sections(nr)
    if drop:
        kept = [raw for t, _, raw in objects(dict(map(tuple, secs))[b'HIRC']) if t not in drop]
        secs = [[t, bytearray(struct.pack('<I', len(kept)) + b''.join(kept)) if t == b'HIRC' else s] for t, s in secs]
    bkhd = dict(map(tuple, secs))[b'BKHD']
    struct.pack_into('<I', bkhd, 4, fnv(name))
    # Wwise project id: every Elden Ring bank has 0x772, Nightreign's 0x31bc; the loader's LoadBank failed with AK_Fail on NR's.
    struct.pack_into('<I', bkhd, 16, ER_PROJECT_ID)
    out = bytearray()
    for t, s in secs: out += t + struct.pack('<I', len(s)) + s
    return bytes(out)


def children(raw, ids):
    """(offset, ids) of an actor-mixer's child list: the object's tail is u32 count + count sorted u32 ids."""
    for n in range(1, (len(raw) - 9) // 4):
        p = len(raw) - 4 * n - 4
        if struct.unpack_from('<I', raw, p)[0] == n:
            kids = struct.unpack_from(f'<{n}I', raw, p + 4)
            if all(k in ids for k in kids): return p, list(kids)
    raise ValueError('no child list')


def merge(er, nr, stream_dir=None, more_media=()):
    """stream_dir: NR clips ER lacks become streamed loose files <stream_dir>/<first 2 digits>/<id>.wem (ER's own
    layout for streamed sounds) instead of growing the bank; more_media: other NR banks to take such clips from."""
    es, ns = sections(er), sections(nr)
    tags = [t for t, _ in es]
    assert struct.unpack_from('<I', dict(es)[b'BKHD'], 0)[0] == struct.unpack_from('<I', dict(ns)[b'BKHD'], 0)[0], 'bank versions differ'
    eh, nh = dict(es)[b'HIRC'], dict(ns)[b'HIRC']
    eobjs, nobjs = objects(eh), objects(nh)
    have = {i: (t, raw) for t, i, raw in eobjs}
    add = [o for o in nobjs if o[1] not in have]
    nids = {i for _, i, _ in nobjs}
    # Objects both banks have must match, except shared actor-mixers (type 7): ER's copy also gets NR's children.
    for t, i, raw in nobjs:
        if i not in have or have[i][1] == raw: continue
        assert t == 7 == have[i][0], f'object {i} (type {t}) differs between the banks'
        p, ek = children(have[i][1], set(have) | nids)
        _, nk = children(raw, nids | set(have))
        kids = sorted(set(ek) | set(nk))
        new = bytearray(have[i][1][:p]) + struct.pack(f'<I{len(kids)}I', len(kids), *kids)
        struct.pack_into('<I', new, 1, len(new) - 5)
        old = have[i][1]; at = eh.find(old)
        eh[at:at + len(old)] = new
        print(f'actor-mixer {i}: {len(ek)} -> {len(kids)} children')
    em, nm = media(es), media(ns)
    for b in more_media: nm = {**media(sections(b)), **nm}
    new_media = {i: m for i, m in nm.items() if i not in em}
    if stream_dir:
        streamed = set()
        for k, (t, i, raw) in enumerate(add):
            if t != 2: continue
            plug, st, src = struct.unpack_from('<IBI', raw, 9)
            if st != 0 or src in em or plug != 0x40001: continue  # 0x640002 etc. = source plugins, no clip
            assert src in new_media, f'sound {i}: clip {src} not found'
            raw = bytearray(raw); raw[13] = 2; add[k] = (t, i, bytes(raw))  # stream type 0 (in bank) -> 2 (streamed)
            d = os.path.join(stream_dir, str(src)[:2]); os.makedirs(d, exist_ok=True)
            open(os.path.join(d, f'{src}.wem'), 'wb').write(new_media[src]); streamed.add(src)
        print(f'{len(streamed)} clips streamed from {stream_dir}')
        new_media = {}
    # HIRC: append objects, bump the count.
    for _, _, raw in add: eh += raw
    struct.pack_into('<I', eh, 0, struct.unpack_from('<I', eh, 0)[0] + len(add))
    # DIDX/DATA: Wwise needs the media index sorted by id (ER's banks also lay the audio out in that order, 16-byte
    # aligned); unsorted entries made most of cs_main's embedded clips silent in game.
    allm = {**em, **new_media}
    didx, data = bytearray(), bytearray()
    for i in sorted(allm):
        data += b'\0' * (-len(data) % 16)
        didx += struct.pack('<III', i, len(data), len(allm[i])); data += allm[i]
    # Wwise wants the audio (DATA payload) 16-byte aligned in the file and pads BKHD (20-32 bytes, zero tail) to get
    # there; every bank of both games does. A misaligned merge made ER drop all of cs_main (no player sounds).
    bkhd = dict(es)[b'BKHD']
    assert not any(bkhd[20:]), 'BKHD tail is not padding'
    pad = -(8 + 20 + 8 + len(didx) + 8) % 16
    d = dict(es); d[b'BKHD'], d[b'DIDX'], d[b'DATA'], d[b'HIRC'] = bkhd[:20] + bytes(pad), didx, data, eh
    es = [[t, d[t]] for t, _ in es]
    out = bytearray()
    for t, s in es: out += t + struct.pack('<I', len(s)) + s
    print(f'+{len(add)} objects ({sum(o[0] == 4 for o in add)} events), +{len(new_media)} media, '
          f'{len(objects(nh)) - len(add)} NR objects already present; sections {[t.decode() for t in tags]}')
    return bytes(out)


if __name__ == '__main__':
    if sys.argv[1] == 'rename':
        drop = {int(x) for x in sys.argv[5].split(',')} if len(sys.argv) > 5 else ()
        open(sys.argv[4], 'wb').write(rename(open(sys.argv[2], 'rb').read(), sys.argv[3], drop)); sys.exit()
    a = sys.argv[1:]
    stream = a[a.index('--stream') + 1] if '--stream' in a else None
    more = [open(x, 'rb').read() for x in a[a.index('--media') + 1:]] if '--media' in a else []
    out = merge(open(a[0], 'rb').read(), open(a[1], 'rb').read(), stream, more)
    open(a[2], 'wb').write(out)
