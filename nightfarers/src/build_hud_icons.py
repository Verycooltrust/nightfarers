# Cut sprites out of an unpacked menu atlas for the helper's HUD.
#   build_hud_icons.py <atlas.layout> <atlas in R8G8B8A8 .dds> <out dir> <sprite name>...
# Writes <out dir>/<sprite name>.rgba (u32 width, u32 height, RGBA bytes) and a .png to look at.
import os, re, struct, sys, zlib

layout, dds, out = sys.argv[1:4]
text = open(layout, encoding='utf-8-sig').read()
data = open(dds, 'rb').read()
height, width = struct.unpack_from('<II', data, 12)
start = 148 if data[84:88] == b'DX10' else 128


def png(path, w, h, rgba):
    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body))
    rows = b''.join(b'\0' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


os.makedirs(out, exist_ok=True)
for name in sys.argv[4:]:
    tag = re.search(rf'<SubTexture[^>]*name="{re.escape(name)}\.png"[^>]*>', text)
    if not tag:
        raise SystemExit(f'{name}: not in {layout}')
    x, y, w, h = (int(re.search(rf'\b{k}="(\d+)"', tag.group(0)).group(1)) for k in ('x', 'y', 'width', 'height'))
    rgba = b''.join(data[start + (y + row) * width * 4 + x * 4:start + (y + row) * width * 4 + (x + w) * 4] for row in range(h))
    with open(f'{out}/{name}.rgba', 'wb') as f:
        f.write(struct.pack('<II', w, h) + rgba)
    png(f'{out}/{name}.png', w, h, rgba)
    print(name, w, h)
