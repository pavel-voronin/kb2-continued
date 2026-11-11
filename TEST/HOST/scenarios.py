"""Compose real game modules in DOS; freeze current continued, never a reference."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from config import ROOT, WORK, limit_host_cpu
from prepare import resources, write


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(record=False):
    limit_host_cpu()
    artwork = resources()
    expected_path = ROOT / "TEST/EXPECT/SCENARIOS.JSON"
    expected = json.loads(expected_path.read_text()) if expected_path.exists() else {}
    folder = WORK / "UNIT/SCENES"
    folder.mkdir(parents=True, exist_ok=True)
    inputs = [
        *sorted((ROOT / "SRC").glob("*.PAS")),
        *sorted(artwork.glob("*")),
        ROOT / "PASCAL/TPC.EXE",
        ROOT / "PASCAL/TURBO.TPL",
        Path(__file__),
        Path(__file__).with_name("dos.ps1"),
    ]
    results = {}
    for name in ("WORLD", "COMBAT"):
        source = ROOT / "TEST/SCENARIOS" / (name + ".PAS")
        fingerprint = hashlib.sha256(
            b"".join(p.name.encode() + p.read_bytes() for p in [*inputs, source])
        ).hexdigest()
        target = folder / name
        cache = target / "CACHE.json"
        prior = json.loads(cache.read_text()) if cache.exists() else {}
        if prior.get("inputs") == fingerprint and all(
            (target / path).is_file() and sha(target / path) == digest
            for path, digest in prior.get("artifacts", {}).items()
        ) and prior.get("artifacts"):
            observed = prior["observed"]
            cached = True
        else:
            code, data = target / "CODE", target / "DATA"
            code.mkdir(parents=True, exist_ok=True)
            data.mkdir(parents=True, exist_ok=True)
            for path in (ROOT / "SRC").glob("*.PAS"):
                shutil.copy2(path, code / path.name)
            shutil.copy2(source, code / source.name)
            for path in artwork.glob("*"):
                if path.is_file():
                    shutil.copy2(path, data / path.name)
            ok = target / "DONE.OK"
            ok.unlink(missing_ok=True)
            write(target / "RUN.BAT", f"""@echo off
cd CODE
..\\..\\..\\..\\PASCAL\\TPC.EXE {name}.PAS /B /L /DSTRUCTURED > ..\\BUILD.LOG
if errorlevel 1 goto failed
cd ..\\DATA
..\\CODE\\{name}.EXE /KEEP
if errorlevel 1 goto failed
echo OK>..\\DONE.OK
:failed
""")
            subprocess.run([
                "pwsh", "-NoProfile", "-File", str(ROOT / "TEST/HOST/dos.ps1"),
                "-Work", str(WORK), "-Core", "normal", "-Cycles", "fixed 3000",
                "-Commands", f"cd UNIT\\SCENES\\{name}\ncall RUN.BAT",
            ], check=True)
            if not ok.exists():
                log = target / "BUILD.LOG"
                detail = log.read_bytes().decode("cp866") if log.exists() else "no build log"
                raise RuntimeError(f"{name}: scenario failed; see {target}\n{detail}")
            if name == "WORLD":
                files = [data / f"{prefix}{level}.DAT" for level in range(4) for prefix in "LR"]
                for level in range(4):
                    original, loaded = (data / f"{p}{level}.DAT" for p in "LR")
                    if original.read_bytes() != loaded.read_bytes() or original.stat().st_size != 27729:
                        raise AssertionError("Campaign did not survive save/load: " + str(level))
                log = data / "REGRESS.LOG"
                if "PASS" not in log.read_text():
                    raise AssertionError("World scenario did not finish")
            else:
                files = [data / "TACTIC.BIN"]
                log = data / "TACTIC.LOG"
                if "16200 strikes, 112 targets, 20 selections, 12 AI phases" not in log.read_text():
                    raise AssertionError("Incomplete combat scenario")
            observed = {p.name: dict(bytes=p.stat().st_size, sha256=sha(p)) for p in files}
            artifacts = {str(p.relative_to(target)): sha(p) for p in [*files, log, code / (name + ".EXE")]}
            prior = dict(inputs=fingerprint, observed=observed, artifacts=artifacts)
            cached = False
        if name not in expected:
            if not record:
                raise AssertionError("Missing current-continued expectation: " + name)
            expected[name] = observed
            expected_path.write_text(json.dumps(expected, indent=2) + "\n", encoding="ascii")
        if observed != expected[name]:
            raise AssertionError(f"{name}: composed behaviour changed; inspect {target}")
        cache.write_text(json.dumps(prior, indent=2), encoding="ascii")
        results[name] = dict(status="pass", cached=cached, observed=observed)
        print("SCENARIO", name, "PASS", "cached" if cached else "DOSBox-X", flush=True)
    (folder / "RESULT.json").write_text(json.dumps(results, indent=2), encoding="ascii")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="Add missing expectations only")
    run(parser.parse_args().record)
