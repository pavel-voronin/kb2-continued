"""Run short independent module tests and report only their actual coverage."""

import argparse
import hashlib
import inspect
import importlib
import json
import sys
import time
from runtime import UnitVM, INDEX, ROOT, WORK
from cases import cases
from characterise import cases as examples
from matrix import cases as matrices
from resources import cases as resource_cases
from graphics import cases as graphics_cases
from bugs import cases as bug_cases
from combat import cases as combat_cases
from motion import cases as motion_cases
from storage import cases as storage_cases
from adventure import cases as adventure_cases
from reporting import cases as reporting_cases
from calendar import cases as calendar_cases
from shopping import cases as shopping_cases
from application import cases as application_cases
from generation import cases as generation_cases
from bios import cases as bios_cases
from report import write_report
from reachability import audit


def signature(value):
    """Semantic code digest: moving a test to another line is not a change."""

    def stable(item):
        if inspect.iscode(item):
            return dict(
                bytecode=item.co_code.hex(),
                constants=stable(item.co_consts),
                names=item.co_names,
                variables=item.co_varnames,
                free=item.co_freevars,
                cells=item.co_cellvars,
                arguments=(
                    item.co_argcount,
                    item.co_posonlyargcount,
                    item.co_kwonlyargcount,
                ),
                flags=item.co_flags,
                exceptions=item.co_exceptiontable.hex(),
            )
        if isinstance(item, bytes):
            return dict(bytes=item.hex())
        if isinstance(item, tuple):
            return [stable(x) for x in item]
        if isinstance(item, frozenset):
            return dict(set=sorted((stable(x) for x in item), key=repr))
        if isinstance(item, dict):
            return dict(
                mapping=sorted(
                    ((stable(k), stable(v)) for k, v in item.items()), key=repr
                )
            )
        if item is None or isinstance(item, (bool, int, float, str)):
            return item
        return dict(type=type(item).__name__, value=repr(item))

    return json.dumps(stable(value), sort_keys=True, separators=(",", ":")).encode()


def plain(value):
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return True
    if isinstance(value, (tuple, list, set, frozenset)):
        return all(plain(x) for x in value)
    if isinstance(value, dict):
        return all(plain(k) and plain(v) for k, v in value.items())
    return False


def loaded_code(names, complete=True):
    chunks = []
    for name in names:
        module = importlib.import_module(name)
        for key, value in sorted(vars(module).items()):
            if (
                inspect.isfunction(value)
                and value.__module__ == name
                and key != "cases"
            ):
                chunks.append(signature(value.__code__))
                if (
                    complete
                    and plain(value.__defaults__)
                    and plain(value.__kwdefaults__)
                ):
                    chunks.append(signature((value.__defaults__, value.__kwdefaults__)))
            elif inspect.isclass(value) and value.__module__ == name:
                for method in vars(value).values():
                    if inspect.isfunction(method):
                        chunks.append(signature(method.__code__))
                        if (
                            complete
                            and plain(method.__defaults__)
                            and plain(method.__kwdefaults__)
                        ):
                            chunks.append(
                                signature((method.__defaults__, method.__kwdefaults__))
                            )
            elif (
                complete
                and key.isupper()
                and key not in ("INDEX", "ROOT", "WORK")
                and plain(value)
            ):
                chunks.append(signature((key, value)))
    return hashlib.sha256(b"".join(chunks)).hexdigest()


HARNESS = loaded_code(("runtime", "hardware", "cases", "machine", "state"))
HARNESS += signature(
    (
        importlib.import_module("unicorn").__version__,
        importlib.import_module("capstone").__version__,
    )
).hex()
CHARACTERISATION = loaded_code(("characterise",))
FAMILIES = {
    name: loaded_code((name,))
    for name in (
        "cases",
        "characterise",
        "matrix",
        "resources",
        "graphics",
        "bugs",
        "combat",
        "motion",
        "storage",
        "adventure",
        "reporting",
        "calendar",
        "shopping",
        "application",
        "generation",
        "bios",
    )
}
for name in (
    "matrix",
    "combat",
    "bugs",
    "reporting",
    "calendar",
    "shopping",
    "application",
):
    FAMILIES[name] += CHARACTERISATION


def run(modules=None, record=False):
    stale = [
        name
        for name, meta in INDEX["modules"].items()
        if hashlib.sha256((ROOT / "SRC" / f"{name}.PAS").read_bytes()).hexdigest()
        != meta["sha256"]
    ]
    assert not stale, ("Rebuild unit hosts after source changes", stale)
    selected = (
        list(dict.fromkeys(m.upper() for m in modules))
        if modules
        else list(INDEX["modules"])
    )
    assert all(name in INDEX["modules"] for name in selected), (
        "Unknown module",
        selected,
    )
    points = {p["id"]: p for p in INDEX["points"]}
    hits = set()
    results = []
    asm_hits = {}
    asm_edges = {}
    for module in selected:
        tests = (
            list(cases(module))
            + list(examples(module))
            + list(matrices(module))
            + list(resource_cases(module))
            + list(graphics_cases(module))
            + list(bug_cases(module))
            + list(combat_cases(module))
            + list(motion_cases(module))
            + list(storage_cases(module))
            + list(adventure_cases(module))
            + list(reporting_cases(module))
            + list(calendar_cases(module))
            + list(shopping_cases(module))
            + list(application_cases(module))
            + list(generation_cases(module))
            + list(bios_cases(module))
        )
        if not tests:
            continue
        expected_path = ROOT / "TEST/EXPECT" / f"{module}.JSON"
        expected = (
            json.loads(expected_path.read_text()) if expected_path.exists() else {}
        )
        cache_path = WORK / "UNIT/CACHE" / f"{module}.JSON"
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        binary = hashlib.sha256(
            (WORK / "UNIT" / module / "CODE/SGHOST.EXE").read_bytes()
        ).hexdigest()
        data = WORK / "UNIT" / module / "DATA"
        binary += hashlib.sha256(
            b"".join(
                p.name.encode() + hashlib.sha256(p.read_bytes()).digest()
                for p in sorted(data.iterdir())
                if p.is_file()
            )
        ).hexdigest()
        runtime = HARNESS
        vm = None
        reused = 0
        for test in tests:
            identity = (test.identity or repr(test.run.__defaults__)) + FAMILIES[
                test.run.__module__
            ]
            code = hashlib.sha256(signature(test.run.__code__)).hexdigest()
            fingerprint = hashlib.sha256(
                (
                    binary
                    + runtime
                    + code
                    + identity
                    + json.dumps(expected.get(test.name), sort_keys=True)
                ).encode()
            ).hexdigest()
            prior = cache.get(test.name)
            if (
                prior
                and prior["fingerprint"] == fingerprint
                and prior["result"]["status"] == "pass"
            ):
                hits.update(prior["hits"])
                results.append(prior["result"])
                asm_hits.setdefault(module, set()).update(
                    prior.get("assembly_hits", [])
                )
                asm_edges.setdefault(module, set()).update(
                    prior.get("assembly_edges", [])
                )
                reused += 1
                continue
            if vm is None:
                vm = UnitVM(module)
            started = time.monotonic()
            try:
                output = test.run(vm)
                if output is not None:
                    output = json.loads(json.dumps(output))
                    if test.name not in expected:
                        assert record, ("Missing frozen expectation", test.name)
                        expected[test.name] = output
                    if record:
                        for key, value in output.items():
                            if key not in expected[test.name]:
                                expected[test.name][key] = value
                    if output != expected[test.name]:
                        failures = WORK / "UNIT/FAILURES"
                        failures.mkdir(exist_ok=True)
                        artifact = failures / (
                            module
                            + "-"
                            + hashlib.sha256(test.name.encode()).hexdigest()[:16]
                            + ".JSON"
                        )
                        artifact.write_text(
                            json.dumps(
                                dict(
                                    test=test.name,
                                    actual=output,
                                    expected=expected[test.name],
                                ),
                                ensure_ascii=True,
                                indent=2,
                            ),
                            encoding="ascii",
                        )
                        fields = [
                            k
                            for k in output.keys() | expected[test.name].keys()
                            if output.get(k) != expected[test.name].get(k)
                        ]
                        raise AssertionError(
                            (
                                "Characterisation differs",
                                test.name,
                                fields,
                                str(artifact),
                            )
                        )
                hits.update(vm.hits)
                hits.update(vm.boot_hits)
                asm_hits.setdefault(module, set()).update(vm.asm_hits)
                asm_edges.setdefault(module, set()).update(vm.asm_edges)
                result = dict(
                    module=module,
                    name=test.name,
                    status="pass",
                    seconds=time.monotonic() - started,
                )
                results.append(result)
                fingerprint = hashlib.sha256(
                    (
                        binary
                        + runtime
                        + code
                        + identity
                        + json.dumps(expected.get(test.name), sort_keys=True)
                    ).encode()
                ).hexdigest()
                cache[test.name] = dict(
                    version=3,
                    fingerprint=fingerprint,
                    result=result,
                    hits=list(vm.hits.keys() | vm.boot_hits.keys()),
                    assembly_hits=sorted(vm.asm_hits),
                    assembly_edges=sorted(vm.asm_edges),
                )
            except Exception as error:
                results.append(
                    dict(
                        module=module,
                        name=test.name,
                        status="fail",
                        error=repr(error),
                        seconds=time.monotonic() - started,
                    )
                )
                print("FAIL", module, test.name, repr(error), flush=True)
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        if record:
            names = {test.name for test in tests}
            expected = {
                name: value for name, value in expected.items() if name in names
            }
            expected_path.write_text(
                json.dumps(expected, ensure_ascii=True, indent=2), encoding="ascii"
            )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
        print(
            module,
            sum(r["status"] == "pass" for r in results if r["module"] == module),
            "/",
            len(tests),
            "cached",
            reused,
            flush=True,
        )
        del vm
    coverage = []
    unreachable, audit_errors = audit(ROOT, INDEX, hits, selected)
    unreachable_ids = {p["id"] for p in unreachable}
    for module in INDEX["modules"]:
        entries = [p for p in points.values() if p["file"] == module + ".PAS"]
        covered = [p for p in entries if p["id"] in hits]
        asm_path = WORK / "UNIT/ASSEMBLY" / f"{module}.JSON"
        assembly = json.loads(asm_path.read_text()) if asm_path.exists() else {}
        instructions = [i for block in assembly.values() for i in block]
        edges = [
            f"{point}:{i[0]}:{direction}"
            for point, block in assembly.items()
            for i in block
            if i[2] != "jmp" and (i[2].startswith("j") or i[2].startswith("loop"))
            for direction in (0, 1)
        ]
        coverage.append(
            dict(
                module=module,
                total=len(entries),
                covered=len(covered),
                unreachable=[p for p in unreachable if p["file"] == module + ".PAS"],
                unexplained_missing=[
                    p
                    for p in entries
                    if p["id"] not in hits and p["id"] not in unreachable_ids
                ],
                assembly_instructions=len(instructions),
                assembly_covered=sum(
                    i[0] in asm_hits.get(module, set()) for i in instructions
                ),
                assembly_edges=len(edges),
                assembly_edges_covered=sum(
                    e in asm_edges.get(module, set()) for e in edges
                ),
                assembly_missing=[
                    i for i in instructions if i[0] not in asm_hits.get(module, set())
                ],
                assembly_missing_edges=[
                    e for e in edges if e not in asm_edges.get(module, set())
                ],
                missing=[p for p in entries if p["id"] not in hits],
            )
        )
    scope = [p for p in points.values() if p["file"][:-4] in selected]
    from collections import Counter

    kinds = Counter(p["kind"] for p in scope)
    covered_kinds = Counter(p["kind"] for p in scope if p["id"] in hits)
    scoped_covered = sum(p["id"] in hits for p in scope)
    report = dict(
        tests=results,
        coverage=coverage,
        covered=scoped_covered,
        total=len(scope),
        all_total=len(points),
        selected=selected,
        scope_total=len(scope),
        scope_covered=sum(p["id"] in hits for p in scope),
        unreachable=unreachable,
        audit_errors=audit_errors,
        reachable_total=len(scope) - len(unreachable),
        reachable_covered=scoped_covered,
        kinds={k: dict(total=n, covered=covered_kinds[k]) for k, n in kinds.items()},
        assembly_scope="Compiled instruction and conditional-edge coverage",
        omitted_programs=[],
    )
    selected_coverage = [c for c in coverage if c["module"] in selected]
    report["complete"] = not (
        audit_errors
        or any(t["status"] != "pass" for t in results)
        or any(
            c["unexplained_missing"]
            or c["assembly_missing"]
            or c["assembly_missing_edges"]
            for c in selected_coverage
        )
        or any(not any(t["module"] == name for t in results) for name in selected)
    )
    (WORK / "UNIT/RESULT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(report, WORK / "UNIT", ROOT)
    print(
        "COVERAGE",
        report["scope_covered"],
        "/",
        len(scope),
        round(100 * report["scope_covered"] / len(scope), 2) if scope else 100,
        "%",
        flush=True,
    )
    print(
        "REACHABLE",
        report["reachable_covered"],
        "/",
        report["reachable_total"],
        "UNREACHABLE",
        len(unreachable),
        flush=True,
    )
    for error in audit_errors:
        print("COVERAGE AUDIT FAIL", error, flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", nargs="+")
    parser.add_argument(
        "--record",
        action="store_true",
        help="Record only missing expectations for continued; preserve existing values",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless all selected Pascal and assembly points are covered",
    )
    parser.add_argument(
        "--allow-coverage-gaps",
        action="store_true",
        help="Development only: allow incomplete coverage",
    )
    args = parser.parse_args()
    report = run(args.module, record=args.record)
    failed = any(r["status"] == "fail" for r in report["tests"])
    if args.require_complete or not args.allow_coverage_gaps:
        if not report["complete"]:
            print("COVERAGE INCOMPLETE", flush=True)
        failed |= not report["complete"]
    sys.exit(int(failed))
