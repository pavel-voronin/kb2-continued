"""Explicit, source-bound proofs for paths that execution cannot visit."""

import hashlib
import json
from pascal import Pascal


def tokens(text):
    return [
        t.text if t.text.startswith("'") else t.text.lower()
        for t in Pascal(text, "proof").tokens
    ]


def source_digest(path):
    return hashlib.sha256(
        json.dumps(
            tokens(path.read_bytes().decode("cp866")), ensure_ascii=True
        ).encode()
    ).hexdigest()


def point_shape(point):
    return dict(
        routine=point["routine"].lower(),
        kind=point["kind"].lower(),
        source=tokens(point["source"]),
    )


def audit(root, index, hits, selected):
    path = root / "TEST/UNREACHABLE.json"
    if not path.exists():
        return [], []
    catalogue = json.loads(path.read_text(encoding="utf-8"))
    groups = {
        name: [p for p in index["points"] if p["file"] == name + ".PAS"]
        for name in index["modules"]
    }
    errors = []
    unreachable = []
    checked = {}

    def check_module(name):
        if name not in checked:
            actual = source_digest(root / "SRC" / f"{name}.PAS")
            checked[name] = actual == catalogue["modules"][name]
            if not checked[name]:
                errors.append("Устарело обоснование: " + name)
        return checked[name]

    for proof in catalogue["proofs"]:
        active = [p for p in proof["points"] if p["module"] in selected]
        if not active:
            continue
        valid = all(check_module(name) for name in proof["depends_on"])
        for entry in active:
            points = groups[entry["module"]]
            number = entry["local_id"] - 1
            if (
                number < 0
                or number >= len(points)
                or point_shape(points[number]) != entry["shape"]
            ):
                errors.append("Изменилась точка обоснования: " + proof["id"])
                continue
            point = points[number]
            if point["id"] in hits:
                errors.append(
                    "Опровергнута недостижимость: "
                    + proof["id"]
                    + " "
                    + str(point["id"])
                )
                continue
            if valid:
                unreachable.append(
                    dict(**point, proof=proof["id"], reason=proof["reason"])
                )
    if any(
        p["module"] in selected
        for proof in catalogue["proofs"]
        for p in proof["points"]
    ):
        for name, digest in catalogue["compiler"].items():
            if (
                hashlib.sha256((root / "PASCAL" / name).read_bytes()).hexdigest()
                != digest
            ):
                errors.append("Изменился компилятор обоснований: " + name)
    ids = [p["id"] for p in unreachable]
    if len(ids) != len(set(ids)):
        errors.append("Повторяющиеся точки в обоснованиях")
    return unreachable, errors
