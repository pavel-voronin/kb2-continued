"""Coordinate and marker oracles for the original viewport assembly."""

from cases import Case, ready


def cases(module):
    if module != "KBMOTION":
        return
    for destination in (9, 10):

        def collectible(v, destination=destination):
            g = v.fixture()
            g.Campaign.Map[0][28][28] = 5
            g.Campaign.Map[0][29][29] = destination
            g.Campaign.WanderingArmies[0][0].X = 28
            g.Campaign.WanderingArmies[0][0].Y = 28
            v.set_game(g)
            ready(v, v.invoke("AdvanceNearbyRoamers"))
            after = v.game().Campaign
            assert after.Map[0][29][29] == 5 and after.Map[0][28][28] == 0
            assert (after.WanderingArmies[0][0].X, after.WanderingArmies[0][0].Y) == (
                29,
                29,
            )

        yield Case(f"movement.overwrites-collectible-{destination}", collectible)
    for grace, late_row in ((0, False), (1, True)):

        def scan(v, grace=grace, late_row=late_row):
            g = v.fixture()
            y = 32 if late_row else 28
            g.Campaign.Map[0][28][y] = 5
            g.Campaign.EnemyGrace = grace
            g.Campaign.WanderingArmies[0][1].X = 28
            g.Campaign.WanderingArmies[0][1].Y = y
            v.set_game(g)
            ready(v, v.invoke("AdvanceNearbyRoamers"))
            after = v.game().Campaign
            assert after.WanderingArmies[0][1].X == (28 if grace else 29)
            assert after.WanderingArmies[0][1].Y == (y if grace else 29)

        yield Case(f"scan.skip-wrong-x.grace-{grace}.late-row-{late_row}", scan)
    for island in (1, 5):

        def reveal(v, island=island):
            g = v.fixture()
            g.Campaign.Island = island
            v.set_game(g)
            ready(v, v.invoke("RevealNearbyTiles"))
            flags = v.game().Campaign.Flags.Discovery
            for i in range(5):
                for x in range(27, 34):
                    for y in range(27, 34):
                        assert flags[i][x][y] == int(
                            i == island - 1 and 28 <= x <= 32 and 28 <= y <= 32
                        )

        yield Case(f"reveal.island-{island}", reveal)
    for tile in (5, 28):
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx == dy == 0:
                    continue
                for blocked in (False, True):
                    if blocked and max(abs(dx), abs(dy)) < 2:
                        continue

                    def move(v, tile=tile, dx=dx, dy=dy, blocked=blocked):
                        g = v.fixture()
                        x, y = 30 + dx, 30 + dy
                        tx = x - (dx > 0) + (dx < 0)
                        ty = y - (dy > 0) + (dy < 0)
                        g.Runtime.WorldMapRedraw = 30
                        g.Campaign.Map[0][x][y] = tile
                        if tile == 5:
                            g.Campaign.WanderingArmies[0][0].X = x
                            g.Campaign.WanderingArmies[0][0].Y = 255
                            g.Campaign.WanderingArmies[0][1].X = x
                            g.Campaign.WanderingArmies[0][1].Y = y
                        else:
                            g.World.MagePosition.X = x
                            g.World.MagePosition.Y = y
                        if blocked:
                            g.Campaign.Map[0][tx][ty] = 7
                        v.set_game(g)
                        ready(v, v.invoke("AdvanceNearbyRoamers"))
                        after = v.game()
                        c = after.Campaign
                        position = (
                            c.WanderingArmies[0][1]
                            if tile == 5
                            else after.World.MagePosition
                        )
                        assert (position.X, position.Y) == (
                            (x, y) if blocked else (tx, ty)
                        )
                        assert c.Map[0][position.X][position.Y] == tile
                        assert after.Runtime.WorldMapRedraw == 29
                        assert all(
                            c.Map[0][a][b] not in (254, 255)
                            for a in range(28, 33)
                            for b in range(28, 33)
                        )

                    yield Case(
                        f"move.tile-{tile}.dx-{dx}.dy-{dy}.blocked-{blocked}", move
                    )

    def grace(v):
        g = v.fixture()
        g.Campaign.EnemyGrace = 1
        g.Campaign.Map[0][28][28] = 5
        g.Campaign.WanderingArmies[0][0].X = 28
        g.Campaign.WanderingArmies[0][0].Y = 28
        v.set_game(g)
        ready(v, v.invoke("AdvanceNearbyRoamers"))
        after = v.game().Campaign
        assert after.EnemyGrace == 0 and after.Map[0][28][28] == 5
        assert (after.WanderingArmies[0][0].X, after.WanderingArmies[0][0].Y) == (
            28,
            28,
        )

    yield Case("enemy-grace.postpones-one-army", grace)
