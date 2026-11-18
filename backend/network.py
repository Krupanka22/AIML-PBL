import os
import random
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / "sumo"
SIGNALS = "ABCD"
KINDS = {"car": ("passenger", 4.5, 15, 2.6), "motorcycle": ("motorcycle", 2, 17, 3),
         "bus": ("bus", 12, 12, 1.3), "auto": ("passenger", 2.8, 11, 2), "truck": ("truck", 9, 11, 1.2)}


def binary(name):
    candidates = [Path(sys.executable).parent, Path(os.environ.get("SUMO_HOME", ".")) / "bin",
                  Path(sys.prefix) / "Lib/site-packages/sumo/bin"]
    for folder in candidates:
        for suffix in (".exe", ""):
            if (folder / (name + suffix)).is_file():
                return str(folder / (name + suffix))
    return shutil.which(name) or name


def write(root, filename):
    ET.indent(root)
    ET.ElementTree(root).write(NETWORK / filename, encoding="utf-8", xml_declaration=True)


def build():
    NETWORK.mkdir(exist_ok=True)
    nodes, edges, routes = ET.Element("nodes"), ET.Element("edges"), ET.Element("routes")
    points = {"W": (0, 0), "E": (1500, 0)}
    for i, s in enumerate(SIGNALS, 1):
        for suffix, y in [("", 0), ("N", 150), ("S", -150)]:
            points[s + suffix] = (300 * i, y)
    for name, (x, y) in points.items():
        ET.SubElement(nodes, "node", id=name, x=str(x), y=str(y), type="traffic_light" if name in SIGNALS else "priority")
    pairs = list(zip("WABCD", "ABCDE")) + [(s, s + d) for s in SIGNALS for d in "NS"]
    for a, b in pairs:
        for start, end in [(a, b), (b, a)]:
            ET.SubElement(edges, "edge", id=start+"_"+end, attrib={"from": start, "to": end}, numLanes="2", speed="15")
    for kind, (vclass, length, speed, accel) in KINDS.items():
        ET.SubElement(routes, "vType", id=kind, vClass=vclass, length=str(length), maxSpeed=str(speed), accel=str(accel))
    write(nodes, "nodes.xml")
    write(edges, "edges.xml")
    write(routes, "types.xml")
    subprocess.run([binary("netconvert"), "-n", "nodes.xml", "-e", "edges.xml", "--no-turnarounds", "true",
                    "--lefthand", "true", "-o", "corridor.net.xml"], cwd=NETWORK, check=True)


def itinerary(rng, origin):
    chain = list("WABCDE")
    if origin in ("W", "E"):
        road = chain if origin == "W" else chain[::-1]
        stop = rng.randint(1, 4) if rng.random() < .35 else 5
        nodes = road[:stop+1]
        if stop < 5:
            nodes.append(nodes[-1] + rng.choice("NS"))
    else:
        signal = origin[0]
        if rng.random() < .6:
            nodes = [origin, signal, signal + ("S" if origin.endswith("N") else "N")]
        else:
            road = chain if rng.random() < .5 else chain[::-1]
            nodes = [origin] + road[road.index(signal):]
    return [a+"_"+b for a,b in zip(nodes,nodes[1:])]
