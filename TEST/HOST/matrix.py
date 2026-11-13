"""Named boundary matrices: one command or transition per independent fixture."""

import json
import struct
from cases import Case
from characterise import preset, arguments, tree, projection
from runtime import INDEX


def sample(
    module,
    routine,
    label,
    *,
    rich=True,
    values=None,
    keys=(),
    scans=(),
    changes=None,
    terrain=None,
    workers=False,
    responses=None,
    seed=None,
    files=None,
    idle_polls=0,
    printer=False,
):
    spec = dict(
        module=module,
        routine=routine,
        label=label,
        rich=rich,
        values=values,
        keys=keys,
        scans=scans,
        changes=changes,
        terrain=terrain,
        workers=workers,
        responses=responses,
        seed=seed,
        files=files,
        idle_polls=idle_polls,
        printer=printer,
    )

    def execute(vm):
        g = preset(vm, rich)
        for path, value in (changes or {}).items():
            target = g
            parts = path.split(".")
            for name in parts[:-1]:
                target = target[int(name)] if name.isdigit() else getattr(target, name)
            if parts[-1].isdigit():
                target[int(parts[-1])] = value
            else:
                setattr(target, parts[-1], value)
        if workers:
            for name in ("Carpenters", "Woodcutters", "Diggers", "Stonecutters"):
                setattr(g.Campaign, name, 10)
        if terrain is not None:
            for x in range(28, 33):
                for y in range(28, 33):
                    g.Campaign.Map[g.Campaign.Island - 1][x][y] = terrain
        vm.set_game(g)
        if seed is not None:
            vm.cpu.mem_write(vm.addresses[2][0], struct.pack("<I", seed))
        for name, data in (files or {}).items():
            vm.disk[name] = data.encode("ascii")
        if printer:
            vm.support(65535)
        if idle_polls:
            point = next(
                p["id"]
                for p in INDEX["points"]
                if p["file"] == "KBAPP.PAS" and p["source"] == "Delay(2)"
            )

            def wake(v):
                if v.hits[point] >= idle_polls:
                    v.keys.append(120)

            vm.entry_probes[point] = wake
        vm.scans.extend(scans)
        entry = next(
            e for e in INDEX["modules"][module]["entries"] if e["name"] == routine
        )
        args, watch = arguments(vm, entry, rich)
        if values is not None:
            args = list(values)
        before = tree(vm.game())
        disk = vm.disk.copy()
        before_creatures = vm.read(vm.addresses[1][0], 540)
        result = vm.invoke(
            routine,
            *args,
            keys=keys,
            responses=responses,
            instructions=120_000_000 if module == "KBMAP" else 2_000_000,
            seconds=30 if module == "KBMAP" else 3,
        )
        assert result[1]["kind"] in ("ready", "exit"), result
        if printer:
            vm.support(65534)
        return projection(vm, before, watch, result, disk, before_creatures)

    return Case(routine + ".matrix." + label, execute, json.dumps(spec, sort_keys=True))


def cases(module):
    if module in ("KBWORLD", "KBADVENT"):
        seed1 = (12345 * 134775813 + 1) & 0xFFFFFFFF
        seed2 = (seed1 * 134775813 + 1) & 0xFFFFFFFF
        x = seed1 * 65 >> 32
        y = seed2 * 65 >> 32
        if module == "KBWORLD":
            for routine in ("PlaceRoamingObject", "RelocateArmy"):
                yield sample(
                    module,
                    routine,
                    "reject-occupied-first-cell",
                    changes={f"Campaign.Map.0.{x}.{y}": 7},
                )
            for island in (0, 6):
                yield sample(
                    module, "EnterIsland", f"boundary-island-{island}", values=[island]
                )
        else:
            yield sample(
                module,
                "RandomHeroLanding",
                "reject-occupied-first-cell",
                changes={f"Campaign.Map.0.{x}.{y}": 7},
            )
            seed3 = (seed2 * 134775813 + 1) & 0xFFFFFFFF
            px = seed2 * 65 >> 32
            py = seed3 * 65 >> 32
            yield sample(
                module,
                "PlaceHiddenSpell",
                "reject-occupied-first-cell",
                rich=False,
                changes={f"Campaign.Map.{i}.{px}.{py}": 7 for i in range(5)},
            )
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 148 >> 32) >= 100
            )
            yield sample(
                module,
                "TransmuteDwellings",
                "upper-species-wrap",
                seed=seed,
                values=[1],
                changes={"Campaign.MagicPower": 2},
            )
            yield sample(
                module,
                "EncounterLanding",
                "opposite-heading",
                changes={
                    "Runtime.ShipAbandonBlocked": True,
                    "Campaign.Flags.Heading": True,
                    "Campaign.ShipHeading": 0,
                },
            )
    if module == "KBLOAD":
        seed1 = (12345 * 134775813 + 1) & 0xFFFFFFFF
        seed2 = (seed1 * 134775813 + 1) & 0xFFFFFFFF
        x = seed1 * 65 >> 32
        y = seed2 * 65 >> 32
        yield sample(
            module,
            "PrepareLoadedCampaign",
            "two-paper-scrolls-and-ship",
            changes={
                "Campaign.Map.0.20.20": 9,
                "Campaign.Map.0.21.21": 9,
                "Campaign.Flags.ShipOwned": True,
                f"Campaign.Map.0.{x}.{y}": 7,
            },
        )
        yield sample(
            module,
            "PrepareLoadedCampaign",
            "no-spirit-stone",
            changes={f"Campaign.Map.4.{x}.10": 0 for x in (10, 20, 30, 40, 50)},
        )
    if module == "KBMAP":
        terrain = {
            f"Campaign.Map.0.{x}.{y}": (
                (
                    0,
                    1,
                    2,
                    3,
                    4,
                    5,
                    7,
                    8,
                    9,
                    10,
                    11,
                    12,
                    14,
                    18,
                    22,
                    23,
                    28,
                    32,
                    48,
                    64,
                    80,
                )[(x + y) % 21]
            )
            for x in range(5, 61)
            for y in range(5, 61)
        }
        for owned in (False, True):
            yield sample(
                module,
                "MapVisit",
                f"color-map.owned-{owned}",
                values=[1],
                scans=[57, 57, 1],
                changes={**terrain, "Campaign.Flags.LocalMapOwned.0": owned},
            )
        for island in range(1, 6):
            yield sample(
                module,
                "MapVisit",
                f"print.island-{island}",
                values=[island],
                scans=[63, 1],
                printer=True,
                changes={**terrain, f"Campaign.Flags.LocalMapOwned.{island - 1}": True},
            )
    if module == "KBSTART":
        yield sample(
            module, "StartupMenu", "difficulty-down-then-up", scans=[28, 80, 72, 28]
        )
        yield sample(module, "StartupMenu", "main-menu-wrap", scans=[72, 80, 28, 28])
        yield sample(
            module,
            "StartupMenu",
            "named-menu-down-and-up",
            scans=[72, 28, 80, 72, 28],
            files={"ONE.KB2": "", "TWO.KB2": ""},
        )
        yield sample(
            module,
            "StartupMenu",
            "named-more-than-ten-files",
            scans=[72, 28, 28],
            files={f"SAVE{i:02}.KB2": "" for i in range(12)},
        )
        for difficulty in range(4):
            yield sample(
                module,
                "StartupMenu",
                f"new.difficulty-{difficulty}",
                scans=[28] + [80] * difficulty + [28],
            )
        yield sample(module, "StartupMenu", "new.wrap", scans=[28, 72, 80, 28])
        for files in ({}, {"ONE.KB2": ""}, {"ONE.KB2": "", "TWO.KB2": ""}):
            scans = [72, 28, 72, 28] if not files else [72, 28, 72, 80, 28]
            yield sample(
                module,
                "StartupMenu",
                "named-" + str(tuple(files)),
                files=files,
                scans=scans,
            )
    if module == "KBCAL":
        for balance, income in ((1, 0), (10, 0), (100000, 0), (0, 1000)):
            for restock in (False, True):
                yield sample(
                    module,
                    "EndWeek",
                    f"gold-{balance}.income-{income}.restock-{restock}",
                    scans=[1, 1],
                    changes={
                        "Campaign.Gold": balance,
                        "Campaign.Income": income,
                        "Runtime.WorkerRestockPhase": restock,
                    },
                )
        yield sample(
            module, "EndWeek", "last-week", scans=[1, 1], changes={"Campaign.Weeks": 1}
        )
    if module == "KBSESS":
        for contract in (1, 100):
            for siege in (False, True):
                yield sample(
                    module,
                    "RestoreControls",
                    f"contract-{contract}.siege-{siege}",
                    changes={
                        "Campaign.ContractIsland": contract,
                        "Campaign.Flags.SiegeEngineOwned": siege,
                    },
                )
        for mode in (0, 1):
            yield sample(module, "SetGraphicsMode", f"mode-{mode}", values=[mode])
        for kind in (2, 5):
            yield sample(
                module,
                "VictoryReport",
                f"kind-{kind}",
                values=[0, kind],
                scans=[1],
                changes={
                    "Runtime.BattleValue": 10000,
                    "Campaign.WanderingArmies.0.0.X": 30,
                    "Campaign.WanderingArmies.0.0.Y": 30,
                },
            )
        for lead in (0, 10000):
            yield sample(
                module,
                "DefeatReport",
                f"leadership-{lead}",
                scans=[1],
                changes={
                    "Campaign.Leadership": lead,
                    "Runtime.BattleValue": 10000,
                    "Campaign.Flags.ShipOwned": True,
                },
            )
    if module == "KBDWELL":
        yield sample(
            module,
            "DwellingVisit",
            "second-dwelling",
            changes={"World.GenerationX": 14, "World.GenerationY": 35},
        )
        for species in (0, 20, 23):
            for lead in (0, 10000):
                yield sample(
                    module,
                    "DwellingVisit",
                    f"species-{species}.leadership-{lead}",
                    changes={
                        "Campaign.Dwellings.0.0.Species": species,
                        "Campaign.Leadership": lead,
                    },
                )
    if module == "KBAPP":
        for polls in (3, 210):
            yield sample(
                module,
                "WaitForCommand",
                f"idle-polls-{polls}",
                idle_polls=polls,
                changes={"Runtime.IdlePowerPhase": 1},
            )
        commands = (
            0,
            17,
            18,
            19,
            20,
            22,
            23,
            24,
            25,
            30,
            31,
            32,
            33,
            34,
            46,
            47,
            48,
            49,
            50,
            68,
            71,
            72,
            73,
            75,
            77,
            79,
            80,
            81,
        )
        for scan in commands:
            for blocked in (False, True):
                yield sample(
                    module,
                    "DispatchCommand",
                    f"scan-{scan}.ship-{blocked}",
                    changes={
                        "Runtime.LastScan": scan,
                        "Runtime.ShipAbandonBlocked": blocked,
                    },
                )
        for scan in (71, 72, 73, 75, 77, 79, 80, 81):
            for x, y in ((2, 2), (63, 63)):
                yield sample(
                    module,
                    "DispatchCommand",
                    f"boundary-{x}-{y}.scan-{scan}",
                    changes={
                        "Runtime.LastScan": scan,
                        "World.GenerationX": x,
                        "World.GenerationY": y,
                    },
                )
        for scan in (71, 72, 73, 75, 77, 79, 80, 81):
            for heading in (False, True):
                for ship in (False, True):
                    yield sample(
                        module,
                        "UpdateHeroFacing",
                        f"scan-{scan}.heading-{heading}.ship-{ship}",
                        changes={
                            "Runtime.LastScan": scan,
                            "Campaign.Flags.Heading": heading,
                            "Runtime.ShipAbandonBlocked": ship,
                        },
                    )
        for tile in (
            0,
            2,
            4,
            5,
            7,
            8,
            9,
            10,
            11,
            12,
            14,
            18,
            22,
            23,
            28,
            32,
            48,
            64,
            80,
        ):
            for ship in (False, True):
                yield sample(
                    module,
                    "ResolveMovement",
                    f"tile-{tile}.ship-{ship}",
                    changes={
                        "Runtime.LastScan": 72,
                        "Runtime.ShipAbandonBlocked": ship,
                        "Runtime.WorldMapPending": 1,
                        "Runtime.RegrowthCountdown": 1,
                        "Campaign.Map.0.30.30": tile,
                    },
                )
        for days, extra in ((0, 0), (1, 0), (2, 0), (200, 1), (200, 2)):
            yield sample(
                module,
                "AdvanceAdventureTime",
                f"days-{days}.extra-{extra}",
                changes={"Campaign.Days": days, "Campaign.ExtraDays": extra},
            )
        for ship in (False, True):
            for scans in ((1,), (21, 1), (21, 21)):
                yield sample(
                    module,
                    "ConfirmExit",
                    f"ship-{ship}.answers-{scans}",
                    scans=scans,
                    changes={"Runtime.ShipAbandonBlocked": ship},
                )
    if module == "KBSAVEUI":
        for keys in (
            (13,),
            (27,),
            (8, 13),
            (65, 8, 13),
            (65, 66, 8, 67, 13),
            tuple(b"ABCDEFGH"),
            (0, 65, 13),
            (47, 48, 13),
        ):
            yield sample(module, "SaveNamedGame", "edit-" + str(keys), keys=keys)
    if module == "KBVISIT":
        for reserve in range(1, 6):
            for power in (0, 40):
                yield sample(
                    module,
                    "WanderingArmyVisit",
                    f"reserve-{reserve}.power-{power}",
                    scans=[49],
                    changes={
                        **{f"Campaign.Army.{i + 5}.Species": 0 for i in range(reserve)},
                        "Campaign.MagicPower": power,
                    },
                )
        yield sample(
            module, "WanderingArmyVisit", "report-joined", responses={"ArmyReport": 1}
        )
        yield sample(
            module,
            "WanderingArmyVisit",
            "grace-with-empty-army",
            rich=False,
            changes={"Campaign.EnemyGrace": 1},
        )
        yield sample(
            module,
            "WanderingArmyVisit",
            "battle-lost",
            scans=[21],
            changes={"Runtime.BattleResult": 2},
            responses={"Battle": 0},
        )
        yield sample(
            module,
            "WanderingArmyVisit",
            "cannot-decline-standing-on-army",
            scans=[49, 21],
            changes={"Campaign.Map.0.30.30": 5},
        )
        yield sample(
            module,
            "RitualGuardianVisit",
            "battle-lost",
            scans=[21],
            changes={"Runtime.BattleResult": 2},
            responses={"Battle": 0, "ArmyReport": 1},
        )
        yield sample(
            module,
            "RitualGuardianVisit",
            "second-spell",
            scans=[21, 1],
            responses={"CountRitualSpells": 2},
        )
        for tile in (0, 5, 14):
            yield sample(
                module,
                "RegrowMountain",
                f"overwrites-tile-{tile}",
                changes={
                    "Campaign.Island": 5,
                    "Runtime.RegrowthPosition.X": 29,
                    "Runtime.RegrowthPosition.Y": 30,
                    "Runtime.RegrowthCountdown": 1,
                    f"Campaign.Map.4.29.30": tile,
                    "Campaign.WanderingArmies.4.0.X": 29,
                    "Campaign.WanderingArmies.4.0.Y": 30,
                },
            )
        yield sample(
            module,
            "TreasureVisit",
            "unrecognised-key-before-reward",
            seed=12,
            keys=[48, 49],
        )
        yield sample(
            module,
            "FindWanderingArmy",
            "second-entry",
            values=[31, 30],
            changes={
                "Campaign.WanderingArmies.0.1.X": 31,
                "Campaign.WanderingArmies.0.1.Y": 30,
            },
        )
        for count in (0, 2, 3, 7, 8, 14, 15, 39):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 40 >> 32) == count
            )
            for key in (49, 50):
                yield sample(
                    module,
                    "TreasureVisit",
                    f"roll-{count}.choice-{key}",
                    seed=seed,
                    keys=[key],
                    scans=[1],
                )
        for days, extra in ((0, 0), (1, 0), (29, 0), (30, 0), (200, 5)):
            yield sample(
                module,
                "SandLanding",
                f"days-{days}.extra-{extra}",
                changes={"Campaign.Days": days, "Campaign.ExtraDays": extra},
            )
        for army in (False, True):
            for scan in (21, 49):
                yield sample(
                    module,
                    "WanderingArmyVisit",
                    f"army-{army}.answer-{scan}",
                    scans=[scan],
                    changes={"Campaign.Flags.ArmyAvailable": army},
                )
                yield sample(
                    module,
                    "RitualGuardianVisit",
                    f"army-{army}.answer-{scan}",
                    scans=[scan, 1],
                    changes={"Campaign.Flags.ArmyAvailable": army},
                    responses={"CountRitualSpells": 1},
                )
        for x, y in ((30, 30), (30, 29), (29, 30)):
            yield sample(
                module,
                "UndergroundVisit",
                f"entrance-{x}-{y}",
                changes={
                    "Campaign.Underground.0.0.X": 30,
                    "Campaign.Underground.0.0.Y": 30,
                    "Campaign.Underground.0.1.X": 40,
                    "Campaign.Underground.0.1.Y": 40,
                    "World.GenerationX": x,
                    "World.GenerationY": y,
                },
            )
        for countdown in (1, 2):
            for occupied in (False, True):
                yield sample(
                    module,
                    "RegrowMountain",
                    f"countdown-{countdown}.occupied-{occupied}",
                    changes={
                        "Runtime.RegrowthCountdown": countdown,
                        "Runtime.RegrowthPosition.X": 30,
                        "Runtime.RegrowthPosition.Y": 30,
                        "World.GenerationX": 30 if occupied else 31,
                        "Campaign.Map.4.29.30": 80,
                        "Campaign.Map.4.31.30": 80,
                        "Campaign.Map.4.30.29": 80,
                        "Campaign.Map.4.30.31": 80,
                    },
                )
    if module == "KBSCROLL":
        for army_count in (0, 1):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 149 >> 32) // 10 == 2
            )
            yield sample(
                module,
                "PaperScrollVisit",
                f"dismiss-army-count-{army_count}",
                rich=False,
                seed=seed,
                scans=[28, 1],
                changes={
                    "Campaign.Army.0.Species": 0 if army_count else 100,
                    "Campaign.Army.0.Count": 3,
                },
            )
        for event in (0, 4):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 149 >> 32) // 10 == event
            )
            yield sample(
                module,
                "PaperScrollVisit",
                f"edge-event-{event}",
                seed=seed,
                scans=[28, 1],
                changes={
                    "Campaign.Flags.ShipOwned": True,
                    "Campaign.Contracts.0.0.Island": 100,
                },
            )
        yield sample(
            module,
            "PaperScrollVisit",
            "chart-already-unlocked",
            scans=[28, 1],
            changes={"Campaign.Flags.PaperChartPresent.0": True},
        )
        for event in range(15):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 149 >> 32) // 10 == event
            )
            yield sample(
                module,
                "PaperScrollVisit",
                f"event-{event}",
                seed=seed,
                scans=[1, 1],
                changes={
                    "Campaign.Flags.PaperChartPresent.0": False,
                    "Campaign.ContractIsland": 100,
                },
            )
        for island in range(1, 6):
            yield sample(
                module,
                "PaperScrollVisit",
                f"chart-island-{island}",
                scans=[1],
                changes={
                    "Campaign.Island": island,
                    "Campaign.UnlockedIslands": 1,
                    f"Campaign.Flags.PaperChartPresent.{island - 1}": True,
                },
            )
    if module == "KBEVENTS":
        for event, changes in (
            (0, {"Campaign.MagicPower": 0}),
            (5, {"Campaign.Leadership": 100000}),
            (9, {"Campaign.Weeks": 1}),
        ):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 119 >> 32) // 10 == event
            )
            yield sample(
                module,
                "BlackMage",
                f"edge-event-{event}",
                seed=seed,
                scans=[28, 1],
                changes=changes,
            )
        yield sample(
            module,
            "TalkingStoneVisit",
            "town-hint-second-island",
            changes={
                "Campaign.Island": 2,
                "Runtime.WorldMapRedraw": 1,
                "Runtime.InstructionCounter": 0,
            },
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "cached-event-out-of-range",
            changes={"Runtime.WorldMapRedraw": 1, "Runtime.InstructionCounter": 255},
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "ritual-stone-wrong-side",
            changes={
                "Campaign.RitualStoneIsland": 1,
                "Campaign.RitualStonePosition.X": 30,
                "Campaign.RitualStonePosition.Y": 30,
            },
        )
        workshop = {
            "Campaign.RitualStoneIsland": 1,
            "Campaign.RitualStonePosition.X": 30,
            "Campaign.RitualStonePosition.Y": 30,
            "Campaign.Hero.Y": 31,
            "Campaign.RitualPower": 100,
        }
        sparse = {
            **workshop,
            **{f"Campaign.Army.{i}.Species": 100 for i in (0, 1, 3, 4)},
        }
        for direction in (72, 80):
            yield sample(
                module,
                "TalkingStoneVisit",
                f"workshop.sparse-donor-wrap-{direction}",
                scans=[28, direction, 28, 1],
                changes=sparse,
                responses={"CountRitualSpells": 7},
            )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop-insufficient-skill",
            changes={**workshop, "Campaign.MagicPower": 9},
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop-donor-forward-wrap",
            scans=[28, 80, 80, 80, 80, 80, 28, 1],
            changes={**workshop, "Campaign.Army.4.Species": 100},
            responses={"CountRitualSpells": 7},
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop-donor-direction-bounds",
            scans=[28, 72, 80, 80, 80, 80, 80, 72, 28, 1],
            changes=workshop,
            responses={"CountRitualSpells": 7},
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop.all-mutants-used",
            scans=[1, 1],
            changes={
                **workshop,
                **{f"Campaign.Army.{i}.Species": 25 + i for i in range(5)},
            },
            responses={"CountRitualSpells": 7},
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop.donor-wrap",
            scans=[28, 72, 28, 1],
            changes={
                **workshop,
                "Campaign.Army.0.Species": 100,
                "Campaign.Army.1.Species": 100,
                "Campaign.Army.3.Species": 100,
            },
            responses={"CountRitualSpells": 7},
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop.effect-bounds",
            scans=[72] + [80] * 9 + [72, 28, 28, 1],
            changes=workshop,
            responses={"CountRitualSpells": 7},
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop.report-clamp",
            scans=[28, 28, 1],
            changes={
                **workshop,
                "Campaign.Army.0.Species": 23,
                "Campaign.Army.0.Count": 65535,
            },
            responses={"CountRitualSpells": 7},
        )
        for effect in range(7):
            yield sample(
                module,
                "TalkingStoneVisit",
                f"workshop.effect-{effect}",
                scans=[28, 28] + [80] * effect + [28, 80, 28, 1],
                changes=workshop,
                responses={"CountRitualSpells": 7},
            )
        for power in (0, 1, 10):
            yield sample(
                module,
                "TalkingStoneVisit",
                f"workshop.power-{power}",
                scans=[28, 28, 1],
                changes={**workshop, "Campaign.RitualPower": power},
                responses={"CountRitualSpells": 7},
            )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop.no-spells",
            scans=[1],
            changes=workshop,
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop.no-army",
            rich=False,
            scans=[1],
            changes={**workshop, "Campaign.Difficulty": 3},
            responses={"CountRitualSpells": 7},
        )
        yield sample(
            module,
            "TalkingStoneVisit",
            "workshop.donor-cancel",
            scans=[28, 1, 1],
            changes=workshop,
            responses={"CountRitualSpells": 7},
        )
        for event in range(12):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 119 >> 32) // 10 == event
            )
            for rich in (False, True):
                yield sample(
                    module,
                    "BlackMage",
                    f"event-{event}.rich-{rich}",
                    seed=seed,
                    rich=rich,
                    scans=[1],
                    changes={
                        "Campaign.Flags.ShipOwned": rich,
                        "Campaign.Carpenters": 10,
                        "Campaign.Diggers": 10,
                        "Campaign.Woodcutters": 10,
                        "Campaign.Stonecutters": 10,
                    },
                )
        for event in range(16):
            yield sample(
                module,
                "TalkingStoneVisit",
                f"cached-hint-{event}",
                scans=[1],
                changes={
                    "Runtime.WorldMapRedraw": 1,
                    "Runtime.InstructionCounter": event,
                },
            )
        for power, hidden, difficulty, island in (
            (0, 1, 3, 1),
            (10, 100, 3, 1),
            (10, 1, 4, 1),
            (10, 1, 3, 2),
        ):
            yield sample(
                module,
                "TalkingStoneVisit",
                f"hint-{power}-{hidden}-{difficulty}-{island}",
                scans=[1],
                changes={
                    "Runtime.WorldMapRedraw": 1,
                    "Runtime.InstructionCounter": 6,
                    "Campaign.MagicPower": power,
                    "Campaign.HiddenSpellIsland": hidden,
                    "Campaign.Difficulty": difficulty,
                    "Campaign.Island": island,
                },
            )
        yield sample(
            module,
            "TalkingStoneVisit",
            "spirit-ritual",
            scans=[1],
            changes={
                "Campaign.Island": 5,
                "Campaign.Cargo.6": 100,
                "Campaign.Flags.SpellAvailable.7": True,
                "Runtime.SpiritStonePosition.X": 30,
                "Runtime.SpiritStonePosition.Y": 30,
            },
        )
    if module == "KBCASTLE":
        yield sample(
            module,
            "CastleVisit",
            "zero-quest-contract-second-castle",
            scans=[21],
            changes={
                "World.GenerationX": 18,
                "Campaign.ContractIsland": 1,
                "Campaign.ContractSlot": 1,
                "Campaign.Contracts.0.0.Slot": 2,
                "Campaign.QuestFlags.0": 0,
                "Campaign.WizardVisited.0": 1,
            },
        )
        yield sample(
            module,
            "CastleVisit",
            "overflow-reserve-selection",
            keys=[9, 49, 54, 27],
            changes={
                "Campaign.Castles.0.0.Owned": True,
                **{f"Campaign.Castles.0.0.Species.{i}": i for i in range(5)},
            },
        )
        for roll in range(5):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 5 >> 32) == roll
            )
            yield sample(
                module,
                "CastleVisit",
                f"hostile-greeting-{roll}",
                seed=seed,
                scans=[49],
                changes={"Campaign.QuestFlags.0": 100},
            )
        yield sample(
            module, "CastleVisit", "blocked-approach", changes={"World.GenerationY": 55}
        )
        yield sample(
            module,
            "CastleVisit",
            "already-visited",
            keys=[27],
            changes={
                "Campaign.VisitedCastles.0.Island": 1,
                "Campaign.VisitedCastles.0.Slot": 1,
            },
        )
        yield sample(
            module,
            "CastleVisit",
            "second-castle-journal-occupied",
            scans=[49],
            changes={
                "World.GenerationX": 18,
                "Campaign.VisitedCastles.0.Island": 1,
                "Campaign.VisitedCastles.0.Slot": 3,
            },
        )
        yield sample(
            module,
            "CastleVisit",
            "buy-map-already-owned",
            keys=[49, 27],
            responses={"PaymentFailed": 1},
        )
        yield sample(
            module,
            "CastleVisit",
            "reward-reject-key-map-part-owned",
            keys=[50, 0, 51],
            changes={"Campaign.QuestFlags.0": 0, "Campaign.WizardVisited.0": 2},
        )
        yield sample(
            module,
            "CastleVisit",
            "garrison-empty-active-selection",
            rich=False,
            keys=[9, 49, 27],
            changes={"Campaign.Castles.0.0.Owned": True},
        )
        yield sample(
            module,
            "CastleVisit",
            "mutants-not-left-in-garrison",
            keys=[27],
            changes={
                "Campaign.Castles.0.0.Owned": True,
                "Campaign.Castles.0.0.Species.0": 25,
            },
        )
        yield sample(
            module,
            "CastleVisit",
            "contract-completed-zero-quest",
            scans=[21],
            changes={
                "World.GenerationX": 18,
                "Campaign.ContractIsland": 1,
                "Campaign.ContractSlot": 1,
                "Campaign.Contracts.0.0.Slot": 2,
                "Campaign.QuestFlags.0": 0,
            },
        )
        for visited in range(4):
            for result in (1, 2):
                yield sample(
                    module,
                    "CastleVisit",
                    f"siege.visited-{visited}.result-{result}",
                    scans=[21],
                    changes={
                        "Campaign.QuestFlags.0": 100,
                        "Campaign.WizardVisited.0": visited,
                        "Campaign.ContractIsland": 1,
                        "Campaign.ContractSlot": 1,
                        "Runtime.BattleResult": result,
                    },
                    responses={"Battle": 0},
                )
        for castle_full in (False, True):
            for army_full in (False, True):
                troops = {
                    f"Campaign.Castles.0.0.Species.{i}": i
                    if castle_full or i == 0
                    else 100
                    for i in range(5)
                }
                troops.update(
                    {
                        f"Campaign.Army.{i}.Species": i + 1 if army_full else 100
                        for i in range(5, 10)
                    }
                )
                troops.update(
                    {"Campaign.Castles.0.0.Owned": True, "Campaign.ContractIsland": 100}
                )
                for keys in (
                    (49, 27),
                    (9, 49, 27),
                    (9, 49, 49, 27),
                    (9, 49, 9, 50, 27),
                ):
                    yield sample(
                        module,
                        "CastleVisit",
                        f"transfer-{keys}.castle-full-{castle_full}.army-full-{army_full}",
                        keys=keys,
                        changes=troops,
                    )
        for matching in (False, True):
            yield sample(
                module,
                "CastleVisit",
                f"garrison-recruit.match-{matching}",
                keys=[49, 27],
                changes={
                    "Campaign.Castles.0.0.Owned": True,
                    "Campaign.ContractIsland": 100,
                    "Campaign.Castles.0.0.Species.0": 20 if matching else 1,
                    "Campaign.Castles.0.0.Counts.0": 10,
                    "Campaign.Army.0.Species": 20 if matching else 100,
                },
            )
        for key in range(49, 53):
            yield sample(
                module,
                "CastleVisit",
                f"poor-reward-{key}",
                rich=False,
                keys=[50, key],
                changes={"Campaign.QuestFlags.0": 0},
            )
        for key in (49, 50, 51):
            yield sample(
                module,
                "CastleVisit",
                f"ruler-menu-{key}",
                keys=[key, 27],
                scans=[1],
                changes={"Campaign.ContractIsland": 100},
            )
        for choice in range(49, 53):
            yield sample(
                module,
                "CastleVisit",
                f"ruler-reward-{choice}",
                keys=[50, choice],
                changes={"Campaign.QuestFlags.0": 0, "Campaign.ContractIsland": 100},
            )
        for quest in (1, 2, 4, 5, 6, 9):
            yield sample(
                module,
                "CastleVisit",
                f"audience-progress-{quest}",
                keys=[50],
                scans=[1],
                changes={
                    "Campaign.QuestFlags.0": quest,
                    "Campaign.WizardVisited.0": 1,
                    "Campaign.ContractIsland": 100,
                },
            )
        for owned in (False, True):
            for siege, army in ((False, False), (True, False), (True, True)):
                yield sample(
                    module,
                    "CastleVisit",
                    f"hostile-owned-{owned}.siege-{siege}.army-{army}",
                    scans=[21],
                    keys=[27],
                    changes={
                        "Campaign.QuestFlags.0": 100,
                        "Campaign.ContractIsland": 100,
                        "Campaign.Castles.0.0.Owned": owned,
                        "Campaign.Flags.SiegeEngineOwned": siege,
                        "Campaign.Flags.ArmyAvailable": army,
                    },
                )
        for keys in ((49, 27), (9, 49, 27), (49, 9, 49, 27), (54, 27)):
            yield sample(
                module,
                "CastleVisit",
                "garrison-" + str(keys),
                keys=keys,
                changes={
                    "Campaign.Castles.0.0.Owned": True,
                    "Campaign.ContractIsland": 100,
                },
            )
    if module == "KBUI":
        for notice in (24, 255):
            yield sample(
                module, "ShowNotice", f"boundary-{notice}", values=[notice], scans=[28]
            )
        for prompt in range(31):
            yield sample(module, "HeaderPrompt", str(prompt), values=[prompt])
        for notice in range(24):
            yield sample(module, "ShowNotice", str(notice), values=[notice], scans=[28])
        yield sample(
            module, "DrawTime", "extra-days", changes={"Campaign.ExtraDays": 30}
        )
    if module == "KBHELP":
        yield sample(
            module,
            "AdventureHelp",
            "ritual-spells-present",
            responses={"CountRitualSpells": 1},
        )
    if module == "KBVIEW":
        yield sample(
            module,
            "DrawAdventureField",
            "aboard-ship",
            changes={"Runtime.ShipAbandonBlocked": True},
        )
    if module == "KBSOUND":
        for cue in range(9):
            for muted in (False, True):
                yield sample(
                    module,
                    "PlayCue",
                    f"{cue}.muted-{muted}",
                    values=[cue],
                    changes={"Runtime.SoundDisabled": muted},
                )
    if module == "KBHUD":
        for gold in (
            49999,
            50000,
            74999,
            75000,
            199999,
            200000,
            499999,
            500000,
            799999,
            800000,
        ):
            yield sample(
                module,
                "RefreshGold",
                f"extra-boundary-{gold}",
                changes={"Campaign.Gold": gold},
            )
        for power in range(23):
            yield sample(
                module,
                "RefreshMagic",
                str(power),
                changes={"Campaign.MagicPower": power},
            )
        for gold in (
            -1,
            0,
            1999,
            2000,
            4999,
            5000,
            9999,
            10000,
            99999,
            100000,
            999999,
            1000000,
            2147483647,
        ):
            yield sample(
                module, "RefreshGold", str(gold), changes={"Campaign.Gold": gold}
            )
        for parts in range(7):
            yield sample(
                module,
                "RefreshMapParts",
                str(parts),
                changes={"Campaign.MapParts": parts},
            )
    if module == "KBART":
        for creature in range(30):
            yield sample(module, "LoadCreatureArt", str(creature), values=[creature])
    if module == "KBWORKER":
        for job in range(1, 5):
            yield sample(
                module, "WorkersMenu", f"no-worker-{job}", values=[1], keys=[48 + job]
            )
        yield sample(
            module,
            "WorkersMenu",
            "dig-adjacent-water",
            values=[1],
            keys=[51, (72,)],
            workers=True,
            changes={
                "Campaign.Map.0.30.28": 48,
                "Campaign.Map.0.30.30": 48,
                "Campaign.Map.0.29.29": 48,
                "Campaign.Map.0.31.29": 48,
            },
        )
        yield sample(
            module,
            "WorkersMenu",
            "fell-isolated-tree",
            values=[1],
            keys=[50, (72,)],
            workers=True,
            changes={"Campaign.Map.0.30.29": 64},
        )
        yield sample(
            module,
            "WorkersMenu",
            "non-direction-extended-key",
            values=[1],
            keys=[50, (59,)],
            workers=True,
        )
        for job, base in ((1, 48), (2, 64), (3, 0), (4, 80)):
            for island in (1, 5):
                for scan in (72, 75, 77, 80):
                    yield sample(
                        module,
                        "WorkersMenu",
                        f"job-{job}.island-{island}.direction-{scan}",
                        values=[island],
                        keys=[48 + job, (scan,), 27],
                        workers=True,
                        terrain=base,
                        changes={"Campaign.Island": island},
                    )
            yield sample(
                module,
                "WorkersMenu",
                f"job-{job}.wrong-terrain",
                values=[1],
                keys=[48 + job, (72,), 27],
                workers=True,
                terrain=16,
            )
            yield sample(
                module,
                "WorkersMenu",
                f"job-{job}.cancel-direction",
                values=[1],
                keys=[48 + job, 27, 27],
                workers=True,
            )
    if module == "KBMAGIC":
        yield sample(
            module, "AdventureMagic", "unrecognised-key-before-choice", scans=[0, 2]
        )
        for routine, collection in (
            ("CastleTeleport", "VisitedCastles"),
            ("TownTeleport", "VisitedTowns"),
        ):
            visited = {
                f"Campaign.{collection}.{i}.{field}": (
                    i // 5 + 1 if field == "Island" else i % 5 + 1
                )
                for i in range(12)
                for field in ("Island", "Slot")
            }
            yield sample(
                module,
                routine,
                "cursor-far-boundaries",
                scans=[75, 77, 77, 80, 80, 80, 1],
                changes=visited,
            )
        yield sample(
            module,
            "TownTeleport",
            "blocked-arrival",
            scans=[28],
            changes={
                "Campaign.VisitedTowns.0.Island": 1,
                "Campaign.VisitedTowns.0.Slot": 1,
                **{
                    f"Campaign.Map.0.{x}.{y}": 7
                    for x in range(7, 10)
                    for y in range(7, 10)
                },
            },
        )
        for arrangement in ("empty", "matching", "full"):
            troops = {
                f"Campaign.Army.{i}.Species": 100
                if arrangement == "empty"
                else 0
                if arrangement == "matching" and i == 0
                else i + 1
                for i in range(10)
            }
            yield sample(
                module, "SummonArmy", f"army-{arrangement}", scans=[28], changes=troops
            )
        yield sample(
            module,
            "SummonArmy",
            "no-power",
            scans=[28],
            changes={"Campaign.MagicPower": 0},
        )
        for routine in ("SummonArmy", "GiftScroll"):
            yield sample(
                module,
                routine,
                "cursor-bounds",
                scans=[80, 72, 77, 75, 77, 77] + [80] * 15 + [28],
            )
        yield sample(
            module, "AdventureMagic", "no-power", changes={"Campaign.MagicPower": 0}
        )
        yield sample(
            module,
            "AdventureMagic",
            "small-grace",
            scans=[3],
            changes={"Campaign.MagicPower": 1},
        )
        for routine, collection in (
            ("CastleTeleport", "VisitedCastles"),
            ("TownTeleport", "VisitedTowns"),
        ):
            locations = {
                f"Campaign.{collection}.{i}.{field}": (
                    i // 5 + 1 if field == "Island" else i % 5 + 1
                )
                for i in range(12)
                for field in ("Island", "Slot")
            }
            for scans in (
                (28,),
                (72, 28),
                (80, 28),
                (77, 28),
                (77, 75, 28),
                (77, 72, 28),
                (1,),
            ):
                yield sample(
                    module,
                    routine,
                    "visited-" + str(scans),
                    scans=scans,
                    changes=locations,
                )
        for scroll in range(7):
            yield sample(
                module,
                "AdventureMagic",
                f"scroll-{scroll}.empty",
                rich=False,
                scans=[scroll + 2, 1],
            )
        for menu in range(2, 9):
            yield sample(module, "AdventureMagic", f"menu-{menu}", scans=[menu, 28, 1])
        for days in (0, 499, 500):
            yield sample(
                module,
                "CastTimeStop",
                f"cap-{days}",
                changes={"World.TimeStopAccumulated": days},
            )
        for key in (72, 75, 77, 80, 28, 1):
            yield sample(
                module, "GiftScroll", f"key-{key}", scans=[key, 28] if key != 1 else [1]
            )
            yield sample(
                module, "SummonArmy", f"key-{key}", scans=[key, 28] if key != 1 else [1]
            )
    if module == "KBHERO":
        yield sample(
            module,
            "DismissArmy",
            "last-stack",
            rich=False,
            keys=[48],
            changes={"Campaign.Army.0.Species": 0, "Campaign.Army.0.Count": 3},
        )
        yield sample(
            module,
            "DismissArmy",
            "unpopulated-row",
            rich=False,
            keys=[0, 57],
            changes={"Campaign.Army.1.Species": 0, "Campaign.Army.1.Count": 3},
        )
        yield sample(
            module,
            "RitualSpellReport",
            "partly-known-spells",
            scans=[1],
            responses={"CountRitualSpells": 1},
            changes={f"Campaign.Flags.SpellAvailable.{i}": i == 0 for i in range(8)},
        )
        yield sample(
            module,
            "SeaVoyage",
            "unrecognised-key-and-locked-menu",
            keys=[0, 27],
            changes={"Campaign.UnlockedIslands": 1},
        )
        yield sample(
            module,
            "CastTornado",
            "army-and-mage",
            changes={
                "Campaign.TornadoCharges": 1,
                "Campaign.Map.0.29.30": 5,
                "Campaign.Map.0.30.30": 28,
                "World.MagePosition.X": 30,
                "World.MagePosition.Y": 30,
                "Campaign.WanderingArmies.0.0.X": 29,
                "Campaign.WanderingArmies.0.0.Y": 30,
            },
        )
        for used in (False, True):
            yield sample(
                module,
                "RitualSpellReport",
                f"spells-used-{used}",
                scans=[1],
                changes={f"Campaign.Flags.SpellUsed.{i}": used for i in range(8)},
                responses={"CountRitualSpells": 8},
            )
        for lead in (0, 1):
            yield sample(
                module,
                "SearchRitualSpell",
                f"leadership-{lead}",
                changes={"Campaign.Leadership": lead},
            )
        for known in (False, True):
            yield sample(
                module,
                "HeroStatus",
                f"picture-cached-{known}",
                scans=[1],
                changes={"Runtime.TownPictureLoaded": known},
            )
        for contract in (1, 100):
            yield sample(
                module,
                "CurrentContract",
                f"contract-{contract}",
                keys=[27],
                changes={
                    "Campaign.ContractIsland": contract,
                    "Campaign.ContractSlot": 1,
                },
            )
        for shore in (False, True):
            yield sample(
                module,
                "SeaVoyage",
                f"island-five.road.shore-{shore}",
                keys=[53],
                changes={
                    "Campaign.Island": 5,
                    "Campaign.Map.4.30.30": 4,
                    "Campaign.ExtraDays": 1,
                    "Campaign.Map.4.29.30": 32 if shore else 0,
                    "Campaign.Map.4.31.30": 32 if shore else 0,
                    "Campaign.Map.4.30.29": 32 if shore else 0,
                    "Campaign.Map.4.30.31": 32 if shore else 0,
                },
            )
        for key in range(49, 55):
            yield sample(module, "SeaVoyage", f"island-menu-{key - 48}", keys=[key, 27])
        for row in range(5):
            yield sample(module, "DismissArmy", f"row-{row}", keys=[48 + row])
        yield sample(module, "SeaVoyage", "locked", rich=False, keys=[54, 27])
    if module == "KBARMY":
        yield sample(
            module,
            "ArmyOverview",
            "select-filled-overflow-row",
            keys=[9, 49, 54, 27, 27],
            changes={f"Campaign.Army.{i}.Species": i for i in range(5, 10)},
        )
        yield sample(
            module,
            "ArmyOverview",
            "empty-reserve-row",
            rich=False,
            keys=[9, 9, 49, 27, 27],
            changes={
                "Campaign.Flags.ArmyAvailable": True,
                "Campaign.Army.1.Species": 0,
                "Campaign.Army.1.Count": 3,
            },
        )
        for filled in (False, True):
            troops = {
                f"Campaign.Army.{i}.Species": i if filled else 100 for i in range(5, 10)
            }
            for keys in (
                (9, 49, 49, 27, 27),
                (9, 9, 54, 27, 27),
                (9, 49, 9, 54, 27, 27),
                (9, 49, 49, 49, 27, 27),
            ):
                yield sample(
                    module,
                    "ArmyOverview",
                    f"reserve-back-transfer.{keys}.filled-{filled}",
                    keys=keys,
                    changes=troops,
                )
        yield sample(
            module,
            "ArmyOverview",
            "mutant-overview",
            keys=[27],
            changes={"Campaign.Army.0.Species": 25},
        )
        for reserve in (False, True):
            reserves = {
                f"Campaign.Army.{i}.Species": i if reserve else 100
                for i in range(5, 10)
            }
            for keys in (
                (9, 49, 27, 27),
                (9, 9, 49, 27, 27),
                (9, 49, 9, 49, 27, 27),
                (9, 54, 27, 27),
            ):
                yield sample(
                    module,
                    "ArmyOverview",
                    f"arrange-{keys}.reserve-{reserve}",
                    keys=keys,
                    changes=reserves,
                )
        yield sample(
            module,
            "ArmyOverview",
            "leadership-exceeded",
            keys=[27],
            changes={"Campaign.Leadership": 0},
        )
        for keys in (
            (49, 27),
            (50, 27),
            (51, 27),
            (52, 27),
            (53, 27),
            (9, 27),
            (48, 27),
            (13, 27),
        ):
            yield sample(
                module, "ArmyOverview", "keys-" + "-".join(map(str, keys)), keys=keys
            )
    if module == "KBTOWN":
        yield sample(
            module,
            "TownVisit",
            "offer-skip-completed-and-owned",
            keys=[49, 27],
            scans=[49],
            changes={
                "Runtime.CurrentContractOffer": 1,
                "Campaign.Contracts.0.1.Island": 100,
                "Campaign.Castles.0.2.Owned": True,
            },
        )
        yield sample(
            module,
            "TownVisit",
            "second-town-journal-occupied",
            keys=[27],
            changes={
                "World.GenerationX": 18,
                "World.GenerationY": 8,
                "Campaign.VisitedTowns.0.Island": 1,
                "Campaign.VisitedTowns.0.Slot": 3,
            },
        )
        for product in range(7):
            for amount in (0, 1, 10):
                yield sample(
                    module,
                    "TownVisit",
                    f"sell-product-{product}.stock-{amount}",
                    keys=[55, 9, 49 + product, 27, 27],
                    changes={
                        f"Campaign.Cargo.{product}": amount,
                        f"Campaign.CargoMaxPrices.{product}": 100,
                    },
                )
        for job in range(2, 6):
            yield sample(
                module,
                "TownVisit",
                f"worker-market-{job}",
                keys=[54, 27],
                scans=[job, 1],
            )
        for owned, blocked in ((False, False), (True, False), (True, True)):
            yield sample(
                module,
                "TownVisit",
                f"ship-owned-{owned}.aboard-{blocked}",
                keys=[50, 27],
                changes={
                    "Campaign.Flags.ShipOwned": owned,
                    "Runtime.ShipAbandonBlocked": blocked,
                },
            )
        for capacity in (0, 27, 28, 29):
            yield sample(
                module,
                "TownVisit",
                f"scroll-capacity-{capacity}",
                keys=[52, 27],
                scans=[1],
                changes={"Campaign.ScrollCapacity": capacity},
            )
        for island in range(2, 6):
            for owned in (False, True):
                yield sample(
                    module,
                    "TownVisit",
                    f"island-{island}.relic-{owned}",
                    keys=[56, 27],
                    changes={
                        "Campaign.Island": island,
                        "World.GenerationX": 8,
                        "World.GenerationY": 8 + (island - 1) * 8,
                        f"Campaign.Relics.{island - 2}.Owned": owned,
                        "Runtime.TownPictureLoaded": False,
                    },
                )
        for key in range(49, 57):
            yield sample(
                module, "TownVisit", f"menu-{key - 48}", keys=[key, 27, 27, 27, 27]
            )
        for balance in (0, 499, 500, 3000):
            yield sample(
                module,
                "TownVisit",
                f"ship-money-{balance}",
                keys=[50, 27],
                changes={"Campaign.Gold": balance},
            )
    if module == "KBWIZARD":
        for island in (1, 5):
            yield sample(
                module,
                "WizardVisit",
                f"travel-unlocks.from-{island}",
                keys=[51, 53, 0, 50],
                changes={
                    "Campaign.Island": island,
                    "Campaign.UnlockedIslands": 1,
                    "Campaign.HighestVisitedIsland": 1,
                    "Campaign.Flags.ShipOwned": True,
                },
            )
        yield sample(module, "WizardVisit", "travel-existing-island", keys=[51, 49])
        yield sample(module, "WizardVisit", "hire-reject-key", keys=[49, 0, 49])
        yield sample(
            module,
            "WizardVisit",
            "contract-missing",
            keys=[52],
            changes={"Campaign.MagicPower": 1, "Campaign.ContractIsland": 100},
        )
        yield sample(
            module,
            "WizardVisit",
            "contract-dismiss-delay",
            keys=[52],
            scans=[28, 1],
            changes={
                "Campaign.MagicPower": 1,
                "Campaign.ContractIsland": 1,
                "Campaign.ContractSlot": 1,
            },
        )
        yield sample(
            module,
            "WizardVisit",
            "instructions-unsupported-difficulty",
            keys=[52],
            changes={"Campaign.Difficulty": 4},
        )
        yield sample(
            module,
            "WizardVisit",
            "instructions-empty-already-known",
            keys=[52],
            changes={"Campaign.Flags.InstructionsShown": True},
        )
        yield sample(
            module,
            "WizardVisit",
            "instructions-page-and-intro-delay",
            keys=[52],
            scans=[28, 1, 28, 1],
            changes={f"Campaign.Flags.SpellAvailable.{i}": i == 0 for i in range(8)},
            responses={"CountRitualSpells": 1},
        )
        seed = next(
            s
            for s in range(20000)
            if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) >= 6
        )
        yield sample(module, "WizardVisit", "offer-reroll", keys=[27], seed=seed)
        seed = next(
            s
            for s in range(20000)
            if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) == 1
        )
        yield sample(
            module,
            "WizardVisit",
            "map-part-already-owned",
            keys=[54],
            seed=seed,
            changes={"Campaign.WizardVisited.0": 2},
        )
        for offer in range(1, 7):
            seed = next(
                s
                for s in range(20000)
                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) + 1 == offer
            )
            yield sample(module, "WizardVisit", f"offer-{offer}", keys=[54], seed=seed)
        for job in range(49, 53):
            for power in (0, 10):
                for failed in (0, 1):
                    yield sample(
                        module,
                        "WizardVisit",
                        f"hire-{job}.power-{power}.payment-failed-{failed}",
                        keys=[49, job],
                        changes={"Campaign.MagicPower": power},
                        responses={"PaymentFailed": failed},
                    )
        for power in (0, 9, 10):
            for known in (False, True):
                yield sample(
                    module,
                    "WizardVisit",
                    f"instructions.power-{power}.known-{known}",
                    keys=[52],
                    changes={
                        "Campaign.MagicPower": power,
                        "Campaign.Flags.InstructionsShown": known,
                        "Campaign.ContractIsland": 1,
                        "Campaign.ContractSlot": 1,
                    },
                    responses={"CountRitualSpells": 7},
                )
        for key in (50, 51, 52, 53, 54):
            yield sample(
                module,
                "WizardVisit",
                f"payment-failure-{key}",
                keys=[key],
                changes={"Campaign.MagicPower": 0},
                responses={"PaymentFailed": 1},
            )
        for affinity in range(7):
            for key in range(49, 55):
                yield sample(
                    module,
                    "WizardVisit",
                    f"affinity-{affinity}.menu-{key - 48}",
                    keys=[key, 27, 27, 27],
                    changes={"Campaign.WizardRelations.0": affinity},
                )
