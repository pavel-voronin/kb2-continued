"""Build isolated TP7 dispatchers from instrumented copies, never edit SRC."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
from config import WORK, limit_host_cpu
from pascal import Pascal

limit_host_cpu()
UNIT = WORK / "UNIT"

COV = """unit UCov;
{$G+,R-,S-,A+}
interface
type TUArgs = array[0..63] of longint; PUArgs = ^TUArgs;
procedure UHit(Id: word);
function UBranch(Yes, No: word; Value: boolean): boolean;
procedure UMark(Kind: word; P: pointer);
procedure UAwait;
implementation
procedure UHit(Id: word);
begin asm
 pushf
 pusha
 push ds
 push es
 mov ax, $f120
 mov bx, Id
 int $f0
 pop es
 pop ds
 popa
 popf
end end;
function UBranch(Yes, No: word; Value: boolean): boolean;
begin
 if Value then UHit(Yes) else UHit(No);
 UBranch := Value;
end;
procedure UMark(Kind: word; P: pointer);
begin asm mov ax, Kind; les bx, P; int $f0 end end;
procedure UAwait;
begin asm mov ax, $f140; int $f0 end end;
end.
"""
IO = """unit UIO;
interface
function ReadKey: char;
function KeyPressed: boolean;
procedure Delay(MS: word);
procedure Sound(Hz: word);
procedure NoSound;
implementation
function ReadKey: char; assembler;
asm mov ax,$f150; int $f0 end;
function KeyPressed: boolean; assembler;
asm mov ax,$f151; int $f0 end;
procedure Delay(MS: word); begin asm mov ax,$f160; mov bx,MS; int $f0 end end;
procedure Sound(Hz: word); begin asm mov ax,$f161; mov bx,Hz; int $f0 end end;
procedure NoSound; begin asm mov ax,$f162; xor bx,bx; int $f0 end end;
end.
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        while len(line) > 120:
            spaces = [
                m.start()
                for m in re.finditer(r"'(?:[^']|'')*'|\s+", line)
                if m.group().isspace() and 0 < m.start() <= 116
            ]
            if not spaces:
                break
            cut = spaces[-1]
            lines.append(line[:cut])
            line = "  " + line[cut:].lstrip()
        lines.append(line)
    text = "\n".join(lines)
    data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("cp866")
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def signature(header):
    match = re.match(
        r"(procedure|function)\s+(\w+)\s*(?:\((.*?)\))?\s*(?::\s*(\w+))?;",
        header,
        re.S | re.I,
    )
    if not match:
        raise ValueError(header)
    kind, name, params, result = match.groups()
    args = []
    for group in (params or "").split(";"):
        if not group.strip():
            continue
        mode = "var" if group.strip().lower().startswith("var ") else "value"
        group = re.sub(r"^\s*var\s+", "", group, flags=re.I)
        names, typ = group.split(":", 1) if ":" in group else (group, "byte")
        args.extend(
            dict(name=n.strip(), type=typ.strip(), mode=mode) for n in names.split(",")
        )
    return dict(
        name=name, args=args, result=result if kind.lower() == "function" else None
    )


def dispatch(routines):
    declarations, cases, entries = {}, [], []
    for routine in routines:
        if routine.parent or not routine.header:
            continue
        entry = signature(routine.header)
        entry["op"] = len(entries) + 1
        args = []
        for i, arg in enumerate(entry["args"]):
            typ = arg["type"]
            value = f"A^[{i}]"
            if arg["mode"] == "var" or typ.lower() not in (
                "byte",
                "word",
                "shortint",
                "integer",
                "longint",
                "boolean",
                "char",
                "pointer",
            ):
                alias = "UTP" + typ
                declarations[alias] = typ
                value = f"{alias}({value})^"
            else:
                value = f"{typ}({value})"
            args.append(value)
        call = entry["name"] + ("(" + ", ".join(args) + ")" if args else "")
        if entry["result"]:
            if entry["result"].lower() == "string":
                declarations["UTPstring"] = "string"
                call = f"UTPstring(A^[31])^ := " + call
            else:
                call = "A^[31] := Longint(" + call + ")"
        cases.append(f"{entry['op']}: {call};")
        entries.append(entry)
    if not entries:
        return "\nprocedure UDispatch(Op: word; AP: pointer); begin end;\n", []
    text = (
        "\ntype\n"
        + "\n".join(f" {alias} = ^{typ};" for alias, typ in declarations.items())
        if declarations
        else ""
    )
    text += "\nprocedure UDispatch(Op: word; AP: pointer);\nvar A: PUArgs;\nbegin\n A := AP;\n case Op of\n"
    return text + "\n".join(cases) + "\n end;\nend;\n", entries


def resources():
    """Build fixture artwork from the checked-in PCX, without search builds."""
    compiler = WORK / "PASCAL"
    compiler.mkdir(parents=True, exist_ok=True)
    for name in ("TPC.EXE", "TURBO.TPL"):
        src = ROOT / "PASCAL" / name
        dest = compiler / name
        if not dest.exists() or dest.read_bytes() != src.read_bytes():
            shutil.copy2(src, dest)
    folder = UNIT / "ASSETS"
    folder.mkdir(parents=True, exist_ok=True)
    inputs = [
        ROOT / "SRC/RSPACK.PAS",
        ROOT / "SRC/PACK.LST",
        *sorted((ROOT / "SRC/ART").glob("*.PCX")),
        ROOT / "PASCAL/TPC.EXE",
        ROOT / "PASCAL/TURBO.TPL",
    ]
    fingerprint = hashlib.sha256(
        b"".join(p.name.encode() + p.read_bytes() for p in inputs)
    ).hexdigest()
    manifest = folder / "CACHE.json"
    prior = json.loads(manifest.read_text()) if manifest.exists() else {}
    valid = prior.get("inputs") == fingerprint and all(
        (folder / "DIST" / name).exists()
        and hashlib.sha256((folder / "DIST" / name).read_bytes()).hexdigest() == digest
        for name, digest in prior.get("outputs", {}).items()
    )
    if valid and prior.get("outputs"):
        return folder / "DIST"
    for path in inputs[:-2]:
        dest = folder / ("ART" if path.suffix == ".PCX" else "") / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    (folder / "DIST").mkdir(exist_ok=True)
    (folder / "DONE.OK").unlink(missing_ok=True)
    write(
        folder / "ASSETS.BAT",
        """@echo off
..\\..\\PASCAL\\TPC.EXE RSPACK.PAS /B /L > BUILD.LOG
if errorlevel 1 goto done
RSPACK.EXE > PACK.LOG
if errorlevel 1 goto done
echo OK>DONE.OK
:done
""",
    )
    subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(ROOT / "TEST/HOST/dos.ps1"),
            "-Work",
            str(WORK),
            "-Commands",
            "cd UNIT\\ASSETS\ncall ASSETS.BAT",
        ],
        check=True,
    )
    if not (folder / "DONE.OK").exists():
        raise RuntimeError("Unit fixture artwork build failed: " + str(folder))
    outputs = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (folder / "DIST").iterdir()
        if p.is_file()
    }
    manifest.write_text(
        json.dumps(dict(inputs=fingerprint, outputs=outputs), indent=2),
        encoding="ascii",
    )
    return folder / "DIST"


def prepare():
    artwork = resources()
    source = UNIT / "SRC"
    source.mkdir(parents=True, exist_ok=True)
    points, modules = [], {}
    for path in sorted((ROOT / "SRC").glob("*.PAS")):
        original = path.read_bytes().decode("cp866").replace("\r\n", "\n")
        if original.lower().startswith("program "):
            program = Pascal(original, path.name).parse()
            main = program.routines[-1].body
            start = program.tokens[main.start].start
            end = program.tokens[main.end - 1].end
            original = (
                original[:start]
                + "procedure UMain; "
                + original[start:end]
                + "; end.\n"
            )
            original = re.sub(
                r"^program\s+\w+;", f"unit {path.stem};", original, count=1, flags=re.I
            )
            original = re.sub(r"\{\$M[^}]*\}", "", original, flags=re.I)
            declarations = re.match(
                r"^unit\s+\w+;\s*(?:\{.*?\}\s*)*", original, re.S | re.I
            ).end()
            original = (
                original[:declarations]
                + "interface implementation "
                + original[declarations:]
            )
        parser = Pascal(original, path.name).parse()
        parser.offset = len(points)
        transformed = parser.instrument()
        points.extend(parser.points)
        body, entries = dispatch(parser.routines)
        data_types = {
            "KBTYPES": [
                "TDirection",
                "TPosition",
                "TContract",
                "TRelic",
                "TCreatureDefinition",
                "TCreatureCost",
            ],
            "KBBTYPE": [
                "TReserveState",
                "TEnemyAIState",
                "TCombatUnit",
                "TBattleState",
            ],
            "KBSTATE": ["TGameState", "TCampaignState", "TCampaignFlags"],
            "KBTABLES": ["CreatureDefinitions"],
        }.get(path.stem)
        if data_types:
            entries = [
                dict(name="SizeOf" + name, args=[], result="word", op=i + 1)
                for i, name in enumerate(data_types)
            ]
            body = "\nprocedure UDispatch(Op: word; AP: pointer);\nvar A: PUArgs;\nbegin A:=AP;\ncase Op of\n"
            body += (
                "\n".join(
                    f"{i + 1}: A^[31]:=SizeOf({name});"
                    for i, name in enumerate(data_types)
                )
                + "\nend end;\n"
            )
        interface_pos = transformed.lower().index("interface") + len("interface")
        tail = transformed[interface_pos:]
        uses = re.match(r"\s*uses\s+", tail, re.I)
        if uses:
            pos = interface_pos + uses.end()
            transformed = transformed[:pos] + "UCov, " + transformed[pos:]
        else:
            transformed = transformed[:interface_pos] + "\nuses UCov;\n" + tail
        pos = transformed.lower().index("implementation")
        public = set(
            re.findall(r"\b(?:procedure|function)\s+(\w+)", transformed[:pos], re.I)
        )
        exports = "\n".join(
            r.header
            for r in parser.routines
            if r.header and not r.parent and r.name not in public
        )
        transformed = (
            transformed[:pos]
            + exports
            + "\nprocedure UDispatch(Op: word; AP: pointer);\n"
            + transformed[pos:]
        )
        # Insert after all original declarations/routines, before initialization/end.
        init = next((r for r in parser.routines if r.name == "$init"), None)
        pos = transformed.lower().rfind("end.")
        if init:
            point = next(
                (
                    p["id"]
                    for p in parser.points
                    if p["kind"] == "routine" and p["routine"] == "$init"
                ),
                None,
            )
            pos = (
                transformed.index(f"begin\nUHit({point});")
                if point
                else transformed.lower().rfind("begin")
            )
        transformed = transformed[:pos] + body + transformed[pos:]
        transformed = re.sub(r"\bCrt\b", "UIO", transformed, flags=re.I)
        transformed = transformed.replace("{$G-}", "{$G+}")
        transformed = re.sub(r"\{\$G-,", "{$G+,", transformed, flags=re.I)
        write(source / path.name, transformed)
        modules[path.stem] = dict(
            entries=entries, sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        )
    write(source / "UCOV.PAS", COV)
    write(source / "UIO.PAS", IO)
    for name, metadata in modules.items():
        if not metadata["entries"]:
            continue
        code = UNIT / name / "CODE"
        write(
            code / "SGHOST.PAS",
            f"""program UnitHost;
{{$G+,R-,S-,I+,A+}}
{{$M 16384,0,655360}}
uses {", ".join(dict.fromkeys(n.upper() for n in ("UCov", "KBState", "KBTables", name)))};
var A: TUArgs; Scratch: pointer;
begin
 GetMem(Scratch, 32000);
 UMark($f130, @Game);
 UMark($f131, @CreatureDefinitions);
 UMark($f132, @RandSeed);
 UMark($f133, @A);
 UMark($f134, Scratch);
 while true do begin
  UAwait;
  case Word(A[0]) of
   65535: begin Assign(Game.Runtime.Lst,'LPT1'); Rewrite(Game.Runtime.Lst) end;
   65534: Close(Game.Runtime.Lst);
   65533: A[32]:=MemAvail;
  else {name}.UDispatch(Word(A[0]), @A[1]) end;
 end;
end.
""",
        )
        data = UNIT / name / "DATA"
        data.mkdir(parents=True, exist_ok=True)
        for resource in artwork.iterdir():
            if resource.suffix.upper() in (".PIC", ".FNT"):
                shutil.copy2(resource, data / resource.name)
        if name == "RSPACK":
            for resource in (ROOT / "SRC/ART").rglob("*.PCX"):
                shutil.copy2(resource, data / resource.name)
            shutil.copy2(ROOT / "SRC/PACK.LST", data / "PACK.LST")
    (UNIT / "INDEX.json").write_text(
        json.dumps(dict(points=points, modules=modules), indent=2), encoding="utf-8"
    )
    return modules


def build():
    modules = prepare()
    inputs = [
        *sorted((UNIT / "SRC").glob("*.PAS")),
        *sorted(UNIT.glob("*/CODE/SGHOST.PAS")),
        WORK / "PASCAL/TPC.EXE",
        WORK / "PASCAL/TURBO.TPL",
    ]
    fingerprint = hashlib.sha256(
        b"".join(p.name.encode() + p.read_bytes() for p in inputs)
    ).hexdigest()
    manifest = UNIT / "BUILD.CACHE.json"
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    if (
        previous.get("inputs") == fingerprint
        and previous.get("outputs")
        and all(
            (UNIT / path).exists()
            and hashlib.sha256((UNIT / path).read_bytes()).hexdigest() == digest
            for path, digest in previous["outputs"].items()
        )
    ):
        print("UNIT BUILD CACHED", len(modules), flush=True)
        return
    commands = ["cd UNIT\\SRC"]
    for name, metadata in modules.items():
        if not metadata["entries"]:
            continue
        commands += [
            rf"..\..\PASCAL\TPC.EXE ..\{name}\CODE\SGHOST.PAS /M /U. /GD /E..\{name}\CODE > ..\{name}\BUILD.LOG",
            "if errorlevel 1 goto bad",
        ]
    commands += [
        "echo OK>..\\BUILD.OK",
        "goto done",
        ":bad",
        "echo FAILED>..\\BUILD.ERR",
        ":done",
    ]
    write(UNIT / "BUILDALL.BAT", "\n".join(commands) + "\n")
    (UNIT / "BUILD.OK").unlink(missing_ok=True)
    subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(ROOT / "TEST/HOST/dos.ps1"),
            "-Work",
            str(WORK),
            "-Commands",
            "call UNIT\\BUILDALL.BAT",
        ],
        check=True,
    )
    if not (UNIT / "BUILD.OK").exists():
        for log in UNIT.glob("*/BUILD.LOG"):
            if b"Error " in log.read_bytes():
                print(log, log.read_bytes().decode("cp866"))
        raise RuntimeError("Unit build failed")
    print("UNIT BUILD OK", len(modules), flush=True)
    outputs = {
        str(p.relative_to(UNIT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in UNIT.glob("*/CODE/SGHOST.*")
        if p.suffix in (".EXE", ".MAP")
    }
    manifest.write_text(
        json.dumps(dict(inputs=fingerprint, outputs=outputs), indent=2),
        encoding="ascii",
    )


if __name__ == "__main__":
    build()
