# Where a Scaleform HUD places things: every named instance with its position on screen, through the nested sprites.
#   gfx_tree.py <file.gfx> <regex on instance or path>
# Positions in stage pixels, from each sprite's first placement of the child (the file's own timeline, not what scripts move later).
import re, struct, sys


class Bits:
    def __init__(s, b, p): s.b, s.p, s.n = b, p, 0
    def u(s, c):
        v = 0
        for _ in range(c):
            v = v << 1 | (s.b[s.p] >> (7 - s.n) & 1)
            s.n += 1
            if s.n == 8: s.n, s.p = 0, s.p + 1
        return v
    def i(s, c):
        v = s.u(c) if c else 0
        return v - (1 << c) if c and v >> (c - 1) else v
    def end(s): return s.p + (1 if s.n else 0)


def matrix(b, p):
    r = Bits(b, p)
    sx = sy = 1.0
    r0 = r1 = 0.0
    if r.u(1):
        n = r.u(5); sx, sy = r.i(n) / 65536, r.i(n) / 65536
    if r.u(1):
        n = r.u(5); r0, r1 = r.i(n) / 65536, r.i(n) / 65536
    n = r.u(5)
    tx, ty = r.i(n) / 20, r.i(n) / 20
    return (sx, r0, r1, sy, tx, ty), r.end()


def tags(b, p, end):
    while p + 2 <= end:
        h = struct.unpack_from('<H', b, p)[0]
        code, ln = h >> 6, h & 63
        p += 2
        if ln == 63:
            ln = struct.unpack_from('<I', b, p)[0]; p += 4
        yield code, p, ln
        p += ln
        if code == 0: return


def cstr(b, p):
    e = b.index(0, p)
    return b[p:e].decode('utf-8', 'replace'), e + 1


def placements(b, p, end):
    out = []
    for code, q, ln in tags(b, p, end):
        if code not in (26, 70): continue
        flags = b[q]; q += 1
        flags2 = 0
        if code == 70:
            flags2 = b[q]; q += 1
        q += 2  # depth
        if code == 70 and flags2 & 8:  # class name
            _, q = cstr(b, q)
        char = None
        if flags & 2:
            char = struct.unpack_from('<H', b, q)[0]; q += 2
        m = None
        if flags & 4:
            m, q = matrix(b, q)
        if flags & 8:  # colour transform: skip
            r = Bits(b, q); add, mul = r.u(1), r.u(1); n = r.u(4)
            for _ in range((4 if mul else 0) + (4 if add else 0)): r.u(n)
            q = r.end()
        if flags & 16: q += 2
        name = None
        if flags & 32:
            name, q = cstr(b, q)
        out.append((char, m, name))
    return out


b = open(sys.argv[1], 'rb').read()
want = re.compile(sys.argv[2])
r = Bits(b, 8)
n = r.u(5)
x0, x1, y0, y1 = (r.i(n) / 20 for _ in range(4))
print(f'stage {x1 - x0:.0f} x {y1 - y0:.0f}')
start = r.end() + 4
sprites, images = {}, {}
for code, q, ln in tags(b, start, len(b)):
    if code == 39:
        sprites[struct.unpack_from('<H', b, q)[0]] = placements(b, q + 4, q + ln)
    elif code == 1009:
        names = re.findall(rb'MENU_[A-Za-z0-9_]+', b[q:q + ln])
        images[struct.unpack_from('<H', b, q)[0]] = names[0].decode() if names else '?'
root = placements(b, start, len(b))


def walk(items, tx, ty, sx, sy, path, depth, seen):
    done = set()
    for char, m, name in items:
        if char is None or (char, name) in done: continue
        done.add((char, name))
        ox, oy = (m[4], m[5]) if m else (0, 0)
        ax, ay = tx + ox * sx, ty + oy * sy
        nsx, nsy = sx * (m[0] if m else 1), sy * (m[3] if m else 1)
        label = name or images.get(char) or f'#{char}'
        p = path + '/' + label
        if want.search(p) and (name or char in images):
            print(f'{ax:8.1f} {ay:8.1f} scale {nsx:.2f} {p[-150:]}')
        if char in sprites and depth < 14 and char not in seen:
            walk(sprites[char], ax, ay, nsx, nsy, p, depth + 1, seen | {char})


walk(root, 0, 0, 1, 1, '', 0, frozenset())
