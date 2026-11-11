"""Characterise existing defects. No corrected behaviour is substituted."""

import ctypes as C
from cases import Case, ready
from characterise import preset, battle
from runtime import INDEX, Battle, linear


def cases(module):
    if module == "KBCAL":

        def equality(v):
            g = v.fixture()
            g.Campaign.Gold = 0
            g.Campaign.Income = 0
            v.set_game(g)
            result = v.invoke("EndWeek", instructions=20_000)
            assert result[1]["kind"] == "budget", result
            assert v.game().Campaign.Weeks == 99 and v.game().Campaign.Gold == 0

        yield Case("B001.zero-payroll-equality-does-not-return", equality)

        def wrong_island(v):
            g = v.fixture()
            c = g.Campaign.Castles[1][0]
            c.Owned = True
            g.Campaign.Map[1][c.X][c.Y] = 18
            g.Campaign.Map[0][c.X][c.Y] = 0
            v.set_game(g)
            ready(v, v.invoke("EndWeek"))
            after = v.game().Campaign
            assert not after.Castles[1][0].Owned
            assert after.Map[0][c.X][c.Y] == 2 and after.Map[1][c.X][c.Y] == 18

        yield Case("B002.empty-castle-changes-current-island-map", wrong_island)
    elif module == "KBEVENTS":

        def spirit_only_workshop(v):
            g = preset(v, True)
            g.Campaign.RitualStoneIsland = 1
            g.Campaign.RitualStonePosition.X = 30
            g.Campaign.RitualStonePosition.Y = 30
            g.Campaign.Hero.Y = 31
            g.Campaign.RitualPower = 100
            for i in range(7):
                g.Campaign.Flags.SpellAvailable[i] = False
            v.set_game(g)
            v.responses["CountRitualSpells"] = 1
            addresses = []
            observed = []
            entry = next(
                p["id"]
                for p in INDEX["points"]
                if p["file"] == "KBEVENTS.PAS"
                and p["routine"] == "TalkingStoneVisit.Workshop"
                and p["kind"] == "routine"
            )
            check = next(
                p["id"]
                for p in INDEX["points"]
                if p["file"] == "KBEVENTS.PAS"
                and p["source"].startswith(
                    "if Game.Runtime.LastScan = 28 then SelectDonor"
                )
            )

            def background(vm):
                ss = vm.r("ss") * 16
                parent = vm.word(ss + vm.r("bp"))
                base = ss + parent - 58
                addresses.append(base)
                vm.cpu.mem_write(base + 26, bytes([0] + [7] * 7))

            def cursor(vm):
                base = addresses[0]
                observed.append(
                    tuple(vm.read(base + offset, 1)[0] for offset in (47, 52, 57))
                )

            v.entry_probes[entry] = background
            v.entry_probes[check] = cursor
            v.scans.extend([28, 28] + [80] * 7 + [28, 28, 1])
            ready(v, v.invoke("TalkingStoneVisit"))
            assert observed and all(
                last == 255 and effect == 0 and current == 0
                for last, effect, current in observed
            ), observed
            assert not v.game().Campaign.Flags.SpellAvailable[0]
            assert any(a.Species == 25 for a in v.game().Campaign.Army)

        yield Case(
            "B019.spirit-only-workshop-uses-uninitialized-effect-zero",
            spirit_only_workshop,
        )
    elif module == "KBBATTLE":

        def partial_initialization(v):
            preset(v, True)
            entry = next(
                p["id"]
                for p in INDEX["points"]
                if p["file"] == "KBBATTLE.PAS"
                and p["routine"] == "Battle"
                and p["kind"] == "routine"
            )

            def dirty_stack(vm):
                ss = vm.r("ss") * 16
                parent_bp = vm.word(ss + vm.r("bp"))
                vm.cpu.mem_write(
                    ss + parent_bp - C.sizeof(Battle), b"\xa5" * C.sizeof(Battle)
                )

            v.entry_probes[entry] = dirty_stack
            observed = []

            def inspect(vm, args):
                combat = Battle.from_buffer_copy(
                    vm.read(linear(args[0]), C.sizeof(Battle))
                )
                observed.append(combat.Enemy[5].Species)
                g = vm.game()
                g.Runtime.LastScan = 68
                vm.set_game(g)
                return 0

            enemies = v.alloc(bytes([100]) * 5)
            counts = v.alloc(bytes(10))
            ready(
                v,
                v.invoke(
                    "Battle", enemies, counts, 0, responses={"AwaitCellKey": inspect}
                ),
            )
            assert observed and observed[0] == 165, observed

        yield Case(
            "B008.enemy-reserve-records-retain-stack-bytes", partial_initialization
        )
    elif module == "KBBMAGIC":

        def resurrect(v):
            g = v.fixture()
            g.Campaign.MagicPower = 1
            g.Campaign.Scrolls[12] = 1
            g.Runtime.BattleField[0][0] = 112
            g.Runtime.BattleDistances[0][0] = 4
            v.set_game(g)
            combat = battle(v)
            combat.PlayerCount = 1
            p = combat.Player[0]
            p.Species = 23
            p.Count = 4
            p.InitialCount = 10
            p.HitPoints = 4000
            pointer = v.alloc(bytes(combat))
            v.scans.append(28)
            ready(v, v.invoke("SelectSpellTarget", pointer, 12, 1))
            after = Battle.from_buffer_copy(v.read(linear(pointer), C.sizeof(Battle)))
            assert (after.Player[0].Count, after.Player[0].HitPoints) == (8, 4050)
            assert v.game().Campaign.Scrolls[12] == 0

        yield Case("B009.resurrection-count-includes-existing-distance", resurrect)
    elif module == "KBHERO":

        def surrounded(v):
            g = v.fixture()
            c = g.Campaign
            c.HiddenSpellIsland = 1
            c.HiddenSpellPosition.X = 30
            c.HiddenSpellPosition.Y = 30
            for x in range(29, 32):
                for y in range(29, 32):
                    c.Map[0][x][y] = 1
            c.Map[0][30][30] = 0
            v.set_game(g)
            ready(v, v.invoke("SearchRitualSpell"))
            after = v.game().Campaign
            assert after.Map[0][after.Hero.X][after.Hero.Y] == 1
            assert (after.Hero.X, after.Hero.Y) == (31, 31)

        yield Case("B011.surrounded-ritual-lands-in-blocked-cell", surrounded)
    elif module == "KBSAVE":

        def markers(v):
            g = v.fixture()
            g.World.WizardPosition.X = 20
            g.World.WizardPosition.Y = 21
            g.World.MagePosition.X = 22
            g.World.MagePosition.Y = 23
            g.Campaign.Map[0][20][21] = 12
            g.Campaign.Map[0][22][23] = 28
            v.set_game(g)
            ready(v, v.invoke("PrepareSave"))
            after = v.game().Campaign
            assert after.Map[0][20][21] == 0 and after.Map[0][22][23] == 0

        yield Case("B012.prepare-save-removes-actor-markers", markers)
    elif module == "KBWIZARD":

        def overflow(v):
            g = v.fixture()
            g.Campaign.MagicPower = 255
            g.Campaign.WizardRelations[0] = 5
            v.set_game(g)
            ready(v, v.invoke("WizardVisit", keys=[50, 27]))
            assert v.game().Campaign.MagicPower == 0
            assert any(
                name == "PaymentFailed" and args == [5000] for _, name, args in v.calls
            )

        yield Case("B013.power-purchase-wraps-byte-to-zero", overflow)
