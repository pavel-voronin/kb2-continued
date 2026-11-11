"""Weekly transitions, reinforcement capacity and packed mutant lifetimes."""

import ctypes as C
from cases import Case, ready
from runtime import Creature


def cases(module):
    if module != "KBCAL":
        return
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
