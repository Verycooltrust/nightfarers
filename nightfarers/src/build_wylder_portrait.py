"""Stage 2: Wylder's class-screen portrait, made from Nightreign's own character art.

The class screen draws BaseChrSelectMenuParam.imageId N as sprite MENU_Ch_(N-5) (Samurai 13 -> MENU_Ch_08). Sprites
live in 01_common: a .layout per atlas (sblytbnd) and BC7 atlases (tpf). SB_Preset_2 (4096x4096) has free space below
its six portraits, so Wylder goes there as MENU_Ch_13. Only the BC7 blocks of that region are replaced; the other
portraits keep their original bytes.

  python build_wylder_portrait.py <nr MENU_Character_49000.dds> <er SB_Preset_2.dds> <er SB_Preset_2.layout> <texconv.exe>
Writes the .dds and .layout in place (pass copies).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

SPRITE, X, Y, W, H = "MENU_Ch_13.png", 0, 2744, 1066, 1352  # free area: y 2744..4096 under the six portraits
DDS_HEADER = 148  # DDS magic + header + DX10 header


def portrait(art_path, atlas):
    # Background: vertical gradient between the Samurai portrait's own top and bottom colours.
    ref = atlas.crop((2140, 0, 2140 + 1066, 1368))
    top, bottom = (ref.crop((0, y, 1066, y + 40)).resize((1, 1)).getpixel((0, 0)) for y in (0, 1328))
    bw = (W + 3) // 4 * 4
    bg = Image.new("RGBA", (bw, H))
    for y in range(H):
        t = y / (H - 1)
        bg.paste(tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)), (0, y, bw, y + 1))
    # Nightreign's 1000x1000 art (transparent background), scaled to the frame height and centred.
    art = Image.open(art_path).convert("RGBA")
    art = art.resize((H, H), Image.LANCZOS)
    bg.alpha_composite(art, ((bw - H) // 2, 0))
    return bg


def bc7(img, texconv):
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "p.png"
        img.save(png)
        subprocess.run([str(Path(texconv).resolve()), "-nologo", "-y", "-f", "BC7_UNORM", "-m", "1", "-o", tmp, str(png)],
                       check=True, capture_output=True)
        return (Path(tmp) / "p.dds").read_bytes()[DDS_HEADER:]


def main(art_path, atlas_dds, layout, texconv):
    atlas = Image.open(atlas_dds).convert("RGBA")
    assert atlas.size == (4096, 4096)
    img = portrait(art_path, atlas)
    blocks = bc7(img, texconv)
    data = bytearray(Path(atlas_dds).read_bytes())
    row_bytes, src_row = 4096 // 4 * 16, img.width // 4 * 16
    for by in range(H // 4):
        dst = DDS_HEADER + (Y // 4 + by) * row_bytes + X // 4 * 16
        data[dst:dst + src_row] = blocks[by * src_row:(by + 1) * src_row]
    Path(atlas_dds).write_bytes(data)

    text = Path(layout).read_text(encoding="utf-8")
    if SPRITE not in text:
        entry = f'\t<SubTexture name="{SPRITE}" x="{X}" y="{Y}" width="{W}" height="{H}" half="0"/>\n'
        text = text.replace("</TextureAtlas>", entry + "</TextureAtlas>")
        Path(layout).write_text(text, encoding="utf-8")
    print(f"{SPRITE} at {X},{Y} {W}x{H}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
