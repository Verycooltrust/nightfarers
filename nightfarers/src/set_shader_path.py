"""Rewrite Nightreign MATBIN XML shader paths to Elden Ring's full form.

Usage: python set_shader_path.py <file.matbin.xml>...
"""
import re
import sys

ER_SPX_DIR = "N:\\GR\\data\\Material\\sat\\OutputData\\SPX\\"

for path in sys.argv[1:]:
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    text = re.sub(r"<ShaderPath>(C\[[^<]*\.spx)</ShaderPath>",
                  lambda m: "<ShaderPath>" + ER_SPX_DIR + m.group(1) + "</ShaderPath>", text)
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(text)
