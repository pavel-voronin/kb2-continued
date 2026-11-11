"""Parse executable TP7 statements; preserve expressions and assembly verbatim."""

from dataclasses import dataclass, field
import re


@dataclass
class Token:
    text: str
    start: int
    end: int
    line: int


@dataclass
class Node:
    kind: str
    start: int
    end: int
    children: list = field(default_factory=list)
    expr: tuple | None = None
    labels: list = field(default_factory=list)


@dataclass
class Routine:
    name: str
    header: str
    body: Node
    parent: str | None


class Pascal:
    def __init__(self, source, name):
        self.source, self.name = source, name
        pattern = r"\{.*?\}|\(\*.*?\*\)|//[^\n]*|'(?:[^']|'')*'|\$[0-9a-fA-F]+|[A-Za-z_][A-Za-z_0-9]*|\d+|:=|\.\.|<>|<=|>=|[^\s]"
        self.tokens = [
            Token(m.group(), m.start(), m.end(), source.count("\n", 0, m.start()) + 1)
            for m in re.finditer(pattern, source, re.S)
            if m.group().startswith("{$") or not m.group().startswith(("{", "(*", "//"))
        ]
        self.routines = []
        self.points = []
        self.offset = 0

    def at(self, i):
        return self.tokens[i].text.lower() if i < len(self.tokens) else "<eof>"

    def text(self, start, end):
        return (
            self.source[self.tokens[start].start : self.tokens[end - 1].end]
            if end > start
            else ""
        )

    def until(self, i, words):
        depth = 0
        while i < len(self.tokens):
            t = self.at(i)
            if not depth and t in words:
                return i
            if t in ("(", "["):
                depth += 1
            elif t in (")", "]"):
                depth -= 1
            i += 1
        raise ValueError((self.name, "Expected", words))

    def sequence(self, i, ends):
        nodes = []
        while self.at(i) not in ends:
            if self.at(i) == ";":
                i += 1
                continue
            n = self.statement(i)
            if n.end <= i:
                raise ValueError((self.name, i, "No progress"))
            nodes.append(n)
            i = n.end
        return nodes, i

    def statement(self, i):
        start, t = i, self.at(i)
        if t.startswith("{$"):
            j = i + 1
            while self.at(j).startswith("{$"):
                j += 1
            if self.at(j) in (";", "end", "else", "until"):
                return Node("directive", start, j)
            child = self.statement(j)
            return Node("prefix", start, child.end, [child])
        if t == "begin":
            children, j = self.sequence(i + 1, {"end"})
            return Node("begin", start, j + 1, children)
        if t == "asm":
            j = self.until(i + 1, {"end"})
            return Node("asm", start, j + 1)
        if t == "if":
            j = self.until(i + 1, {"then"})
            child = self.statement(j + 1)
            children = [child]
            end = child.end
            if self.at(end) == "else":
                other = self.statement(end + 1)
                children.append(other)
                end = other.end
            return Node("if", start, end, children, (i + 1, j))
        if t in ("while", "for", "with"):
            j = self.until(i + 1, {"do"})
            child = self.statement(j + 1)
            return Node(t, start, child.end, [child], (i + 1, j))
        if t == "repeat":
            children, j = self.sequence(i + 1, {"until"})
            end = self.until(j + 1, {";", "end", "else", "until"})
            return Node("repeat", start, end, children, (j + 1, end))
        if t == "case":
            j = self.until(i + 1, {"of"})
            expr = i + 1, j
            children, labels = [], []
            j += 1
            while self.at(j) not in ("end", "else"):
                if self.at(j) == ";":
                    j += 1
                    continue
                colon = self.until(j, {":"})
                labels.append(self.text(j, colon))
                child = self.statement(colon + 1)
                children.append(child)
                j = child.end
            if self.at(j) == "else":
                others, j = self.sequence(j + 1, {"end"})
                children.append(Node("sequence", start, j, others))
                labels.append("else")
            return Node("case", start, j + 1, children, expr, labels)
        if self.at(i + 1) == ":":
            child = self.statement(i + 2)
            return Node(
                "label", start, child.end, [child], labels=[self.tokens[i].text]
            )
        if t in (";", "end", "else", "until"):
            return Node("empty", i, i)
        j = self.until(i, {";", "end", "else", "until"})
        return Node("simple", start, j)

    def routine(self, i, parent=None):
        start = i
        name = self.tokens[i + 1].text
        j = self.until(i + 2, {";"})
        header = self.text(start, j + 1)
        j += 1
        while self.at(j) in ("assembler", "far", "near", "interrupt", "forward"):
            qualifier = self.at(j)
            j = self.until(j + 1, {";"}) + 1
            if qualifier == "forward":
                return j
        while self.at(j) not in ("begin", "asm"):
            if self.at(j) in ("procedure", "function"):
                j = self.routine(j, name if parent is None else parent + "." + name)
            else:
                j += 1
            if j >= len(self.tokens):
                raise ValueError((self.name, name, "Missing body"))
        body = self.statement(j)
        self.routines.append(Routine(name, header, body, parent))
        return body.end + (self.at(body.end) == ";")

    def parse(self):
        unit = self.at(0) == "unit"
        i = (
            next(i for i in range(len(self.tokens)) if self.at(i) == "implementation")
            + 1
            if unit
            else 3
        )
        while i < len(self.tokens):
            if self.at(i) in ("procedure", "function"):
                i = self.routine(i)
            elif self.at(i) == "begin":
                self.routines.append(
                    Routine("$init" if unit else "$main", "", self.statement(i), None)
                )
                break
            else:
                i += 1
        return self

    def point(self, node, kind, owner):
        number = self.offset + len(self.points) + 1
        self.points.append(
            dict(
                id=number,
                file=self.name,
                routine=owner,
                line=self.tokens[node.start].line,
                kind=kind,
                source=self.text(node.start, min(node.end, node.start + 16)),
            )
        )
        return number

    def emit(self, n, owner):
        kind = n.kind
        if kind == "empty":
            return "begin end"
        if kind == "directive":
            return self.text(n.start, n.end)
        if kind == "prefix":
            return (
                self.text(n.start, n.children[0].start)
                + "\n"
                + self.emit(n.children[0], owner)
            )
        if kind in ("begin", "sequence"):
            return (
                "begin\n"
                + ";\n".join(self.emit(c, owner) for c in n.children)
                + "\nend"
            )
        if kind == "label":
            return n.labels[0] + ": " + self.emit(n.children[0], owner)
        point = self.point(n, "assembly" if kind == "asm" else "statement", owner)
        if kind == "asm":
            raw = self.text(n.start, n.end)
            marker = (
                "\n pushf\n pusha\n push ds\n push es\n mov ax, $f120\n"
                f" mov bx, {point}\n int $f0\n pop es\n pop ds\n popa\n popf\n"
            )
            ending = marker.replace("$f120", "$f122")
            return raw[:3] + marker + raw[3:-3] + ending + raw[-3:]
        hit = f"UHit({point});\n"
        if kind == "simple":
            return "begin " + hit + self.text(n.start, n.end) + " end"
        if kind in ("if", "while", "repeat"):
            yes, no = (
                self.point(n, "branch-true", owner),
                self.point(n, "branch-false", owner),
            )
            condition = f"UBranch({yes}, {no}, ({self.text(*n.expr)}))"
            if kind == "if":
                body = "if " + condition + " then " + self.emit(n.children[0], owner)
                if len(n.children) == 2:
                    body += " else " + self.emit(n.children[1], owner)
            elif kind == "while":
                body = "while " + condition + " do " + self.emit(n.children[0], owner)
            else:
                body = (
                    "repeat\n"
                    + ";\n".join(self.emit(c, owner) for c in n.children)
                    + "\nuntil "
                    + condition
                )
            return "begin " + hit + body + " end"
        if kind in ("for", "with"):
            body = self.emit(n.children[0], owner)
            if kind == "for":
                yes, no = (
                    self.point(n, "loop-body", owner),
                    self.point(n, "loop-exit", owner),
                )
                body = f"begin UHit({yes}); {body} end; UHit({no})"
            return (
                "begin "
                + hit
                + kind
                + " "
                + self.text(*n.expr)
                + " do "
                + body
                + " end"
            )
        if kind == "case":
            parts = []
            for label, child in zip(n.labels, n.children):
                arm = self.point(child, "case-" + label, owner)
                prefix = "else " if label == "else" else label + ": "
                parts.append(
                    prefix + f"begin UHit({arm}); " + self.emit(child, owner) + " end;"
                )
            if "else" not in n.labels:
                arm = self.point(n, "case-unmatched", owner)
                parts.append(f"else UHit({arm});")
            return (
                "begin "
                + hit
                + "case "
                + self.text(*n.expr)
                + " of\n"
                + "\n".join(parts)
                + "\nend end"
            )
        raise ValueError(kind)

    def instrument(self):
        patches = []
        # Nested routines have disjoint body ranges; the parent's declarations stay intact.
        for r in self.routines:
            if r.name == "$init" and not r.body.children:
                continue
            owner = (r.parent + "." if r.parent else "") + r.name
            body = self.emit(r.body, owner)
            if r.body.kind == "begin":
                entry = self.point(r.body, "routine", owner)
                body = body[:5] + f"\nUHit({entry});" + body[5:]
            patches.append(
                (self.tokens[r.body.start].start, self.tokens[r.body.end - 1].end, body)
            )
        output = self.source
        for start, end, text in sorted(patches, reverse=True):
            output = output[:start] + text + output[end:]
        return output
