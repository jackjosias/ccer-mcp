"""Génération SVG déterministe depuis le sous-ensemble flowchart LR de Mermaid."""
from pathlib import Path
from collections import defaultdict
from html import escape
import argparse
import re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "architecture.mmd"
OUTPUT = ROOT / "architecture.svg"
N = re.compile(r'^\s*(\w+)\["([^"]+)"\]\s*$')
E = re.compile(r'^\s*(\w+)\s*-->\s*(\w+)\s*$')


def render(source: str) -> str:
    lines = [x for x in source.splitlines() if x.strip()]
    if lines.pop(0).strip() != "flowchart LR":
        raise ValueError("Expected flowchart LR")
    nodes, edges = {}, []
    for line in lines:
        if m := N.fullmatch(line):
            if m[1] in nodes:
                raise ValueError("Duplicate node")
            nodes[m[1]] = m[2]
        elif m := E.fullmatch(line):
            edges.append((m[1], m[2]))
        else:
            raise ValueError("Unsupported Mermaid line: " + line)
    if not nodes or not edges or any(a not in nodes or b not in nodes for a, b in edges):
        raise ValueError("Incomplete diagram")
    depth = dict.fromkeys(nodes, 0)
    for _ in nodes:
        if not any(depth.__setitem__(b, depth[a] + 1) or True for a, b in edges if depth[b] <= depth[a]):
            break
    else:
        raise ValueError("Cycle detected")
    cols = defaultdict(list)
    for key in nodes:
        cols[depth[key]].append(key)
    pos = {key: (45 + level * 236, 190 + int((i - (len(keys)-1)/2)*138))
           for level, keys in cols.items() for i, key in enumerate(keys)}
    width = 130 + (max(depth.values()) + 1)*236
    output = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 430" role="img" aria-labelledby="title desc">',
        '<title id="title">Architecture de CCER et Concat</title>',
        '<desc id="desc">Passerelle MCP vers Concat via contrôles et pont Slint; analyse FFmpeg locale.</desc>',
        '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#55c5cf"/></marker></defs>',
        f'<rect width="{width}" height="430" rx="20" fill="#101b2c"/>',
        '<text x="45" y="46" fill="#5ad3ce" font-family="sans-serif" font-size="13" letter-spacing="3">ARCHITECTURE · LOCAL-FIRST</text>',
        '<text x="45" y="91" fill="#f2f8ff" font-family="sans-serif" font-size="31" font-weight="bold">CCER × Concat</text>',
        '<text x="45" y="120" fill="#a8bdd2" font-family="sans-serif" font-size="15">MCP, fenêtre Concat instrumentée et analyse audiovisuelle</text>',
    ]
    for a, b in edges:
        x, y = pos[a]
        xx, yy = pos[b]
        output.append(f'<path d="M{x+194} {y+36} C{x+214} {y+36} {xx-22} {yy+36} {xx-6} {yy+36}" fill="none" stroke="#55c5cf" stroke-width="2" marker-end="url(#a)"/>')
    for key, label in nodes.items():
        x, y = pos[key]
        color = "#1a4352" if key in ("Gateway", "Concat") else "#1d3049"
        output.extend([
            f'<rect x="{x}" y="{y}" width="192" height="72" rx="13" fill="{color}" stroke="#498da2"/>',
            f'<text x="{x+15}" y="{y+42}" fill="#f4f9ff" font-family="sans-serif" font-size="13.4" font-weight="bold">{escape(label)}</text>',
        ])
    output.extend(['<text x="45" y="407" fill="#8ea7bb" font-family="sans-serif" font-size="12">Le pont Slint nécessite une version de Concat instrumentée.</text>', '</svg>', ''])
    return "\n".join(output)


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = p.parse_args()
    content = render(SOURCE.read_text(encoding="utf-8"))
    if a.write:
        OUTPUT.write_text(content, encoding="utf-8")
        print("Rendered", OUTPUT)
        return 0
    if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != content:
        print("SVG differs from Mermaid source")
        return 1
    print("SVG matches Mermaid source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
