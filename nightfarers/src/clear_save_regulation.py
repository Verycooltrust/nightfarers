"""Empty the regulation copy Elden Ring keeps inside a save file (BND4 entry USER_DATA011).

The game checks shop rows against that copy and hides any modded row that doesn't match it. ME3 stops the game
from writing the mod's regulation into the save, so the old vanilla copy stays there unless it is cleared.
Each save entry starts with an MD5 of the rest of the entry; it is recomputed here.

Usage: python clear_save_regulation.py <save.sl2>   (use only on the mod's own save, e.g. NF0000.sl2)
"""
import hashlib
import struct
import sys

REGULATION_ENTRY = 11

path = sys.argv[1]
with open(path, "rb") as f:
    save = bytearray(f.read())
assert save[:4] == b"BND4", "not an Elden Ring PC save"
header_size = struct.unpack_from("<q", save, 0x20)[0]
entry = 0x40 + REGULATION_ENTRY * header_size
size = struct.unpack_from("<q", save, entry + 8)[0]
offset = struct.unpack_from("<i", save, entry + 0x10)[0]

data = bytes(size - 16)
save[offset:offset + size] = hashlib.md5(data).digest() + data
with open(path, "wb") as f:
    f.write(save)
print(f"cleared entry {REGULATION_ENTRY} ({size} bytes at {offset:#x}) in {path}")
