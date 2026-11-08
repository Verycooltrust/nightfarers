"""Read an HKLib behaviour XML (Havok 2018 tagfile) into a compact node graph, for comparing NR and ER graphs.

  python behgraph.py <beh.xml> <out.json>
Each object: {"type", "name", "animId", "kids": [object ids it points to]}.
"""
import json
import sys
import xml.etree.ElementTree as ET


def main(src, out):
    root = ET.parse(src).getroot()
    types = {t.get("id"): t.find("name").get("value") for t in root.iter("type") if t.find("name") is not None}
    nodes = {}
    for obj in root.iter("object"):
        rec = obj.find("record")
        node = {"type": types.get(obj.get("typeid"), "?"), "kids": []}
        if rec is not None:
            for f in rec.findall("field"):
                n = f.get("name")
                if n == "name" and f.find("string") is not None:
                    node["name"] = f.find("string").get("value")
                elif n == "animId" and f.find("integer") is not None:
                    node["animId"] = int(f.find("integer").get("value"))
            node["kids"] = [p.get("id") for p in rec.iter("pointer") if p.get("id") != "object0"]
        nodes[obj.get("id")] = node
    json.dump(nodes, open(out, "w"), separators=(",", ":"))
    print(len(nodes), "objects")


if __name__ == "__main__":
    main(*sys.argv[1:3])
