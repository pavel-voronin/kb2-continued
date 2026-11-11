"""Isolated calls into compiled Pascal, with explicit dependency doubles."""

import collections
import fnmatch
import ctypes as C
import json
from pathlib import Path
import re
import struct
import time

ROOT = Path(__file__).resolve().parents[2]
from machine import VM
from config import WORK
from state import Game, Creature as Creature, Battle as Battle, TYPES as TYPES
import unicorn as uc

INDEX = json.loads((WORK / "UNIT/INDEX.json").read_text(encoding="utf-8"))
SCALARS = {
    "byte": 2,
    "shortint": 2,
    "boolean": 2,
    "char": 2,
    "word": 2,
    "integer": 2,
    "longint": 4,
    "pointer": 4,
}


def linear(pointer):
    return (pointer >> 16) * 16 + (pointer & 65535)


def far(address):
    return (address >> 4) << 16 | (address & 15)


class UnitVM(VM):
    def __init__(self, module):
        self.target = module.upper()
        self.hits = collections.Counter()
        self.calls = []
        self.responses = {}
        self.keys = collections.deque()
        self.input_fallback = None
        self.ports = []
        self.mock_own = set()
        self.active_entry = None
        self.asm_hits = set()
        self.asm_edges = set()
        self.asm_previous = None
        self.effects = []
        self.entry_probes = {}
        self.os_events = []
        super().__init__("UNIT/" + self.target, 1)
        from hardware import Ega

        self.ega = Ega(self)
        self.read_regions()
        for address, entry in self.functions.items():
            self.cpu.hook_add(uc.UC_HOOK_CODE, self.on_code, None, address, address)
        self.assembly = {}
        self.asm_instructions = {}
        from capstone import Cs, CS_ARCH_X86, CS_MODE_16

        decoder = Cs(CS_ARCH_X86, CS_MODE_16)
        for start, end, owner in self.regions:
            if owner != self.target:
                continue
            raw = self.read(start, end - start)
            for match in re.finditer(
                rb"\x9c\x60\x1e\x06\xb8\x20\xf1\xbb(..)\xcd\xf0\x07\x1f\x61\x9d",
                raw,
                re.S,
            ):
                point = struct.unpack("<H", match[1])[0]
                closing = (
                    b"\x9c\x60\x1e\x06\xb8\x22\xf1\xbb"
                    + match[1]
                    + b"\xcd\xf0\x07\x1f\x61\x9d"
                )
                stop = raw.find(closing, match.end())
                if stop < 0:
                    raise RuntimeError(("No assembly boundary", module, point))
                code = raw[match.end() : stop]
                address = start + match.end()
                instructions = list(decoder.disasm(code, address))
                if sum(i.size for i in instructions) != len(code):
                    raise RuntimeError("Assembly decode incomplete")
                self.assembly[point] = [
                    (i.address, i.size, i.mnemonic, i.op_str) for i in instructions
                ]
                self.asm_instructions.update(
                    {i.address: (point, i.size, i.mnemonic) for i in instructions}
                )
                if code:
                    self.cpu.hook_add(
                        uc.UC_HOOK_CODE,
                        self.on_assembly,
                        None,
                        address,
                        start + stop - 1,
                    )
        inventory = WORK / "UNIT/ASSEMBLY" / f"{self.target}.JSON"
        inventory.parent.mkdir(parents=True, exist_ok=True)
        inventory.write_text(json.dumps(self.assembly), encoding="utf-8")
        self.execute()
        if self.pending != {"kind": "ready"}:
            raise RuntimeError(("Unit host initialization", self.pending))
        self.boot_hits = self.hits.copy()
        self.initial = self.snapshot()
        self.heap_cursor = 0

    def read_regions(self):
        self.regions = []
        text = (self.root / "CODE/SGHOST.MAP").read_text()
        for start, stop, size, name in re.findall(
            r"^\s+([0-9A-F]+)H\s+([0-9A-F]+)H\s+([0-9A-F]+)H\s+(\w+)\s+CODE", text, re.M
        ):
            if int(size, 16):
                self.regions.append(
                    (
                        self.base + int(start, 16),
                        self.base + int(stop, 16) + 1,
                        name.upper(),
                    )
                )
        self.functions = {}
        for address, name in self.symbols:
            owner = next((n for a, b, n in self.regions if a <= address < b), None)
            if owner in INDEX["modules"]:
                meta = next(
                    (
                        m
                        for m in INDEX["modules"][owner]["entries"]
                        if m["name"].lower() == name.lower()
                    ),
                    None,
                )
                if meta:
                    self.functions[address] = (owner, meta)

    def on_code(self, cpu, address, size, user):
        entry = self.functions.get(address)
        if entry and (
            entry[0] != self.target
            or entry[1]["name"] in self.mock_own
            and entry[1]["name"] != self.active_entry
        ):
            self.stop("dependency", owner=entry[0], function=entry[1])

    def on_assembly(self, cpu, address, size, user):
        if time.process_time() > self.execution_deadline:
            self.stop("budget")
            return
        self.finish_assembly_edge(address)
        self.asm_hits.add(address)
        point, length, mnemonic = self.asm_instructions[address]
        if mnemonic != "jmp" and (
            mnemonic.startswith("j") or mnemonic.startswith("loop")
        ):
            self.asm_previous = (point, address, length)

    def finish_assembly_edge(self, address):
        if self.asm_previous:
            point, previous, length = self.asm_previous
            self.asm_edges.add(
                f"{point}:{previous}:{int(address != previous + length)}"
            )
            self.asm_previous = None

    def interrupt(self, cpu, number, user):
        ax = self.r("ax")
        if number == 0xF0:
            if ax == 0xF120:
                if time.process_time() > self.execution_deadline:
                    self.stop("budget")
                    return
                self.hits[self.r("bx")] += 1
                probe = self.entry_probes.get(self.r("bx"))
                if probe:
                    probe(self)
                return
            if ax == 0xF122:
                self.finish_assembly_edge(self.r("cs") * 16 + self.r("ip") - 12)
                return
            if 0xF130 <= ax <= 0xF134:
                self.addresses[ax - 0xF130] = (self.r("es") * 16 + self.r("bx"), 0)
                return
            if ax == 0xF140:
                self.stop("ready")
                return
            if ax == 0xF150:
                if self.extended:
                    self.w("ax", self.extended)
                    self.extended = 0
                elif self.keys:
                    value = self.keys.popleft()
                    if isinstance(value, tuple):
                        self.w("ax", 0)
                        self.extended = value[0]
                    else:
                        self.w("ax", value)
                elif self.input_fallback is not None:
                    self.w("ax", self.input_fallback)
                else:
                    self.stop("input-exhausted")
                return
            if ax == 0xF151:
                self.w("ax", int(bool(self.keys)))
                return
            if 0xF160 <= ax <= 0xF162:
                self.effects.append(
                    (("delay", "sound", "no-sound")[ax - 0xF160], self.r("bx"))
                )
                return
        if number == 0x16 and ax >> 8 == 1:
            self.w(
                "eflags",
                (self.r("eflags") & ~0x40) if self.queue else self.r("eflags") | 0x40,
            )
            if self.queue:
                sc, ch = self.queue[0]
                self.w("ax", sc * 256 + ch)
            return
        if number == 0x21 and ax >> 8 == 0x44:
            fd = self.r("bx")
            mode = self.r("dx")
            name = self.files.get(fd, [f"STD{fd}"])[0]
            super().interrupt(cpu, number, user)
            self.os_events.append(
                ["ioctl", ax, name, mode if ax & 255 else self.r("dx")]
            )
            return
        if number == 0x21 and ax >> 8 in (0x4E, 0x4F):
            first = ax >> 8 == 0x4E
            if first:
                pattern = (
                    self.string(self.r("ds") * 16 + self.r("dx"))
                    .split("\\")[-1]
                    .upper()
                )
                self.directory = collections.deque(
                    name
                    for name in sorted(self.disk)
                    if fnmatch.fnmatchcase(name, pattern)
                )
            if not self.directory:
                self.carry(True)
                self.w("ax", 2 if first else 18)
            else:
                name = self.directory.popleft()
                record = bytearray(43)
                record[21] = 32
                struct.pack_into("<HHI", record, 22, 0, 6689, len(self.disk[name]))
                encoded = name.encode("cp866")
                record[30 : 30 + len(encoded)] = encoded
                self.cpu.mem_write(self.dta, bytes(record))
                self.carry(False)
                self.w("ax", 0)
            return
        super().interrupt(cpu, number, user)

    def dependency(self):
        meta = self.pending["function"]
        sp = self.r("ss") * 16 + self.r("sp")
        ip, cs = struct.unpack("<HH", self.read(sp, 4))
        offset = 4
        decoded = []
        for arg in reversed(meta["args"]):
            size = 4 if arg["mode"] == "var" else SCALARS.get(arg["type"].lower(), 4)
            value = int.from_bytes(self.read(sp + offset, size), "little")
            decoded.insert(0, value)
            offset += size
        name = meta["name"]
        trace = []
        for spec, value in zip(meta["args"], decoded):
            if spec["type"].lower() == "string":
                address = linear(value)
                size = self.read(address, 1)[0]
                trace.append(self.read(address + 1, size).decode("cp866"))
            else:
                trace.append(value)
        self.calls.append((self.pending["owner"], name, trace))
        answer = self.responses.get(name, 0)
        if name not in self.responses:
            if name == "ReadScanCode":
                answer = self.scans.popleft() if self.scans else 1
            elif name == "BIOSKeyPressed":
                answer = 1
            elif name == "AwaitCellKey":
                g = self.game()
                g.Runtime.LastScan = (
                    self.scans.popleft()
                    if self.scans
                    else (68 if self.target == "KBBATTLE" else 1)
                )
                self.set_game(g)
            elif name == "ReadQuantity":
                self.cpu.mem_write(linear(decoded[0]), struct.pack("<i", 1))
                answer = 1
            elif name == "ShowNotice":
                g = self.game()
                g.Runtime.LastScan = self.scans.popleft() if self.scans else 28
                self.set_game(g)
            elif name == "Battle":
                g = self.game()
                g.Runtime.BattleResult = 1
                self.set_game(g)
            elif name == "FindUnitCell":
                wanted = decoded[0] * 3 + decoded[1]
                g = self.game()
                found = next(
                    (
                        (x, y)
                        for x in range(6)
                        for y in range(5)
                        if g.Runtime.BattleField[x][y] == wanted
                    ),
                    None,
                )
                if found is None:
                    raise AssertionError(
                        ("Unconfigured FindUnitCell dependency", wanted)
                    )
                self.cpu.mem_write(linear(decoded[2]), bytes([found[0]]))
                self.cpu.mem_write(linear(decoded[3]), bytes([found[1]]))
            elif name in ("BuyQuantity", "BuyByteQuantity"):
                g = self.game()
                g.Runtime.LastScan = 27
                self.set_game(g)
        if callable(answer):
            answer = answer(self, decoded)
        self.w("ax", int(answer) & 65535)
        self.w("dx", (int(answer) >> 16) & 65535)
        self.w("sp", self.r("sp") + offset)
        self.w("cs", cs)
        self.w("ip", ip)

    def execute(self, instructions=2_000_000, seconds=3):
        self.pending = None
        deadline = time.process_time() + seconds
        self.execution_deadline = deadline
        for _ in range(20000):
            if time.process_time() > deadline:
                self.pending = {"kind": "budget"}
                return self.pending
            self.pending = None
            try:
                self.cpu.emu_start(
                    self.r("cs") * 16 + self.r("ip"), 0, count=instructions
                )
            except uc.UcError as error:
                self.pending = {"kind": "cpu-error", "error": str(error)}
            if self.pending is None:
                self.pending = {"kind": "budget"}
            if self.pending["kind"] != "dependency":
                return self.pending
            self.dependency()
        self.pending = {"kind": "dependency-budget"}
        return self.pending

    def reset(self):
        self.restore(self.initial)
        self.hits.clear()
        self.calls.clear()
        self.responses.clear()
        self.keys.clear()
        self.asm_hits.clear()
        self.asm_edges.clear()
        self.asm_previous = None
        self.effects.clear()
        self.entry_probes.clear()
        self.os_events.clear()
        self.input_fallback = None
        self.scans = collections.deque()
        self.directory = collections.deque()
        self.mock_own = set()
        self.heap_cursor = 0
        self.ega.reset()

    def alloc(self, value, size=None):
        address = self.addresses[4][0] + self.heap_cursor
        raw = bytes(value) if not isinstance(value, int) else bytes(size or value)
        self.heap_cursor += (len(raw) + 1) & ~1
        if self.heap_cursor > 32000:
            raise RuntimeError("Fixture scratch overflow")
        self.cpu.mem_write(address, raw)
        return far(address)

    def string_arg(self, value):
        raw = value.encode("cp866") if isinstance(value, str) else value
        return self.alloc(bytes([len(raw)]) + raw + bytes(255 - len(raw)))

    def game(self):
        return Game.from_buffer_copy(self.read(self.addresses[0][0], C.sizeof(Game)))

    def set_game(self, value):
        self.cpu.mem_write(self.addresses[0][0], bytes(value))

    def invoke(
        self, name, *values, keys=(), responses=None, instructions=2_000_000, seconds=3
    ):
        meta = next(
            m
            for m in INDEX["modules"][self.target]["entries"]
            if m["name"].lower() == name.lower()
        )
        if len(values) != len(meta["args"]):
            raise ValueError((name, len(values), meta["args"]))
        self.keys.extend(keys)
        self.active_entry = meta["name"]
        if responses:
            self.responses.update(responses)
        args = [meta["op"]] + list(values) + [0] * (64 - len(values) - 1)
        string_result = None
        if meta["result"] and meta["result"].lower() == "string":
            string_result = self.string_arg("")
            args[32] = string_result
        self.cpu.mem_write(
            self.addresses[3][0], struct.pack("<64I", *(v & 0xFFFFFFFF for v in args))
        )
        self.execute(instructions, seconds)
        result = struct.unpack("<i", self.read(self.addresses[3][0] + 32 * 4, 4))[0]
        if string_result:
            address = linear(string_result)
            size = self.read(address, 1)[0]
            result = self.read(address + 1, size).decode("cp866")
        return result, self.pending

    def support(self, op):
        """Native TP fixture helpers in the driver, outside source coverage."""
        self.cpu.mem_write(self.addresses[3][0], struct.pack("<I", op))
        result = self.execute()
        assert result == {"kind": "ready"}, result
        return struct.unpack("<i", self.read(self.addresses[3][0] + 128, 4))[0]

    def fixture(self):
        self.reset()
        self.cpu.mem_write(0xA0000, bytes(0x60000))
        g = Game()
        c = g.Campaign
        c.Island = 1
        c.UnlockedIslands = 5
        c.HighestVisitedIsland = 5
        c.Leadership = 1000
        c.MagicPower = 10
        c.Gold = 100000
        c.Weeks = 100
        c.Days = 200
        c.HiddenSpellIsland = 100
        c.ShipIsland = 1
        c.Ship.X = 25
        c.Ship.Y = 25
        c.Hero.X = 30
        c.Hero.Y = 30
        g.World.GenerationIsland = 1
        g.World.GenerationX = 30
        g.World.GenerationY = 30
        g.Runtime.FontPointer = far(
            self.addresses[0][0] + Game.Runtime.offset + type(g.Runtime).Font.offset
        )
        for i in range(15):
            g.Runtime.PictureBanks[i] = far(0xB0000)
        for i, address in (
            (10, 0xC0000),
            (11, 0xD0000),
            (12, 0xD4000),
            (13, 0xD8000),
            (14, 0xDC000),
        ):
            g.Runtime.PictureBanks[i] = far(address)
        g.Runtime.CalmArmyPicture = far(0xD8000)
        g.Runtime.RegrowthPosition.X = 100
        g.Runtime.CurrentContractOffer = 1
        g.Runtime.DataFileName[:] = (
            bytes([7]) + b"KB2.DAT" + bytes(len(g.Runtime.DataFileName) - 8)
        )
        for a in c.Army:
            a.Species = 100
        for island in range(5):
            c.QuestFlags[island] = 3
            for slot in range(5):
                t = c.Towns[island][slot]
                t.X = 8 + slot * 10
                t.Y = 8 + island * 8
                t.Name = slot + 1
                t.Scroll = slot
                for i in range(4):
                    t.Workers[i] = 20
                z = c.Castles[island][slot]
                z.X = 8 + slot * 10
                z.Y = 53
                z.Name = slot + 1
                for i in range(5):
                    z.Species[i] = 100
                c.Contracts[island][slot].Island = island + 1
                c.Contracts[island][slot].Slot = slot + 1
            for j, d in enumerate(c.Dwellings[island]):
                d.X = 8 + j * 6
                d.Y = 35
                d.Count = 40
                d.Species = j
            for a in c.WanderingArmies[island]:
                a.X = 255
                a.Y = 255
            for x, y in ((10, 10), (20, 10), (30, 10), (40, 10), (50, 10)):
                c.Map[island][x][y] = 22
        self.set_game(g)
        self.cpu.mem_write(self.addresses[2][0], struct.pack("<I", 12345))
        return g
