"""Weekly transitions, reinforcement capacity and packed mutant lifetimes."""

import ctypes as C
from cases import Case, ready
from runtime import Creature


def cases(module):
    if module != "KBCAL":
        return
    for current_island, castle_island in ((2, 1), (1, 5), (2, 2)):
        for garrison in (False, True):

            def castle_map(v, current_island=current_island,
                           castle_island=castle_island, garrison=garrison):
                g = v.fixture()
                g.Campaign.Island = current_island
                c = g.Campaign.Castles[castle_island - 1][0]
                c.Owned = True
                if garrison:
                    c.Species[0] = 0
                    c.Counts[0] = 1
                g.Campaign.Map[castle_island - 1][c.X][c.Y] = 18
                if current_island != castle_island:
                    g.Campaign.Map[current_island - 1][c.X][c.Y] = 48
                v.set_game(g)
                if not garrison:
                    g.Campaign.Map[castle_island - 1][c.X][c.Y] = 2
                ready(v, v.invoke("EndWeek"))
                after = v.game().Campaign
                assert after.Island == current_island
                assert after.Castles[castle_island - 1][0].Owned == garrison
                assert bytes(after.Map) == bytes(g.Campaign.Map)

            yield Case(f"castle-map.hero-{current_island}.castle-{castle_island}.garrison-{garrison}",
                       castle_map)
    for gold, count in ((250, 100), (0, 0)):

        def payroll_equality(v, gold=gold, count=count):
            g = v.fixture()
            g.Campaign.Gold = gold
            g.Campaign.Income = 0
            if count:
                g.Campaign.Army[0].Species = 0
                g.Campaign.Army[0].Count = count
                definition = Creature.from_buffer_copy(
                    v.read(v.addresses[1][0], C.sizeof(Creature))
                )
                assert definition.Cost.Price * count // 20 == gold
            v.set_game(g)
            before = [(a.Species, a.Count) for a in g.Campaign.Army]
            ready(v, v.invoke("EndWeek"))
            after = v.game().Campaign
            assert after.Weeks == 99 and after.Days == 200
            assert after.Gold == 0
            assert [(a.Species, a.Count) for a in after.Army] == before
            assert any(n == "DrawText" and a[3] == "ФИНАНСОВЫЙ ОТЧЕТ ПРОШЕДШЕЙ НЕДЕЛИ"
                       for _, n, a in v.calls)

        yield Case(f"payroll-equality.gold-{gold}.count-{count}", payroll_equality)
    for lifetime in (0, 1, 2, 255):

        def mutant(v, lifetime=lifetime):
            g = v.fixture()
            g.Campaign.Army[0].Species = 25
            g.Campaign.Army[0].Count = 3
            v.set_game(g)
            definition = Creature.from_buffer_copy(
                v.read(v.addresses[1][0], C.sizeof(Creature))
            )
            definition.Cost.Price = 0x1C00 | lifetime
            address = v.addresses[1][0] + 25 * C.sizeof(Creature)
            v.cpu.mem_write(address, bytes(definition))
            ready(v, v.invoke("EndWeek"))
            after = Creature.from_buffer_copy(v.read(address, C.sizeof(Creature)))
            if lifetime == 1:
                assert (
                    v.game().Campaign.Army[0].Species == 100
                    and after.Cost.Price == definition.Cost.Price
                )
            else:
                assert v.game().Campaign.Army[0].Species == 25
                assert after.Cost.Price == (
                    65535 if lifetime == 0 else 0x1C00 | lifetime - 1
                )

        yield Case(f"mutant-lifetime.{lifetime}", mutant)

    for label, authority, free, species, counts in (
        ("existing-empty-result", 0, False, (5, 100, 4, 100, 6), (10, 0, 10, 0, 10)),
        ("existing-partial-result", 20, False, (5, 100, 1, 0, 100), (1, 0, 2, 10, 0)),
        ("new-empty-result", 0, True, (100,) * 5, (10, 0, 10, 0, 10)),
        ("new-positive-result", 20, True, (1, 0, 100, 100, 100), (2, 10, 0, 0, 0)),
    ):

        def weekly_enemy(v, authority=authority, free=free, species=species, counts=counts):
            g = v.fixture()
            campaign = g.Campaign
            campaign.UnlockedIslands = 1
            campaign.Leadership = authority
            for army in campaign.WanderingArmies[0]:
                army.X, army.Y = 20, 20
                army.Species[:] = [100] * 5
            army = campaign.WanderingArmies[0][0]
            army.Counts[:] = (10, 0, 10, 0, 10)
            if free:
                army.X, army.Y = 255, 17
            else:
                army.Species[:] = (5, 100, 4, 100, 6)
                campaign.Map[0][20][20] = 5
            v.set_game(g)

            # Keep native placement and its random draws in the same weekly transition.
            placement = {
                address: entry for address, entry in v.functions.items()
                if entry[0] == "KBWORLD" and entry[1]["name"] == "RelocateArmy"
            }
            assert len(placement) == 1
            for address in placement:
                del v.functions[address]
            try:
                ready(v, v.invoke("EndWeek"))
            finally:
                v.functions.update(placement)

            after = v.game().Campaign
            actual = after.WanderingArmies[0][0]
            position = (22, 28) if free and authority else (army.X, army.Y)
            assert (actual.X, actual.Y) == position, (actual.X, actual.Y)
            assert tuple(actual.Species) == species, tuple(actual.Species)
            assert tuple(actual.Counts) == counts, tuple(actual.Counts)
            if free and authority:
                campaign.Map[0][22][28] = 5
            assert bytes(after.Map) == bytes(campaign.Map)

        yield Case(f"weekly-enemy.{label}", weekly_enemy)

    from matrix import sample

    yield sample(
        module,
        "EndWeek",
        "unlocked-island-clamp",
        changes={"Campaign.UnlockedIslands": 255},
        scans=[1, 1],
    )
    castles = {
        f"Campaign.Castles.{island}.{slot}.{field}": value
        for island in range(5)
        for slot in range(5)
        for field, value in (("Owned", True), ("Species.0", 0), ("Counts.0", 1))
    }
    yield sample(
        module, "EndWeek", "owned-castles-with-garrisons", changes=castles, scans=[1, 1]
    )
    yield sample(
        module,
        "EndWeek",
        "empty-castle-no-leadership",
        changes={"Campaign.Castles.0.0.Owned": True, "Campaign.Leadership": 0},
        scans=[1, 1],
    )
    stones = {
        f"Campaign.Map.{island}.{x}.10": 0
        for island in range(5)
        for x in (10, 20, 30, 40, 50)
    }
    yield sample(
        module, "EndWeek", "missing-talking-stones", changes=stones, scans=[1, 1]
    )
    weekly = (((12345 * 134775813 + 1) & 0xFFFFFFFF) * 24) >> 32
    yield sample(
        module,
        "EndWeek",
        "weekly-dwelling-restock",
        scans=[1, 1],
        changes={
            f"Campaign.Dwellings.{island}.{slot}.Species": weekly
            for island in range(5)
            for slot in range(8)
        },
    )
    for strength in (0, 1, 65535):
        troops = {
            f"Campaign.WanderingArmies.{island}.{i}.{field}": value
            for island in range(5)
            for i in range(21)
            for field, value in (
                ("X", 20),
                ("Y", 20),
                ("Species.1", 100 if strength == 0 else 0),
                ("Counts.1", strength),
            )
        }
        yield sample(
            module,
            "EndWeek",
            f"no-free-roamer-slots.strength-{strength}",
            changes=troops,
            scans=[1, 1],
        )
