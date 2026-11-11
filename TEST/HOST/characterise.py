"""Frozen, named unit-level examples for menu and state-machine boundaries."""

import ctypes as C
import hashlib
import struct
from cases import Case
from runtime import Battle, INDEX, linear


def preset(vm, rich=False):
    g = vm.fixture()
    vm.input_fallback = 27
    if rich:
        c = g.Campaign
        c.Gold = 2000000
        c.MagicPower = 40
        c.Leadership = 2500
        c.Income = 1500
        c.MapParts = 5
        c.Difficulty = 3
        c.Flags.ArmyAvailable = True
        c.Flags.SiegeEngineOwned = True
        for i in range(8):
            c.Flags.SpellAvailable[i] = True
            c.Flags.SpellUsed[i] = True
        for i in range(14):
            c.Scrolls[i] = 2
        c.ScrollCapacity = 100
        for i, species in enumerate((20, 23, 17, 18, 22)):
            c.Army[i].Species = species
            c.Army[i].Count = 3
        for i in range(5):
            c.WizardRelations[i] = 10
            c.Flags.LocalMapOwned[i] = True
        c.HiddenSpellIsland = 1
        c.HiddenSpellPosition.X = 30
        c.HiddenSpellPosition.Y = 30
        c.GuardianSpecies[:] = [0, 100, 100, 100, 100]
        c.GuardianCounts[0] = 3
        for i in range(4):
            c.Relics[i].Owned = True
        g.Runtime.GoodsMarketIsland = 255
        g.Runtime.GoodsMarketTown = 255
    if vm.target == "KBTOWN":
        g.World.GenerationX = g.Campaign.Towns[0][0].X
        g.World.GenerationY = g.Campaign.Towns[0][0].Y
    if vm.target == "KBCASTLE":
        c = g.Campaign
        c.Hero.X = c.Castles[0][0].X
        c.Hero.Y = c.Castles[0][0].Y + 1
        g.World.GenerationX = c.Castles[0][0].X
        g.World.GenerationY = c.Castles[0][0].Y
    if vm.target == "KBDWELL":
        g.World.GenerationX = g.Campaign.Dwellings[0][0].X
        g.World.GenerationY = g.Campaign.Dwellings[0][0].Y
    if vm.target == "KBVISIT":
        a = g.Campaign.WanderingArmies[0][0]
        a.X = 30
        a.Y = 30
        a.Species[:] = [0, 100, 100, 100, 100]
        a.Counts[0] = 10
    vm.set_game(g)
    return g


def battle(vm, rich=False):
    b = Battle()
    b.FrozenEnemySlot = 100
    b.MaxReserve = 9
    b.VampireInitialCount = 100
    b.RoundMagicReady = True
    b.EnemyPhaseFinished = True
    for a in b.Player:
        a.Species = 100
    for a in b.Enemy:
        a.Species = 100
    if rich:
        b.PlayerCount = 1
        b.EnemyCount = 1
        for troops in (b.Player, b.Enemy):
            a = troops[0]
            a.Species = 0
            a.Count = 20
            a.InitialCount = 20
            a.HitPoints = 40
            a.AttackPower = 20
            a.Shots = 2
            a.CanFly = True
        b.CanMove[0] = True
        g = vm.game()
        g.Runtime.BattleField[0][0] = 112
        g.Runtime.BattleField[5][4] = 32
        g.Runtime.BattleDistances[0][0] = 20
        g.Runtime.BattleDistances[5][4] = 20
        vm.set_game(g)
    return b


def arguments(vm, entry, rich):
    args = []
    watch = []
    for arg in entry["args"]:
        name, typ = arg["name"].lower(), arg["type"].lower()
        if typ == "tbattlestate":
            b = battle(vm, rich)
            p = vm.alloc(bytes(b))
            args.append(p)
            watch.append((name, p, C.sizeof(b)))
        elif typ in ("tposition", "tsignedposition"):
            p = vm.alloc(bytes((30, 30)))
            args.append(p)
            watch.append((name, p, 2))
        elif typ == "string":
            args.append(vm.string_arg("UNIT"))
        elif typ == "treportspecies":
            args.append(
                vm.alloc(bytes((0, 100, 100, 100, 100)) if rich else bytes([100]) * 5)
            )
        elif typ == "treportcounts":
            args.append(vm.alloc(struct.pack("<5H", 20 if rich else 0, 0, 0, 0, 0)))
        elif arg["mode"] == "var":
            size = 4 if typ == "longint" else 2 if typ in ("integer", "word") else 1
            value = (
                100
                if name in ("hitpoints", "attackerhitpoints", "defenderhitpoints")
                else 2
                if name in ("shots", "x", "y")
                else 0
            )
            p = vm.alloc(value.to_bytes(size, "little"))
            args.append(p)
            watch.append((name, p, size))
        elif typ == "pointer":
            if name == "enemytypes":
                raw = bytes((0, 100, 100, 100, 100)) if rich else bytes([100]) * 5
            elif name == "enemycounts":
                raw = struct.pack("<5H", 10 if rich else 0, 0, 0, 0, 0)
            else:
                raw = bytes(1024)
            p = vm.alloc(raw)
            args.append(p)
            watch.append((name, p, len(raw)))
        else:
            value = 1 if name == "island" else 0
            if typ == "boolean":
                value = int(rich)
            if name in ("damage", "bytes"):
                value = 2
            if name in ("x", "y", "newx", "newy", "x1", "y1"):
                value = 1
            if name in ("x2", "y2"):
                value = 3
            if name == "spell":
                value = 7
            args.append(value)
    if vm.target == "KBVISIT" and entry["name"] == "FindWanderingArmy":
        args = [30, 30]
    return args, watch


def tree(value):
    if isinstance(value, C.Structure):
        return {
            name: tree(getattr(value, name))
            for name, typ in value._fields_
            if not name.startswith("Unknown")
            and typ is not C.c_uint32
            and name not in ("PictureBanks", "Lst")
        }
    if isinstance(value, C.Array):
        if C.sizeof(value) > 64:
            return {
                "bytes": C.sizeof(value),
                "sha256": hashlib.sha256(bytes(value)).hexdigest(),
            }
        return [tree(x) for x in value]
    return value


def projection(vm, before, watch, result, before_disk, before_creatures=None):
    after = tree(vm.game())
    delta = {}

    def diff(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in a.keys() | b.keys():
                diff(a.get(key), b.get(key), path + "." + key if path else key)
        elif a != b:
            delta[path] = b

    diff(before, after, "")
    calls = []
    for owner, name, args in vm.calls:
        meta = next(m for m in INDEX["modules"][owner]["entries"] if m["name"] == name)
        decoded = []
        for spec, value in zip(meta["args"], args):
            typ = spec["type"].lower()
            if typ == "string":
                decoded.append(value)
            elif (
                spec["mode"] == "var"
                or typ == "pointer"
                or typ
                not in (
                    "byte",
                    "word",
                    "shortint",
                    "integer",
                    "longint",
                    "boolean",
                    "char",
                )
            ):
                decoded.append("<buffer>")
            else:
                decoded.append(value)
        calls.append([owner, name, decoded])
    tables = vm.read(vm.addresses[1][0], 540)
    creature_delta = (
        {
            str(i): tables[i * 18 : (i + 1) * 18].hex()
            for i in range(30)
            if tables[i * 18 : (i + 1) * 18] != before_creatures[i * 18 : (i + 1) * 18]
        }
        if before_creatures is not None
        else {}
    )
    return dict(
        result=result[0],
        phase=result[1]["kind"],
        exit_code=result[1].get("code"),
        random_seed=struct.unpack("<I", vm.read(vm.addresses[2][0], 4))[0],
        output=vm.output,
        state_delta=delta,
        calls_at_entry=calls,
        creature_delta=creature_delta,
        buffers={name: vm.read(linear(p), size).hex() for name, p, size in watch},
        disk={
            name: dict(size=len(data), sha256=hashlib.sha256(data).hexdigest())
            for name, data in vm.disk.items()
            if before_disk.get(name) != data
        },
        effects=vm.effects,
        os_events=vm.os_events,
        video=hashlib.sha256(vm.ega.snapshot()).hexdigest(),
        ports=vm.ega.port_log,
    )


def cases(module):
    if module in (
        "KBFILES",
        "KBECON",
        "KBRANDOM",
        "KBWORLD",
        "RSPACK",
        "KBTYPES",
        "KBBTYPE",
        "KBSTATE",
        "KBTABLES",
    ):
        return
    for entry in INDEX["modules"][module]["entries"]:
        if entry["name"] in ("AllocateArtwork", "ReleaseArtwork", "GenerateWorld"):
            continue
        for rich in (False, True):

            def sample(vm, entry=entry, rich=rich):
                preset(vm, rich)
                if entry["name"] == "RunGame":
                    vm.mock_own = {
                        "WaitForCommand",
                        "DispatchCommand",
                        "UpdateHeroFacing",
                        "ResolveMovement",
                        "AdvanceAdventureTime",
                        "ConfirmExit",
                    }

                    def command(v, args):
                        g = v.game()
                        g.Runtime.LastScan = 68
                        v.set_game(g)
                        return 0

                    vm.responses.update(WaitForCommand=command, ConfirmExit=1)
                if vm.target == "KBGEN" and entry["name"] == "FrameTerrain":
                    # A terrain base of zero violates this routine's terrain-family contract.
                    args_base = 48
                else:
                    args_base = None
                if vm.target == "KBGEN" and entry["name"] == "GenerateContracts":
                    g = vm.game()
                    for i in range(5):
                        for j in range(5):
                            g.Campaign.Castles[i][j].Name = i * 5 + j
                            g.World.CastleNamePool[i * 5 + j] = 255
                    vm.set_game(g)
                if vm.target == "KBGFX":
                    g = vm.game()
                    for field, value in (
                        ("PictureFileName", "TITL.PIC"),
                        ("ReservePictureFileName", "ARMY5.PIC"),
                    ):
                        target = getattr(g.Runtime, field)
                        raw = value.encode("ascii")
                        target[:] = (
                            bytes([len(raw)]) + raw + bytes(len(target) - len(raw) - 1)
                        )
                    vm.set_game(g)
                if vm.target == "KBINPUT" and entry["name"] == "ReadScanCode":
                    vm.queue.append((28, 13))
                if entry["name"] == "StartupMenu":
                    vm.scans.extend((80, 28))
                if entry["name"] == "TreasureVisit":
                    vm.keys.append(49)
                if entry["name"] == "ShootUnit":
                    vm.scans.append(28)
                    g = vm.game()
                    g.Runtime.BattleField[0][0] = 32
                    vm.set_game(g)
                args, watch = arguments(vm, entry, rich)
                if args_base is not None:
                    args[0] = args_base
                before = tree(vm.game())
                before_disk = vm.disk.copy()
                before_creatures = vm.read(vm.addresses[1][0], 540)
                result = vm.invoke(
                    entry["name"],
                    *args,
                    keys=[120] if entry["name"] == "WaitForCommand" else (),
                )
                assert result[1]["kind"] in ("ready", "exit"), result
                return projection(
                    vm, before, watch, result, before_disk, before_creatures
                )

            yield Case(
                entry["name"]
                + "."
                + ("army" if rich else "empty")
                + (
                    ".ega"
                    if module == "KBGFX"
                    else ".located"
                    if module == "KBBAI" and rich
                    else ""
                ),
                sample,
            )
