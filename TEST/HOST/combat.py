"""Independent combat fixtures, scalar oracles and single-command transitions."""

import ctypes as C
import json
import struct
from cases import Case, ready
from characterise import preset, battle, tree, projection
from runtime import Battle, Creature, linear


def adjacent(v, args):
    px, py, base = args
    x = v.read(linear(px), 1)[0]
    y = v.read(linear(py), 1)[0]
    g = v.game()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            tx, ty = x + dx, y + dy
            if (
                (dx or dy)
                and 0 <= tx < 6
                and 0 <= ty < 5
                and base < g.Runtime.BattleField[tx][ty] < base + 14
            ):
                v.cpu.mem_write(linear(px), bytes([tx]))
                v.cpu.mem_write(linear(py), bytes([ty]))
                return 1
    return 0


def relocate(v, args):
    px, py, tx, ty = args
    x = v.read(linear(px), 1)[0]
    y = v.read(linear(py), 1)[0]
    g = v.game()
    g.Runtime.BattleField[tx][ty] = g.Runtime.BattleField[x][y]
    g.Runtime.BattleDistances[tx][ty] = g.Runtime.BattleDistances[x][y]
    if (x, y) != (tx, ty):
        g.Runtime.BattleField[x][y] = 0
        g.Runtime.BattleDistances[x][y] = 0
    v.set_game(g)
    v.cpu.mem_write(linear(px), bytes([tx]))
    v.cpu.mem_write(linear(py), bytes([ty]))
    return 0


def trial(
    module,
    routine,
    label,
    *,
    spell=7,
    consume=True,
    spends_scroll=None,
    cursor=(0, 0),
    scans=(),
    keys=(),
    units=(),
    changes=None,
    field=None,
    args=None,
    responses=None,
    seed=None,
    outcomes=None,
    flush_keyboard=False,
):
    spec = dict(
        module=module,
        routine=routine,
        label=label,
        spell=spell,
        consume=consume,
        cursor=cursor,
        scans=scans,
        keys=keys,
        units=units,
        changes=changes,
        field=field,
        args=args,
        responses=responses,
        seed=seed,
        outcomes=outcomes,
        flush_keyboard=flush_keyboard,
    )
    if spends_scroll is not None:
        spec["spends_scroll"] = spends_scroll

    def execute(vm):
        g = preset(vm, True)
        b = battle(vm, False)
        b.CursorX, b.CursorY = cursor
        for side, slot, species, count, x, y in units:
            a = getattr(b, side)[slot]
            a.Species = species
            a.Count = count
            a.InitialCount = count
            definition = Creature.from_buffer_copy(
                vm.read(
                    vm.addresses[1][0] + species * C.sizeof(Creature),
                    C.sizeof(Creature),
                )
            )
            a.HitPoints = count * definition.Defense
            a.AttackPower = count * definition.Attack
            a.Shots = 2
            if side == "Player":
                b.PlayerCount += int(slot < 5)
                if slot < 5:
                    b.CanMove[slot] = True
            else:
                b.EnemyCount += int(slot < 5)
            if x >= 0:
                g.Runtime.BattleField[x][y] = (
                    112 if side == "Player" else 32
                ) + slot * 3
                g.Runtime.BattleDistances[x][y] = count
        for path, value in (changes or {}).items():
            root = b if path.startswith("Combat.") else g
            parts = (
                path.split(".")[1:] if path.startswith("Combat.") else path.split(".")
            )
            for name in parts[:-1]:
                root = root[int(name)] if name.isdigit() else getattr(root, name)
            if parts[-1].isdigit():
                root[int(parts[-1])] = value
            else:
                setattr(root, parts[-1], value)
        for x, y, tile in field or ():
            g.Runtime.BattleField[x][y] = tile
        vm.set_game(g)
        p = vm.alloc(bytes(b))
        vm.scans.extend(scans)
        if seed is not None:
            vm.cpu.mem_write(vm.addresses[2][0], struct.pack("<I", seed))
        if module in ("KBBAI", "KBPLAYER", "KBBRES"):
            vm.responses.update(FindAdjacent=adjacent, RelocateUnit=relocate)
        for name, outcome in (outcomes or {}).items():

            def finish(v, values, outcome=outcome):
                state = v.game()
                if outcome == "kill-target":
                    x, y = values[-2:]
                    tile = state.Runtime.BattleField[x][y]
                    context = Battle.from_buffer_copy(
                        v.read(linear(values[0]), C.sizeof(Battle))
                    )
                    player = tile > 111
                    slot = (tile - (112 if player else 32)) // 3
                    getattr(context, "Player" if player else "Enemy")[
                        slot
                    ].Species = 100
                    if player:
                        context.PlayerCount -= 1
                    else:
                        context.EnemyCount -= 1
                    state.Runtime.BattleField[x][y] = 0
                    state.Runtime.BattleDistances[x][y] = 0
                    v.cpu.mem_write(linear(values[0]), bytes(context))
                else:
                    state.Runtime.BattleResult = outcome
                v.set_game(state)
                return 0

            vm.responses[name] = finish
        if flush_keyboard:

            def scan(v, values):
                v.keys.clear()
                return 1

            vm.responses["ReadScanCode"] = scan
        watch = [("combat", p, C.sizeof(b))]
        values = [p]
        if routine == "SelectSpellTarget":
            values.extend((spell, consume))
        if routine == "MovePlayerUnit":
            values.extend(args or [0])
        if routine == "ShootUnit":
            shots = vm.alloc(bytes([2]))
            values.extend((shots, 0))
            watch.append(("shots", shots, 1))
        if routine == "AwaitCellKey":
            values.extend(args or (*cursor, 0, 2))
        if routine == "PaintBattleTerrain":
            values.append(args[0])
        if routine in ("AttackUnit", "ReportEnemyLoss"):
            values.extend(args)
        if routine == "ResolveStrike":
            attacker, defender, hpa, hpd = args
            for species in (attacker, defender):
                if species >= 25:
                    vm.cpu.mem_write(
                        vm.addresses[1][0] + species * C.sizeof(Creature),
                        vm.read(vm.addresses[1][0], C.sizeof(Creature)),
                    )
            pa = vm.alloc(struct.pack("<i", hpa))
            pd = vm.alloc(struct.pack("<i", hpd))
            values.extend((attacker, defender, pa, pd))
            watch.extend((("attacker_hp", pa, 4), ("defender_hp", pd, 4)))
        before = tree(vm.game())
        disk = vm.disk.copy()
        before_creatures = vm.read(vm.addresses[1][0], 540)
        result = vm.invoke(routine, *values, keys=keys, responses=responses)
        assert result[1]["kind"] == "ready", result
        if routine == "SelectSpellTarget":
            spent = consume if spends_scroll is None else spends_scroll
            assert vm.game().Campaign.Scrolls[spell] == g.Campaign.Scrolls[spell] - int(spent)
            assert not Battle.from_buffer_copy(
                vm.read(linear(p), C.sizeof(Battle))
            ).EnemyPhaseFinished
        return projection(vm, before, watch, result, disk, before_creatures)

    return Case(routine + ".combat." + label, execute, json.dumps(spec, sort_keys=True))


def cases(module):
    if module == "KBBATTLE":
        scripts = [
            (f"boundary-{scan}.{x}-{y}", [scan, 68], x, y, 0, 0, 0)
            for scan in (71, 72, 73, 75, 77, 79, 80, 81)
            for x, y in ((0, 0), (5, 4))
        ]
        scripts += [
            ("shoot", [31, 68], 0, 0, 2, 0, 0),
            ("shoot-defeat", [31], 0, 0, 2, 2, 0),
            ("move-defeat", [50], 0, 0, 0, 2, 0),
            ("disabled-cast", [22, 68], 0, 0, 0, 0, 1),
            ("enemy-phase-defeat", [68], 0, 0, 0, 2, 2),
            ("reserve-survivors", [1], 0, 0, 0, 1, 3),
            ("fly-on-enemy", [33, 68], 5, 4, 0, 0, 0),
            ("move-on-enemy", [50, 68], 5, 4, 0, 0, 0),
            ("initial-first-player-turn", [68], 0, 0, 0, 0, 4),
        ]
        for label, keys, x, y, species, outcome, mode in scripts:

            def script(
                v,
                label=label,
                keys=keys,
                x=x,
                y=y,
                species=species,
                outcome=outcome,
                mode=mode,
            ):
                g = preset(v, True)
                g.Campaign.Army[0].Species = species
                if mode == 3:
                    g.Campaign.Leadership = 0
                    for i in range(5, 10):
                        g.Campaign.Army[i].Species = 0
                        g.Campaign.Army[i].Count = 3
                v.set_game(g)
                events = iter(keys)
                if mode == 4:
                    seed = next(
                        s
                        for s in range(20000)
                        if (((s * 134775813 + 1) & 0xFFFFFFFF) * 30 >> 32) >= 15
                    )
                    v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))

                def phase(vm, args):
                    b = Battle.from_buffer_copy(
                        vm.read(linear(args[0]), C.sizeof(Battle))
                    )
                    b.ReadyPlayerCount = 0
                    vm.cpu.mem_write(linear(args[0]), bytes(b))
                    if mode == 2:
                        state = vm.game()
                        state.Runtime.BattleResult = outcome
                        vm.set_game(state)
                    return 0

                def await_key(vm, args):
                    b = Battle.from_buffer_copy(
                        vm.read(linear(args[0]), C.sizeof(Battle))
                    )
                    b.CursorX = x
                    b.CursorY = y
                    if mode == 1:
                        b.EnemyPhaseFinished = False
                    if mode == 3:
                        b.EnemyCount = 0
                        for a in b.Enemy:
                            a.Species = 100
                    vm.cpu.mem_write(linear(args[0]), bytes(b))
                    state = vm.game()
                    state.Runtime.LastScan = next(events)
                    if mode == 3:
                        state.Runtime.BattleResult = 1
                    vm.set_game(state)
                    return 0

                def moved(vm, args):
                    if outcome:
                        state = vm.game()
                        state.Runtime.BattleResult = outcome
                        vm.set_game(state)
                    return 0

                def uncontrolled(vm, args):
                    b = Battle.from_buffer_copy(
                        vm.read(linear(args[0]), C.sizeof(Battle))
                    )
                    b.RoundMagicReady = False
                    vm.cpu.mem_write(linear(args[0]), bytes(b))
                    return 0

                v.responses.update(
                    EnemyPhase=phase,
                    AwaitCellKey=await_key,
                    MovePlayerUnit=moved,
                    ShootUnit=moved,
                    UncontrolledTurn=uncontrolled,
                )
                types = v.alloc(bytes((0, 100, 100, 100, 100)))
                counts = v.alloc(struct.pack("<5H", 20, 0, 0, 0, 0))
                before = tree(v.game())
                disk = v.disk.copy()
                tables = v.read(v.addresses[1][0], 540)
                result = v.invoke("Battle", types, counts, 0)
                ready(v, result)
                return projection(
                    v,
                    before,
                    [("enemy_species", types, 5), ("enemy_counts", counts, 10)],
                    result,
                    disk,
                    tables,
                )

            yield Case("battle.script." + label, script)
        for command in (
            18,
            22,
            24,
            30,
            31,
            33,
            48,
            49,
            50,
            71,
            72,
            73,
            75,
            77,
            79,
            80,
            81,
        ):

            def battle_command(vm, command=command):
                g = preset(vm, True)
                g.Campaign.Army[0].Species = 23
                vm.set_game(g)
                types = vm.alloc(bytes([0, 100, 100, 100, 100]))
                counts = vm.alloc(struct.pack("<5H", 20, 0, 0, 0, 0))
                vm.scans.extend(
                    [77, 80, command, 68]
                    if command in (71, 72, 73, 75, 77, 79, 80, 81)
                    else [command, 68]
                )
                before = tree(vm.game())
                disk = vm.disk.copy()
                tables = vm.read(vm.addresses[1][0], 540)
                result = vm.invoke("Battle", types, counts, 0)
                ready(vm, result)
                assert vm.game().Runtime.BattleResult == 2
                assert all(a.Species == 100 for a in vm.game().Campaign.Army)
                return projection(
                    vm,
                    before,
                    [("enemy_species", types, 5), ("enemy_counts", counts, 10)],
                    result,
                    disk,
                    tables,
                )

            yield Case(f"battle.command-{command}", battle_command)
        for leadership in (0, 2500):

            def victory(vm, leadership=leadership):
                g = preset(vm, True)
                g.Campaign.Leadership = leadership
                vm.set_game(g)
                types = vm.alloc(bytes([100]) * 5)
                counts = vm.alloc(bytes(10))

                def won(v, args):
                    state = v.game()
                    state.Runtime.BattleResult = 1
                    state.Runtime.LastScan = 1
                    v.set_game(state)
                    return 0

                vm.responses["AwaitCellKey"] = won
                before = tree(vm.game())
                disk = vm.disk.copy()
                tables = vm.read(vm.addresses[1][0], 540)
                result = vm.invoke("Battle", types, counts, 0)
                ready(vm, result)
                assert vm.game().Runtime.BattleResult == 1
                return projection(
                    vm,
                    before,
                    [("enemy_species", types, 5), ("enemy_counts", counts, 10)],
                    result,
                    disk,
                    tables,
                )

            yield Case(f"battle.victory.leadership-{leadership}", victory)
    elif module == "KBBAI":
        yield trial(
            module,
            "EnemyPhase",
            "aligned-three-way-rank-tie",
            units=[("Player", 0, 0, 20, 0, 2), ("Enemy", 0, 0, 20, 3, 2)],
            changes={"Combat.Enemy.0.Shots": 0},
            field=[(2, 1, 64), (2, 2, 64), (2, 3, 64)],
        )
        for target_x in (3, 4):
            for diagonal in (0, 48, 64, 80):
                specimen = trial(
                    module,
                    "EnemyPhase",
                    f"route-choice.target-{target_x}.diagonal-{diagonal}",
                    units=[
                        ("Player", 0, 3, 60, target_x, 1),
                        ("Player", 1, 5, 10, 0, 3),
                        ("Enemy", 0, 3, 20, 1, 1),
                    ],
                    changes={"Combat.Player.0.Shots": 0, "Combat.Enemy.0.Shots": 0},
                    field=[(2, 0, 80), (2, 1, 80), (2, 2, diagonal)],
                )

                def route_choice(v, specimen=specimen, target_x=target_x, diagonal=diagonal):
                    specimen.run(v)
                    if target_x == 3 and diagonal == 0:
                        step, target = [2, 2], [3, 1]
                    else:
                        step, target = [0, 2], [0, 3]
                    moves = [args[-2:] for _, name, args in v.calls if name == "RelocateUnit"]
                    attacks = [args[1:] for _, name, args in v.calls if name == "AttackUnit"]
                    assert moves == [step], moves
                    assert attacks and attacks[0] == step + target, attacks

                yield Case(specimen.name, route_choice, specimen.identity)
        for mode, species, shots, power in (
            ("walk", 1, 0, 0),
            ("shoot", 0, 2, 5),
            ("fly", 0, 0, 0),
        ):
            specimen = trial(
                module,
                "EnemyPhase",
                f"zero-sized-player-stack.{mode}",
                units=[
                    ("Player", 0, species, 0, 0, 0),
                    ("Player", 5, 6, 20, -1, -1),
                    ("Enemy", 0, 1, 20, 5, 4),
                ],
                changes={
                    "Combat.Player.0.Shots": shots,
                    "Combat.Player.0.AttackPower": power,
                    "Combat.Enemy.0.Shots": 2 if mode == "shoot" else 0,
                    "Combat.Enemy.0.CanFly": mode == "fly",
                },
            )
            def no_living_target(v, specimen=specimen):
                specimen.run(v)
                assert v.game().Runtime.BattleResult == 2
                assert not any(name in ("FindUnitCell", "AttackUnit", "RelocateUnit")
                               for _, name, _ in v.calls)

            yield Case("B030.no-living-target." + mode, no_living_target, specimen.identity)

        def living_target_without_attack_power(v):
            choose = trial(
                module,
                "EnemyPhase",
                "living-target-without-attack-power",
                units=[("Player", 4, 6, 8192, 0, 0),
                       ("Enemy", 0, 5, 5, 5, 4)],
                changes={
                    "Combat.Player.4.HitPoints": 204795,
                    "Combat.Player.4.AttackPower": 0,
                    "Combat.Player.4.Shots": 0,
                    "Combat.Uncontrolled.4": True,
                    "Combat.PlayerCount": 0,
                },
            )
            choose.run(v)
            targets = [args[:2] for _, name, args in v.calls
                       if name == "FindUnitCell" and args[1] == 112]
            attacks = [args[1:] for _, name, args in v.calls if name == "AttackUnit"]
            assert targets == [[4, 112]], targets
            assert attacks == [[5, 4, 0, 0]], attacks
            assert v.game().Runtime.BattleResult == 0

        yield Case("B030.living-target-without-attack-power", living_target_without_attack_power)
        for species in (0, 4):
            yield trial(
                module,
                "EnemyPhase",
                f"blocked-far-target-weak-neighbour.species-{species}",
                units=[
                    ("Player", 0, species, 100, 0, 0),
                    ("Player", 1, 1, 1, 4, 4),
                    ("Enemy", 0, species, 20, 5, 4),
                ],
                changes={"Combat.Enemy.0.Shots": 0},
                field=[(4, 3, 64), (5, 3, 64)],
            )
        yield trial(
            module,
            "EnemyPhase",
            "ranged-strike-ends-battle",
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 2, 20, 5, 4)],
            outcomes={"AttackUnit": 2},
        )
        yield trial(
            module,
            "EnemyPhase",
            "archer-escape-blocked-first-step",
            units=[("Player", 0, 0, 20, 1, 2), ("Enemy", 0, 4, 20, 2, 2)],
            field=[(1, 1, 64)],
        )
        yield trial(
            module,
            "EnemyPhase",
            "archer-escape-blocked-after-leaving-contact",
            units=[("Player", 0, 0, 20, 4, 3), ("Enemy", 0, 11, 20, 3, 3)],
            field=[(1, 1, 64)],
        )
        yield trial(
            module,
            "EnemyPhase",
            "unsupported-poison-byte",
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 5, 4)],
            changes={"Combat.Poison.0": 4},
        )
        yield trial(
            module,
            "EnemyPhase",
            "keyboard-buffer-drained",
            keys=[65],
            flush_keyboard=True,
        )
        yield trial(
            module,
            "EnemyPhase",
            "poison-kills-last-opponent",
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 5, 4)],
            changes={"Combat.Poison.0": 2},
            responses={"ApplyDamage": 65535},
            outcomes={"ReportEnemyLoss": 1},
        )
        for shots in (0, 2):
            yield trial(
                module,
                "EnemyPhase",
                f"attack-ends-battle.shots-{shots}",
                units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 1, 0)],
                changes={"Combat.Enemy.0.Shots": shots},
                outcomes={"AttackUnit": 2},
            )
        yield trial(
            module,
            "EnemyPhase",
            "fatal-strike-no-retaliation",
            units=[
                ("Player", 0, 0, 20, 0, 0),
                ("Player", 1, 1, 20, 0, 4),
                ("Enemy", 0, 0, 20, 1, 0),
            ],
            changes={"Combat.Enemy.0.Shots": 0},
            outcomes={"AttackUnit": "kill-target"},
        )
        yield trial(
            module,
            "EnemyPhase",
            "retaliation-used-by-first-attacker",
            units=[
                ("Player", 0, 0, 20, 0, 0),
                ("Enemy", 0, 0, 1, 1, 0),
                ("Enemy", 1, 0, 1, 0, 1),
            ],
            changes={"Combat.Enemy.0.Shots": 0, "Combat.Enemy.1.Shots": 0},
        )
        yield trial(
            module,
            "EnemyPhase",
            "weaker-later-candidate",
            units=[
                ("Player", 0, 0, 100, 0, 0),
                ("Player", 1, 1, 1, 0, 4),
                ("Enemy", 0, 0, 20, 5, 4),
            ],
        )
        yield trial(
            module,
            "EnemyPhase",
            "flight-target-ring-occupied",
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 1, 20, 5, 4)],
            changes={"Combat.Enemy.0.CanFly": True},
            field=[(0, 1, 64), (1, 0, 64), (1, 1, 64)],
        )
        yield trial(
            module,
            "EnemyPhase",
            "no-adjacent-empty-cell",
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 5, 4)],
            changes={"Combat.Enemy.0.Shots": 0},
            field=[(4, 3, 64), (4, 4, 64), (5, 3, 64)],
        )
        yield trial(
            module,
            "EnemyPhase",
            "blocked-preference-attacks-adjacent-other-species",
            units=[
                ("Player", 0, 4, 20, 0, 0),
                ("Player", 1, 1, 20, 4, 4),
                ("Enemy", 0, 4, 20, 5, 4),
            ],
            changes={"Combat.Enemy.0.Shots": 0},
            field=[(4, 3, 64), (5, 3, 64)],
        )
        yield trial(
            module,
            "EnemyPhase",
            "diagonal-best-rank-tie",
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 2, 2)],
            changes={"Combat.Enemy.0.Shots": 0},
            field=[(1, 1, 64), (1, 2, 64), (2, 1, 64)],
        )
        for x, y in ((0, 3), (0, 4), (4, 0), (5, 0)):
            wall = [
                (x + dx, y + dy, 64)
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                if (dx or dy) and 0 <= x + dx < 6 and 0 <= y + dy < 5
            ]
            yield trial(
                module,
                "EnemyPhase",
                f"second-unit-blocked.{x}-{y}",
                units=[
                    ("Player", 0, 0, 20, 0, 0),
                    ("Enemy", 0, 0, 20, 5, 4),
                    ("Enemy", 1, 0, 20, x, y),
                ],
                field=wall,
                changes={"Combat.Enemy.0.Shots": 0, "Combat.Enemy.1.Shots": 0},
            )
        for ex, ey, px, py in ((1, 0, 0, 0), (4, 4, 5, 4), (0, 1, 0, 0), (2, 2, 1, 1)):
            for movement_species in (2, 4, 5):
                yield trial(
                    module,
                    "EnemyPhase",
                    f"archer-escape.{ex}-{ey}.player-{px}-{py}.species-{movement_species}",
                    units=[
                        ("Player", 0, 0, 20, px, py),
                        ("Enemy", 0, movement_species, 20, ex, ey),
                    ],
                    changes={"Combat.Enemy.0.Shots": 2},
                )
        for variant in range(16):
            walls = [
                (x, y, 64)
                for x in range(1, 5)
                for y in range(5)
                if ((x * 13 + y * 7 + variant * 3) % 11) < 3 and (x, y) != (2, 2)
            ]
            yield trial(
                module,
                "EnemyPhase",
                f"obstacle-layout-{variant}",
                units=[
                    ("Player", 0, 0, 20, 0, 0),
                    ("Player", 1, 2, 100, 0, 4),
                    ("Enemy", 0, 4, 20, 5, 2),
                ],
                changes={
                    "Combat.Enemy.0.Shots": 0,
                    "Combat.Enemy.0.CanFly": bool(variant % 2),
                },
                field=walls,
            )
        for ex, ey in ((5, 4), (1, 0), (4, 0), (0, 4), (2, 2)):
            for mode in (
                "walk",
                "shoot",
                "fly",
                "frozen",
                "poison1",
                "poison2",
                "poison3",
            ):
                changes = {
                    "Combat.Enemy.0.Shots": 2 if mode == "shoot" else 0,
                    "Combat.Enemy.0.CanFly": mode == "fly",
                    "Combat.FrozenEnemySlot": 0 if mode == "frozen" else 100,
                    "Combat.Poison.0": int(mode[-1])
                    if mode.startswith("poison")
                    else 0,
                }
                yield trial(
                    module,
                    "EnemyPhase",
                    f"position-{ex}-{ey}.{mode}",
                    changes=changes,
                    units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, ex, ey)],
                )
        for enemy_species in (0, 1, 5, 17, 23):
            yield trial(
                module,
                "EnemyPhase",
                f"target-priorities.{enemy_species}",
                units=[
                    ("Player", 0, 0, 20, 0, 0),
                    ("Player", 1, 1, 100, 0, 2),
                    ("Enemy", 0, enemy_species, 20, 5, 4),
                ],
                changes={"Combat.Enemy.0.Shots": 0},
            )
    elif module == "KBBDMG":
        for count in (21, 8193):
            losses = []
            for side, other in (("Player", "Enemy"), ("Enemy", "Player")):
                hit = trial(
                    module, "AttackUnit", f"attack-power.{side}.{count}",
                    units=[(side, 0, 6, count, 0, 0), (other, 0, 5, 5, 5, 4)],
                    args=[5, 4, 0, 0],
                    changes={"Campaign.WeeklySpecies": 5, "Campaign.DamageBonus": 0},
                )
                losses.append((hit, side))
            magic = trial(
                module, "ReportEnemyLoss", f"attack-power.{count}",
                units=[("Enemy", 0, 6, count, 0, 0)],
                args=[0, 0, 0],
                changes={
                    "Runtime.BattleTextColumn": 1,
                    "Combat.Enemy.0.HitPoints": count * 25 - 30,
                },
            )
            losses.append((magic, "Enemy"))

            for loss, side in losses:
                def attack_power_after_loss(v, loss=loss, side=side, count=count):
                    result = loss.run(v)
                    state = Battle.from_buffer_copy(bytes.fromhex(result["buffers"]["combat"]))
                    survivor = getattr(state, side)[0]
                    assert survivor.Count == count - 1
                    assert v.game().Runtime.BattleDistances[0][0] == count - 1
                    assert survivor.HitPoints == count * 25 - 30
                    assert survivor.AttackPower == (count - 1) * 8, survivor.AttackPower

                yield Case(loss.name, attack_power_after_loss, loss.identity)

        for label, species, count, health, healed_health in (
            ("wounded-ghost", 12, 1, 10, 25),
            ("wounded-vampire", 17, 1, 10, 50),
            ("ghost-at-limit", 12, 65535, 65535 * 70, 65535 * 70),
            ("vampire-at-limit", 17, 1, 90, 110),
        ):
            strike = trial(
                module,
                "AttackUnit",
                "healing." + label,
                units=[("Player", 0, species, count, 0, 0), ("Enemy", 0, 0, 2, 1, 0)],
                args=[0, 0, 1, 0],
                changes={
                    "Campaign.WeeklySpecies": species,
                    "Campaign.DamageBonus": 0,
                    "Combat.Player.0.HitPoints": health,
                },
            )

            def preserve_healed_unit(v, strike=strike, count=count, health=healed_health):
                result = strike.run(v)
                state = Battle.from_buffer_copy(bytes.fromhex(result["buffers"]["combat"]))
                attacker = state.Player[0]
                assert attacker.HitPoints == health, (attacker.HitPoints, health)
                assert attacker.Count == count, (attacker.Count, count)
                field_count = v.game().Runtime.BattleDistances[0][0]
                assert field_count == count, (field_count, count)

            yield Case(strike.name, preserve_healed_unit, strike.identity)

        seed = next(
            s
            for s in range(20000)
            if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) > 5
        )
        for hp in (1, 100000):
            yield trial(
                module,
                "ResolveStrike",
                f"demon-halving.hp-{hp}",
                args=[22, 0, 51, hp],
                seed=seed,
                changes={"Campaign.WeeklySpecies": 22},
            )
        yield trial(
            module,
            "AttackUnit",
            "demon-halving-animation",
            seed=seed,
            units=[("Player", 0, 22, 20, 0, 0), ("Enemy", 0, 0, 20, 5, 4)],
            args=[0, 0, 5, 4],
            changes={"Campaign.WeeklySpecies": 22, "Combat.Enemy.0.HitPoints": 100000},
        )
        yield trial(
            module,
            "AttackUnit",
            "resistant-dragon-loses-no-units",
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 23, 20, 5, 4)],
            args=[0, 0, 5, 4],
        )
        yield trial(
            module,
            "AttackUnit",
            "second-player-stack-survives",
            units=[
                ("Enemy", 0, 0, 20, 0, 0),
                ("Player", 0, 0, 20, 5, 4),
                ("Player", 1, 0, 20, 0, 4),
            ],
            args=[0, 0, 5, 4],
            changes={"Combat.Player.0.HitPoints": 1},
        )
        last_uncontrolled = trial(
            module,
            "AttackUnit",
            "last-uncontrolled-player-stack-dies",
            units=[("Enemy", 0, 5, 19, 5, 3), ("Player", 0, 7, 1, 1, 1)],
            args=[5, 3, 1, 1],
            changes={
                "Campaign.WeeklySpecies": 5,
                "Combat.PlayerCount": 0,
                "Combat.ReadyPlayerCount": 0,
                "Combat.Uncontrolled.0": True,
            },
        )

        def last_uncontrolled_defeat(v):
            last_uncontrolled.run(v)
            runtime = v.game().Runtime
            assert runtime.BattleField[1][1] == 0
            assert runtime.BattleResult == 2, runtime.BattleResult

        yield Case(last_uncontrolled.name, last_uncontrolled_defeat, last_uncontrolled.identity)
        yield trial(
            module,
            "ReportEnemyLoss",
            "redraw-other-unit-on-row",
            args=[0, 5, 0],
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 5, 0)],
            changes={"Runtime.BattleTextColumn": 65535},
        )
        for same in (False, True):

            def relocate_unit(v, same=same):
                g = v.fixture()
                g.Runtime.BattleField[0][0] = 112
                g.Runtime.BattleDistances[0][0] = 20
                v.set_game(g)
                x = v.alloc(b"\x00")
                y = v.alloc(b"\x00")
                tx = 0 if same else 1
                ready(v, v.invoke("RelocateUnit", x, y, tx, 0))
                after = v.game().Runtime
                assert (
                    after.BattleField[tx][0] == 112
                    and after.BattleDistances[tx][0] == 20
                )
                assert (
                    v.read(linear(x), 1) == bytes([tx])
                    and v.read(linear(y), 1) == b"\x00"
                )
                if not same:
                    assert (
                        after.BattleField[0][0] == 0
                        and after.BattleDistances[0][0] == 0
                    )

            yield Case(f"relocate-unit.same-{same}", relocate_unit)
        for attacker in (0, 12, 15, 17, 19, 21, 22, 23):
            for defender in (0, 19, 22, 23, 24, 25):
                for spent in (False, True):
                    yield trial(
                        module,
                        "ResolveStrike",
                        f"{attacker}-vs-{defender}.spent-{spent}",
                        args=[attacker, defender, 51, 10000],
                        changes={
                            "Combat.DragonResists": 6 if spent else 0,
                            "Combat.DemonResists": 4 if spent else 0,
                            "Combat.MutantResists.0": 4 if spent else 0,
                            "Campaign.WeeklySpecies": attacker if spent else 100,
                        },
                    )
        for defender_player in (False, True):
            for hp in (1, 10000):
                for attacker in (0, 12, 17, 22):
                    yield trial(
                        module,
                        "AttackUnit",
                        f"player-target-{defender_player}.hp-{hp}.attacker-{attacker}",
                        units=[
                            (
                                "Enemy" if defender_player else "Player",
                                0,
                                attacker,
                                20,
                                0,
                                0,
                            ),
                            ("Player" if defender_player else "Enemy", 0, 0, 20, 5, 4),
                        ],
                        args=[0, 0, 5, 4],
                        changes={
                            f"Combat.{'Player' if defender_player else 'Enemy'}.0.HitPoints": hp
                        },
                    )
        for x in (0, 5):
            for killed in (0, 1, 20, 65535):
                yield trial(
                    module,
                    "ReportEnemyLoss",
                    f"x-{x}.killed-{killed}",
                    args=[0, x, 0],
                    units=[("Enemy", 0, 0, 20, x, 0)],
                    changes={"Runtime.BattleTextColumn": killed},
                )
    elif module == "KBBSCENE":
        yield trial(
            module,
            "PaintBattleTerrain",
            "unsupported-island-no-obstacles",
            args=[0],
            changes={"Campaign.Island": 0},
        )
        for island in range(1, 6):
            for density in (0, 1, 5, 20):
                yield trial(
                    module,
                    "PaintBattleTerrain",
                    f"island-{island}.density-{density}",
                    args=[density],
                    changes={"Campaign.Island": island},
                )
    elif module == "KBBMAGIC":
        for label, scans, count, health, expected in (
            ("ordinary", [28], 20, 39, (35, 69, 0)),
            ("partial", [28], 65521, 131042, (65535, 131070, 0)),
            ("full-wounded", [28], 65535, 131069, (65535, 131070, 0)),
            ("full-healthy", [28], 65535, 131070, (65535, 131070, 1)),
            ("cancelled", [1], 20, 40, (20, 40, 1)),
            ("empty-cell", [77, 28], 20, 40, (20, 40, 1)),
        ):
            cast = trial(
                module,
                "MagicMenu",
                "multiply." + label,
                scans=[3, *scans],
                units=[("Player", 0, 0, count, 0, 0)],
                changes={
                    "Campaign.MagicPower": 1,
                    "Campaign.Scrolls.8": 1,
                    "Combat.Player.0.HitPoints": health,
                },
            )

            def multiply(v, cast=cast, expected=expected):
                result = cast.run(v)
                combat = Battle.from_buffer_copy(bytes.fromhex(result["buffers"]["combat"]))
                unit = combat.Player[0]
                game = v.game()
                actual = unit.Count, unit.HitPoints, game.Campaign.Scrolls[8]
                assert actual == expected, (actual, expected)
                assert game.Runtime.BattleDistances[0][0] == expected[0]

            yield Case(cast.name, multiply, cast.identity)

        for power, stock, expected_health in ((0, 1, 40), (1, 0, 70)):
            cast = trial(
                module,
                "SelectSpellTarget",
                f"multiply.power-{power}.stock-{stock}",
                spell=8,
                spends_scroll=False,
                scans=[28],
                units=[("Player", 0, 0, 20, 0, 0)],
                changes={"Campaign.MagicPower": power, "Campaign.Scrolls.8": stock},
            )

            def check_direct_cast(v, cast=cast, expected_health=expected_health):
                result = cast.run(v)
                state = Battle.from_buffer_copy(bytes.fromhex(result["buffers"]["combat"]))
                assert state.Player[0].HitPoints == expected_health
                assert state.Player[0].Count == expected_health // 2

            yield Case(cast.name, check_direct_cast, cast.identity)

        for label, scans, species, count, initial, health, expected in (
            ("ordinary", [28], 0, 20, 100, 39, (89, 139, 0)),
            ("overflow", [28], 0, 32743, 32744, 65486, (32744, 65488, 0)),
            ("wide-health", [28], 12, 999, 1000, 69930, (1000, 70000, 0)),
            ("full-wounded", [28], 0, 20, 20, 39, (20, 40, 0)),
            ("full-healthy", [28], 0, 32743, 32743, 65486, (32743, 65486, 1)),
            ("cancelled", [1], 0, 20, 30, 40, (20, 40, 1)),
            ("empty-cell", [77, 28], 0, 20, 30, 40, (20, 40, 1)),
        ):
            cast = trial(
                module,
                "MagicMenu",
                "resurrect." + label,
                scans=[7, *scans],
                units=[("Player", 0, species, count, 0, 0)],
                changes={
                    "Campaign.MagicPower": 2,
                    "Campaign.Scrolls.12": 1,
                    "Combat.Player.0.InitialCount": initial,
                    "Combat.Player.0.HitPoints": health,
                },
            )

            def resurrect(v, cast=cast, expected=expected):
                result = cast.run(v)
                combat = Battle.from_buffer_copy(bytes.fromhex(result["buffers"]["combat"]))
                unit = combat.Player[0]
                game = v.game()
                actual = unit.Count, unit.HitPoints, game.Campaign.Scrolls[12]
                assert actual == expected, (actual, expected)
                assert game.Runtime.BattleDistances[0][0] == expected[0]

            yield Case(cast.name, resurrect, cast.identity)

        for consume, stock in ((False, 1), (True, 0)):
            cast = trial(
                module,
                "SelectSpellTarget",
                f"resurrect.consume-{consume}.stock-{stock}",
                spell=12,
                consume=consume,
                spends_scroll=False,
                scans=[28],
                units=[("Player", 0, 0, 20, 0, 0)],
                changes={
                    "Campaign.MagicPower": 1,
                    "Campaign.Scrolls.12": stock,
                    "Combat.Player.0.InitialCount": 25,
                },
            )

            def check_resurrect_target(v, cast=cast):
                result = cast.run(v)
                combat = Battle.from_buffer_copy(bytes.fromhex(result["buffers"]["combat"]))
                assert combat.Player[0].Count == 25
                assert combat.Player[0].HitPoints == 50

            yield Case(cast.name, check_resurrect_target, cast.identity)

        yield trial(
            module,
            "SelectSpellTarget",
            "multiply-rounds-up",
            spell=8,
            scans=[28],
            units=[("Player", 0, 0, 20, 0, 0)],
            changes={"Combat.Player.0.HitPoints": 39},
        )
        yield trial(
            module,
            "SelectSpellTarget",
            "damage-reports-fatal-loss",
            spell=9,
            scans=[28],
            units=[("Enemy", 0, 0, 20, 0, 0)],
            responses={"ApplyDamage": 65535},
        )
        yield trial(
            module,
            "SelectSpellTarget",
            "teleport-already-selected",
            spell=7,
            scans=[1],
            changes={"Combat.TeleportSelected": True},
        )
        yield trial(
            module, "SelectSpellTarget", "unsupported-spell-byte", spell=0, scans=[28]
        )
        yield trial(module, "MagicMenu", "reject-unknown-key", scans=[0, 1])
        for spell in range(7, 14):
            for tile in (0, 32, 112):
                for consume in (False, True):
                    yield trial(
                        module,
                        "SelectSpellTarget",
                        f"spell-{spell}.tile-{tile}.consume-{consume}",
                        spell=spell,
                        consume=consume,
                        spends_scroll=False
                        if consume and (spell == 12 or (spell == 8 and tile != 112))
                        else None,
                        scans=[28, 28, 1],
                        units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 5, 4)],
                        field=[(0, 0, tile)],
                    )
        for scan in (71, 72, 73, 75, 77, 79, 80, 81):
            for cursor in ((0, 0), (3, 2), (5, 4)):
                yield trial(
                    module,
                    "SelectSpellTarget",
                    f"cursor-{cursor}.scan-{scan}",
                    cursor=cursor,
                    scans=[scan, 1],
                )
        for hp, initial in ((1, 100), (39, 20), (40, 20)):
            yield trial(
                module,
                "SelectSpellTarget",
                f"resurrect-{hp}-{initial}",
                spell=12,
                spends_scroll=False if hp == 40 and initial == 20 else None,
                scans=[28],
                units=[("Player", 0, 0, 20, 0, 0)],
                changes={
                    "Combat.Player.0.HitPoints": hp,
                    "Combat.Player.0.InitialCount": initial,
                },
            )
        for spell in range(7, 14):
            for scrolls in (0, 2):
                yield trial(
                    module,
                    "MagicMenu",
                    f"menu-{spell}.stock-{scrolls}",
                    scans=[spell - 5, 1],
                    changes={f"Campaign.Scrolls.{spell}": scrolls},
                )
        yield trial(module, "MagicMenu", "no-power", changes={"Campaign.MagicPower": 0})
    elif module == "KBBRES":
        for wanted in range(8):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 8 >> 32) == wanted
            )
            yield trial(
                module,
                "UncontrolledTurn",
                f"long-walk.initial-random-{wanted}",
                seed=seed,
                units=[("Player", 0, 4, 20, 0, 0)],
                changes={"Combat.Uncontrolled.0": True},
                field=[(1, 0, 64)],
            )
        neighbors = [(2 + dx, 2 + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]
        for start_direction in range(8):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 8 >> 32) == start_direction
            )
            for opening in [None, *neighbors]:
                specimen = trial(
                    module,
                    "UncontrolledTurn",
                    f"single-opening.direction-{start_direction}.{opening}",
                    seed=seed,
                    units=[("Player", 0, 0, 20, 2, 2)],
                    changes={"Combat.Uncontrolled.0": True},
                    field=[(*cell, 80) for cell in neighbors if cell != opening],
                )

                def single_opening(v, specimen=specimen, opening=opening):
                    specimen.run(v)
                    moves = [args[-2:] for _, name, args in v.calls if name == "RelocateUnit"]
                    assert moves == ([] if opening is None else [list(opening)]), moves

                yield Case(specimen.name, single_opening, specimen.identity)
        yield trial(
            module,
            "ReserveMenu",
            "unpopulated-reserve-row",
            keys=[9, 50, 27],
            units=[("Player", 5, 0, 20, -1, -1)],
        )
        yield trial(
            module,
            "ReserveMenu",
            "unpopulated-active-row",
            keys=[50, 27],
            units=[("Player", 1, 0, 20, 0, 0)],
        )
        yield trial(
            module,
            "ReserveMenu",
            "entry-column-blocked",
            keys=[9, 49, 27],
            units=[("Player", 5, 0, 20, -1, -1)],
            field=[(0, y, 64) for y in range(5)],
        )
        yield trial(
            module,
            "ReserveMenu",
            "reserve-capacity-exhausted",
            keys=[49, 27],
            units=[("Player", 0, 0, 20, 0, 0)]
            + [("Player", i, 0, 20, -1, -1) for i in range(5, 10)],
        )
        yield trial(
            module,
            "ReserveMenu",
            "unit-away-from-entry-column",
            keys=[27],
            units=[("Player", 0, 0, 20, 2, 2)],
        )
        for seed in range(16):
            for cursor in ((0, 0), (2, 2), (5, 4)):
                yield trial(
                    module,
                    "UncontrolledTurn",
                    f"random-{seed}.position-{cursor}",
                    seed=seed,
                    units=[("Player", 0, 0, 20, *cursor)],
                    changes={"Combat.Uncontrolled.0": True},
                )
        for side in ("Player", "Enemy"):
            for count in (0, 10):
                yield trial(
                    module,
                    "UncontrolledTurn",
                    f"attack-{side}.target-count-{count}",
                    units=[("Player", 0, 0, 20, 0, 0), (side, 1, 0, count, 1, 0)],
                    changes={"Combat.Uncontrolled.0": True},
                )
        for species in (0, 24, 25, 29):
            for count in (1, 5000):

                def leadership(vm, species=species, count=count):
                    g = vm.fixture()
                    g.Campaign.Leadership = 100
                    vm.set_game(g)
                    b = battle(vm)
                    b.Player[0].Species = species
                    b.Player[0].Count = count
                    if species >= 25:
                        src = vm.read(vm.addresses[1][0], C.sizeof(Creature))
                        vm.cpu.mem_write(
                            vm.addresses[1][0] + species * C.sizeof(Creature), src
                        )
                    p = vm.alloc(bytes(b))
                    ready(vm, vm.invoke("CheckLeadership", p))
                    out = Battle.from_buffer_copy(vm.read(linear(p), C.sizeof(b)))
                    definition = Creature.from_buffer_copy(
                        vm.read(
                            vm.addresses[1][0] + species * C.sizeof(Creature),
                            C.sizeof(Creature),
                        )
                    )
                    controlled = species >= 25 or count <= 100 // definition.Defense
                    assert out.PlayerCount == int(controlled) and out.Uncontrolled[
                        0
                    ] == (not controlled)

                yield Case(f"leadership.species-{species}.count-{count}", leadership)
        for keys in ((49, 27), (9, 49, 27), (49, 9, 49, 27), (9, 27)):
            for occupied in (False, True):
                units = [("Player", 0, 0, 20, 0, 0), ("Player", 5, 1, 10, -1, -1)]
                if occupied:
                    units.extend(
                        ("Player", slot, slot, 5, 0, slot) for slot in range(1, 5)
                    )
                yield trial(
                    module,
                    "ReserveMenu",
                    f"keys-{keys}.full-{occupied}",
                    keys=keys,
                    units=units,
                )
    elif module == "KBBDRAW":
        for stop_after in (63, 200, None):

            def pulses(v, stop_after=stop_after):
                preset(v)
                count = 0

                def pressed(vm, args):
                    nonlocal count
                    count += 1
                    return int(stop_after is not None and count > stop_after)

                v.responses["BIOSKeyPressed"] = pressed
                if stop_after == 200:
                    b = battle(v)
                    p = v.alloc(bytes(b))
                    result = v.invoke("AwaitCellKey", p, 0, 0, 15, 0)
                else:
                    result = v.invoke("PulseCell", 0, 0, 5)
                ready(v, result)
                delays = [event for event in v.effects if event[0] == "delay"]
                assert len(delays) == (
                    122 if stop_after is None else 199 if stop_after == 200 else 63
                )
                assert all(event == ("delay", 2) for event in delays)

            yield Case(f"pulse.keyboard-after-{stop_after}", pulses)
        yield trial(
            module,
            "AwaitCellKey",
            "unit-without-shots-or-flight",
            units=[("Player", 0, 0, 20, 0, 0)],
            changes={"Combat.Player.0.Shots": 0, "Combat.Player.0.CanFly": False},
            scans=[28],
        )
        for color in (0, 5, 12, 15):
            for state in ("ready", "moved", "uncontrolled", "terrain"):
                yield trial(
                    module,
                    "AwaitCellKey",
                    f"color-{color}.{state}",
                    scans=[28],
                    units=[("Player", 0, 0, 20, 0, 0)],
                    args=[0, 0, color, 3],
                    changes={
                        "Combat.CanMove.0": state == "ready",
                        "Combat.Uncontrolled.0": state == "uncontrolled",
                        "Combat.Player.0.CanFly": True,
                    },
                    field=[(0, 0, 0 if state == "terrain" else 112)],
                )
    elif module == "KBPLAYER":
        yield trial(
            module,
            "ShootUnit",
            "uncontrolled-ally-target",
            scans=[77, 28],
            units=[("Player", 0, 0, 20, 0, 0), ("Player", 1, 0, 20, 1, 0)],
            changes={"Combat.Uncontrolled.1": True},
        )
        yield trial(
            module,
            "ShootUnit",
            "empty-target-retry-and-unknown-key",
            scans=[0, 77, 28] + [77] * 4 + [80] * 4 + [28],
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 5, 4)],
        )
        for shots in (0, 2):
            yield trial(
                module,
                "MovePlayerUnit",
                f"shoot-shortcut.shots-{shots}",
                scans=[31, 1],
                units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 1, 0)],
                changes={"Combat.Player.0.Shots": shots},
            )
        yield trial(
            module,
            "MovePlayerUnit",
            "blocked-terrain",
            scans=[77, 1],
            units=[("Player", 0, 0, 20, 0, 0)],
            field=[(1, 0, 64)],
        )
        for allied in (False, True):
            yield trial(
                module,
                "MovePlayerUnit",
                f"zero-target-count.allied-{allied}",
                scans=[77],
                units=[
                    ("Player", 0, 0, 20, 0, 0),
                    ("Player" if allied else "Enemy", 1 if allied else 0, 0, 0, 1, 0),
                ],
                changes={"Combat.Uncontrolled.1": allied},
            )
        moves = {
            71: (-1, -1),
            72: (0, -1),
            73: (1, -1),
            75: (-1, 0),
            77: (1, 0),
            79: (-1, 1),
            80: (0, 1),
            81: (1, 1),
        }
        for cursor in ((0, 0), (3, 2), (5, 4)):
            for scan, (dx, dy) in moves.items():
                yield trial(
                    module,
                    "MovePlayerUnit",
                    f"cursor-{cursor}.scan-{scan}",
                    cursor=cursor,
                    scans=[scan, 1],
                    units=[("Player", 0, 0, 20, *cursor)],
                )
                x, y = cursor
                if 0 <= x + dx < 6 and 0 <= y + dy < 5:
                    x += dx
                    y += dy
                tx, ty = (5, 4) if cursor == (0, 0) else (0, 0)
                path = [77 if tx > x else 75] * abs(tx - x) + [
                    80 if ty > y else 72
                ] * abs(ty - y)
                yield trial(
                    module,
                    "ShootUnit",
                    f"cursor-{cursor}.scan-{scan}",
                    cursor=cursor,
                    scans=[scan, *path, 28],
                    units=[("Player", 0, 0, 20, *cursor), ("Enemy", 0, 0, 20, tx, ty)],
                )
        for allied in (False, True):
            for retaliations in (0, 2):
                yield trial(
                    module,
                    "MovePlayerUnit",
                    f"attack-allied-{allied}.retaliations-{retaliations}",
                    scans=[77],
                    units=[
                        ("Player", 0, 0, 20, 0, 0),
                        (
                            "Player" if allied else "Enemy",
                            1 if allied else 0,
                            0,
                            20,
                            1,
                            0,
                        ),
                    ],
                    changes={
                        "Combat.Uncontrolled.1": allied,
                        "Combat.Retaliations.0": retaliations,
                        "Combat.Retaliations.1": retaliations,
                    },
                )
        yield trial(
            module,
            "ShootUnit",
            "adjacent-enemy-blocks-shot",
            units=[("Player", 0, 0, 20, 0, 0), ("Enemy", 0, 0, 20, 1, 0)],
        )
        for base in (31, 111):
            for x, y in ((0, 0), (0, 4), (5, 0), (5, 4), (2, 2)):
                for present in (False, True):

                    def adjacent(vm, base=base, x=x, y=y, present=present):
                        g = vm.fixture()
                        tx, ty = (x + 1 if x < 5 else x - 1), y
                        if present:
                            g.Runtime.BattleField[tx][ty] = base + 1
                        vm.set_game(g)
                        px = vm.alloc(bytes([x]))
                        py = vm.alloc(bytes([y]))
                        result = ready(vm, vm.invoke("FindAdjacent", px, py, base))
                        assert result == int(present)
                        assert vm.read(linear(px), 1)[0] == (tx if present else x)
                        assert vm.read(linear(py), 1)[0] == y

                    yield Case(
                        f"adjacent.base-{base}.{x}-{y}.present-{present}", adjacent
                    )
        for current in range(5):
            for available in (True, False):
                yield trial(
                    module,
                    "NextPlayerUnit",
                    f"current-{current}.available-{available}",
                    units=[("Player", 0, 0, 20, 0, 0)],
                    changes={
                        "Runtime.CurrentBattleSlot": current,
                        "Combat.CanMove.0": available,
                    },
                )
