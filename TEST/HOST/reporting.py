"""Reports and recruitment: boundary quantities and independent join fixtures."""

import struct
from cases import Case, ready
from characterise import preset, tree, projection


def cases(module):
    if module != "KBREPORT":
        return
    for count in (0, 29, 30, 99, 100, 249, 250, 499, 500, 65535):

        def numbers(v, count=count):
            preset(v)
            species = v.alloc(bytes((0, 1, 100, 100, 100)))
            counts = v.alloc(struct.pack("<5H", count, count, 0, 0, 0))
            before = tree(v.game())
            disk = v.disk.copy()
            tables = v.read(v.addresses[1][0], 540)
            result = v.invoke("ArmyReport", species, counts, v.string_arg("UNIT"))
            assert ready(v, result) == 0
            return projection(v, before, [], result, disk, tables)

        yield Case(f"counts.category-{count}", numbers)
    for arrangement in (
        "empty",
        "matching",
        "reserve-free",
        "full",
        "normal-leadership",
    ):
        for accept in (False, True):

            def join(v, arrangement=arrangement, accept=accept):
                g = preset(v)
                g.Campaign.Leadership = (
                    1000 if arrangement == "normal-leadership" else 0
                )
                if arrangement == "matching":
                    g.Campaign.Army[0].Species = 0
                    g.Campaign.Army[0].Count = 7
                if arrangement in ("reserve-free", "full"):
                    for i in range(5 if arrangement == "reserve-free" else 10):
                        g.Campaign.Army[i].Species = i + 1
                        g.Campaign.Army[i].Count = 7
                v.set_game(g)
                v.cpu.mem_write(v.addresses[2][0], bytes(4))
                v.scans.append(21 if accept else 49)
                species = v.alloc(bytes([100]) * 5)
                counts = v.alloc(bytes(10))
                ready(v, v.invoke("ArmyReport", species, counts, v.string_arg(" ")))
                after = v.game().Campaign
                if accept and arrangement != "full":
                    slot = 5 if arrangement == "reserve-free" else 0
                    assert after.Army[slot].Species == 0 and after.Army[slot].Count == (
                        17
                        if arrangement == "matching"
                        else 500
                        if arrangement == "normal-leadership"
                        else 10
                    )
                elif arrangement == "full":
                    assert all(a.Species == i + 1 for i, a in enumerate(after.Army))
                else:
                    assert all(
                        a.Species == b.Species and a.Count == b.Count
                        for a, b in zip(after.Army, g.Campaign.Army)
                    )

            yield Case(f"join.{arrangement}.accept-{accept}", join)
    from matrix import sample

    for island in range(6):
        yield sample(
            module, "DrawIslandName", f"island-{island}", values=[island, 2, 240]
        )
