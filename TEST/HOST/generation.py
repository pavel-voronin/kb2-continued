"""Generator boundary fixtures without rerunning completed campaign tests."""

import struct
from cases import Case, ready
from runtime import INDEX


def cases(module):
    if module != "KBGEN":
        return
    from matrix import sample

    yield sample(module, "PrepareCampaign", "unsupported-level-byte", values=[4])
    yield sample(
        module,
        "PlaceInitialHero",
        "town-with-no-free-neighbour",
        values=[0],
        changes={
            f"Campaign.Map.0.{x}.{y}": 7 for x in range(7, 10) for y in range(7, 10)
        },
    )
    names = {
        f"Campaign.Castles.{island}.{slot}.Name": 255
        for island in range(5)
        for slot in range(5)
    }
    names.update({f"World.CastleNamePool.{i}": 255 for i in range(25)})
    yield sample(module, "GenerateContracts", "missing-castle-names", changes=names)

    def paper_collision(v):
        v.fixture()
        ready(v, v.invoke("PrepareCampaign", 0))
        seen = []
        enter = next(
            p["id"]
            for p in INDEX["points"]
            if p["file"] == "KBGEN.PAS"
            and p["routine"] == "GenerateWorld.GeneratePaperScrolls"
            and p["kind"] == "routine"
        )
        leave = next(
            p["id"]
            for p in INDEX["points"]
            if p["file"] == "KBGEN.PAS"
            and p["routine"] == "GenerateWorld.PaintOuterFrame"
            and p["kind"] == "routine"
        )
        retry = next(
            p["id"]
            for p in INDEX["points"]
            if p["file"] == "KBGEN.PAS"
            and p["line"] == 755
            and p["kind"] == "branch-false"
        )

        def fixture_at_entry(vm):
            g = vm.game()
            seed = struct.unpack("<I", vm.read(vm.addresses[2][0], 4))[0]
            s1 = (seed * 134775813 + 1) & 0xFFFFFFFF
            s2 = (s1 * 134775813 + 1) & 0xFFFFFFFF
            x = (s1 * g.World.GenerationCount >> 32) + 5
            y = (s2 * g.World.GenerationLimit >> 32) + 5
            assert 0 <= x < 66 and 0 <= y < 66
            g.Campaign.Map[g.World.GenerationIsland - 1][x][y] = 7
            vm.set_game(g)
            seen.append((g.World.GenerationIsland - 1, x, y))

        def stop_at_exit(vm):
            if seen:
                vm.stop("isolated-procedure-return")

        v.entry_probes[enter] = fixture_at_entry
        v.entry_probes[leave] = stop_at_exit
        result = v.invoke("GenerateWorld", 0, instructions=120_000_000, seconds=30)
        assert result[1] == {"kind": "isolated-procedure-return"}, result
        assert len(seen) == 1 and v.hits[retry] > 0
        island, x, y = seen[0]
        world = v.game().Campaign.Map[island]
        assert world[x][y] == 7
        assert sum(world[a][b] == 9 for a in range(66) for b in range(66)) == 2

    yield Case("paper-scroll.rejects-occupied-candidate", paper_collision)
