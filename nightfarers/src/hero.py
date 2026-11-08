"""Hero manifest (heroes/<name>.toml), for the generators.

  python hero.py <manifest> <dotted.key> [separator]   print one value; lists are joined by the separator (default ",")
"""
import os
import sys
import tomllib
from pathlib import Path


def load(path=None):
    """The manifest at `path`, else $NF_HERO, else Wylder's."""
    path = path or os.environ.get("NF_HERO") or Path(__file__).resolve().parent.parent / "heroes" / "wylder.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)


if __name__ == "__main__":
    value = load(sys.argv[1])
    for key in sys.argv[2].split("."):
        value = value[key]
    sep = sys.argv[3] if len(sys.argv) > 3 else ","
    if isinstance(value, list) and value and isinstance(value[0], list):  # pairs: old=new
        value = [f"{a}={b}" for a, b in value]
    print(sep.join(map(str, value)) if isinstance(value, list) else value)
