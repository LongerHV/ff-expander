"""Minimal KiCad s-expression reader/writer."""
import re

_TOK = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


class Q(str):
    """A quoted string atom."""


def parse(text):
    stack, cur, pos = [], [], 0
    while True:
        m = _TOK.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            done, cur = cur, stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            cur.append(Q(m.group(3).replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")))
        else:
            cur.append(m.group(4))
    return cur[0]


def dump(node, indent=0):
    if isinstance(node, Q):
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if not isinstance(node, list):
        return str(node)
    simple = all(not isinstance(c, list) for c in node)
    if simple:
        return "(" + " ".join(dump(c) for c in node) + ")"
    pad = "\t" * (indent + 1)
    out = "(" + dump(node[0])
    for c in node[1:]:
        out += "\n" + pad + dump(c, indent + 1) if isinstance(c, list) else " " + dump(c)
    return out + "\n" + "\t" * indent + ")"


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]
