"""Local world effects with independent coordinate and visibility checks."""

import struct
from cases import Case, ready
from runtime import linear


def cases(module):
    if module == "KBVISIT":
        for current in (1, 5):
            for island, slot in ((1, 2), (5, 7)):

                def lookup(v, current=current, island=island, slot=slot):
                    g = v.fixture()
                    g.Campaign.Island = current
                    for land, index in ((0, 2), (4, 7)):
                        g.Campaign.WanderingArmies[land][index].X = 30
                        g.Campaign.WanderingArmies[land][index].Y = 30
                    v.set_game(g)
                    assert ready(v, v.invoke("FindWanderingArmy", island, 30, 30)) == slot
                    assert v.game().Campaign.Island == current

                yield Case(f"army-lookup.current-{current}.island-{island}", lookup)

            def regrow(v, current=current):
                g = v.fixture()
                g.Campaign.Island = current
                g.Runtime.RegrowthPosition.X = 30
                g.Runtime.RegrowthPosition.Y = 30
                g.Runtime.RegrowthCountdown = 1
                g.World.GenerationX = 31
                g.World.GenerationY = 30
                for land, slot, x, y in ((0, 2, 30, 30), (4, 2, 25, 25), (4, 7, 30, 30)):
                    army = g.Campaign.WanderingArmies[land][slot]
                    army.X, army.Y = x, y
                    g.Campaign.Map[land][x][y] = 5
                v.set_game(g)
                g.Campaign.WanderingArmies[4][7].X = 255
                g.Campaign.Map[4][30][30] = 80
                ready(v, v.invoke("RegrowMountain"))
                after = v.game()
                assert bytes(after.Campaign.WanderingArmies) == bytes(g.Campaign.WanderingArmies)
                assert bytes(after.Campaign.Map) == bytes(g.Campaign.Map)
                assert after.Campaign.Island == current
                assert after.Runtime.RegrowthCountdown == 0
                assert after.Runtime.RegrowthPosition.X == 100

            yield Case(f"regrowth.army-on-island-5.hero-{current}", regrow)

            def visit(v, current=current):
                g = v.fixture()
                g.Campaign.Island = current
                slot = 2 if current == 1 else 7
                army = g.Campaign.WanderingArmies[current - 1][slot]
                army.X = army.Y = 30
                army.Species[:] = [2, 3, 100, 100, 100]
                army.Counts[:] = [37, 42, 0, 0, 0]
                v.set_game(g)
                reports = []

                def report(vm, args):
                    assert vm.read(linear(args[0]), 5) == bytes(army.Species)
                    assert vm.read(linear(args[1]), 10) == bytes(army.Counts)
                    reports.append(True)
                    return 1

                v.responses["ArmyReport"] = report
                ready(v, v.invoke("WanderingArmyVisit"))
                assert reports == [True]

            yield Case(f"army-visit.current-island-{current}", visit)
        return
    if module == "KBHERO":
        for island in (1, 5):

            def tornado(v, island=island):
                g = v.fixture()
                g.Campaign.Island = island
                g.Campaign.TornadoCharges = 1
                g.Campaign.Map[island - 1][29][30] = 5
                v.set_game(g)
                queries = []

                def lookup(vm, args):
                    assert list(args) == [island, 29, 30]
                    queries.append(list(args))
                    return 7

                v.responses["FindWanderingArmy"] = lookup
                ready(v, v.invoke("CastTornado"))
                assert queries == [[island, 29, 30]]
                assert [a for _, n, a in v.calls if n == "RelocateArmy"] == [[island, 7]]
                assert v.game().Campaign.Map[island - 1][29][30] == 0
                assert v.game().Campaign.TornadoCharges == 0

            yield Case(f"tornado.army-current-island-{island}", tornado)
        return
    if module == "KBSCROLL":
        for event, scratch in ((1, 0), (1, 10), (8, None)):

            def paper_wait(v, event=event, scratch=scratch):
                g = v.fixture()
                g.Campaign.Flags.PaperChartPresent[0] = False
                v.set_game(g)
                seed = next(s for s in range(20000)
                            if (((s * 134775813 + 1) & 0xFFFFFFFF) * 149 >> 32) // 10 == event)
                v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))
                reads = []
                visits = []

                def read(vm, args):
                    reads.append(len(reads) + 1)
                    assert len(reads) <= (1 if event == 1 else 2), "Extra key read after wizard"
                    return 28 if event == 1 else (2 if len(reads) == 1 else 1)

                def wizard(vm, args):
                    visits.append(True)
                    state = vm.game()
                    state.Runtime.ActionScratch = scratch
                    state.Runtime.LastScan = 27
                    vm.set_game(state)
                    return 0

                v.responses["ReadScanCode"] = read
                v.responses["WizardVisit"] = wizard
                ready(v, v.invoke("PaperScrollVisit"))
                after = v.game().Campaign
                assert visits == ([True] if event == 1 else [])
                assert len(reads) == (1 if event == 1 else 2)
                assert after.Flags.PaperChartPresent[0]
                assert after.Gold == g.Campaign.Gold * (2 if event == 8 else 1)
                assert any(n == "RefreshGold" for _, n, _ in v.calls)
                assert [a[0] for _, n, a in v.calls if n == "HeaderPrompt"] == (
                    [0] if event == 1 else [5, 0])

            yield Case(f"paper-result-wait.event-{event}.wizard-scratch-{scratch}", paper_wait)
        return
    if module != "KBADVENT":
        return
    directions = ((-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0))
    for direction, (dx, dy) in enumerate(directions):
        for blocked in (False, True):

            def roamer(v, direction=direction, dx=dx, dy=dy, blocked=blocked):
                g = v.fixture()
                g.Campaign.Difficulty = 3
                g.Campaign.Map[0][30][30] = 12
                if blocked:
                    g.Campaign.Map[0][30 + dx][30 + dy] = 7
                v.set_game(g)
                p = v.alloc(bytes((30, 30, 0)))
                seed = next(
                    s
                    for s in range(20000)
                    if (((s * 134775813 + 1) & 0xFFFFFFFF) * 79 >> 32) // 10
                    == direction
                )
                v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))
                ready(v, v.invoke("MoveRoamer", 1, 12, p))
                after = v.game().Campaign
                assert v.read(linear(p), 3) == (
                    bytes((30, 30, 1)) if blocked else bytes((30 + dx, 30 + dy, 1))
                )
                assert after.Map[0][30][30] == (12 if blocked else 0)
                if not blocked:
                    assert after.Map[0][30 + dx][30 + dy] == 12

            yield Case(f"roamer.direction-{direction}.blocked-{blocked}", roamer)

    def aged(v):
        g = v.fixture()
        g.Campaign.Difficulty = 3
        g.Campaign.Map[0][30][30] = 12
        v.set_game(g)
        p = v.alloc(bytes((30, 30, 4)))
        ready(v, v.invoke("MoveRoamer", 1, 12, p))
        assert (
            v.read(linear(p) + 2, 1) == b"\x00"
            and v.game().Campaign.Map[0][30][30] == 0
        )
        assert any(
            name == "PlaceRoamingObject" and args[:2] == [1, 12]
            for _, name, args in v.calls
        )

    yield Case("roamer.age-expiry", aged)
    for power in (0, 1, 3, 5, 11):
        for protected in (False, True):

            def visibility(v, power=power, protected=protected):
                g = v.fixture()
                g.Campaign.MagicPower = power
                for island in range(5):
                    for i, d in enumerate(g.Campaign.Dwellings[island]):
                        d.Species = 10 + 2 * i
                        g.Campaign.Map[island][d.X][d.Y] = 7 if protected else 0
                v.set_game(g)
                ready(v, v.invoke("RefreshDwellings"))
                after = v.game().Campaign
                for island in range(5):
                    for d in after.Dwellings[island]:
                        visible = (
                            (power > 0 and 9 < d.Species < 15)
                            or (power > 2 and 14 < d.Species < 20)
                            or (power > 4 and 19 < d.Species < 22)
                            or (power > 10 and 21 < d.Species < 25)
                        )
                        assert after.Map[island][d.X][d.Y] == (
                            7 if protected else 8 if visible else 0
                        )

            yield Case(
                f"dwelling-visibility.power-{power}.protected-{protected}", visibility
            )
