"""Local world effects with independent coordinate and visibility checks."""

import struct
from cases import Case, ready
from runtime import linear


def cases(module):
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
