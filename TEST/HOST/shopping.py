"""Transaction protocols with explicit successful and cancelled economy doubles."""

import struct
from cases import Case, ready
from characterise import preset, tree, projection
from runtime import linear


def buying(v, args, byte_stock=False):
    capacity, price, destination, stock = args
    seen = sum(
        name == ("BuyByteQuantity" if byte_stock else "BuyQuantity")
        for _, name, _ in v.calls
    )
    g = v.game()
    g.Runtime.LastScan = 13 if seen == 1 and capacity > 0 else 27
    if g.Runtime.LastScan == 13:
        g.Campaign.Gold -= price
    v.set_game(g)
    if g.Runtime.LastScan == 13:
        count = v.word(linear(destination))
        v.cpu.mem_write(linear(destination), struct.pack("<H", count + 1))
        size = 1 if byte_stock else 2
        available = int.from_bytes(v.read(linear(stock), size), "little")
        v.cpu.mem_write(linear(stock), (available - 1).to_bytes(size, "little"))
    return 0


def cases(module):
    if module == "KBDWELL":
        for army in ("empty", "reserve-free", "full", "over-limit"):
            for grace in (0, 1):

                def recruit(v, army=army, grace=grace):
                    g = preset(v)
                    g.Campaign.EnemyGrace = grace
                    if army in ("reserve-free", "full"):
                        for i in range(5 if army == "reserve-free" else 10):
                            g.Campaign.Army[i].Species = i + 1
                            g.Campaign.Army[i].Count = 1
                    if army == "over-limit":
                        g.Campaign.Army[0].Species = 0
                        g.Campaign.Army[0].Count = 10000
                    v.set_game(g)
                    v.responses["BuyQuantity"] = buying
                    before = tree(v.game())
                    disk = v.disk.copy()
                    tables = v.read(v.addresses[1][0], 540)
                    result = v.invoke("DwellingVisit")
                    ready(v, result)
                    after = v.game().Campaign
                    if army in ("empty", "reserve-free"):
                        slot = 5 if army == "reserve-free" else 0
                        assert (
                            after.Army[slot].Species == 0
                            and after.Army[slot].Count == 1
                        )
                        assert (
                            after.Dwellings[0][0].Count == 39 and after.EnemyGrace == 0
                        )
                    elif army == "over-limit":
                        assert after.Army[0].Count == 10000
                    else:
                        assert all(a.Species == i + 1 for i, a in enumerate(after.Army))
                    return projection(v, before, [], result, disk, tables)

                yield Case(f"recruit.{army}.grace-{grace}", recruit)
    elif module == "KBTOWN":
        for cancel, cap in ((False, 0), (True, 0), (False, 1000)):

            def market(v, cancel=cancel, cap=cap):
                g = preset(v, True)
                g.Runtime.GoodsMarketTown = 1
                g.Runtime.GoodsMarketIsland = 1
                g.Runtime.GoodsMarketAge = 0
                g.Runtime.GoodsStock[0] = 10
                g.Runtime.GoodsBuyPrices[0] = 100
                g.Campaign.CargoMaxPrices[0] = cap
                v.set_game(g)
                if not cancel:
                    v.responses["BuyByteQuantity"] = lambda vm, args: buying(
                        vm, args, True
                    )
                before = tree(v.game())
                disk = v.disk.copy()
                tables = v.read(v.addresses[1][0], 540)
                result = v.invoke("TownVisit", keys=[55, 49, 27, 27])
                ready(v, result)
                after = v.game().Campaign
                assert after.Cargo[0] == int(not cancel)
                if not cancel:
                    assert (
                        after.CargoMaxPrices[0] == max(100, cap)
                        and after.Gold == g.Campaign.Gold - 100
                    )
                return projection(v, before, [], result, disk, tables)

            yield Case(f"goods.buy.cancel-{cancel}.prior-price-{cap}", market)
        from matrix import sample

        yield sample(
            module,
            "TownVisit",
            "cancel-sale",
            keys=[55, 9, 49, 27, 27],
            responses={"ReadQuantity": 0},
            changes={"Campaign.Cargo.0": 5},
        )
        yield sample(
            module, "TownVisit", "toggle-market-twice", keys=[55, 9, 9, 27, 27]
        )
        yield sample(
            module, "TownVisit", "market-small-spread", keys=[55, 27, 27], seed=0
        )
        for failed in (0, 1):
            for key in (50, 52, 53):
                yield sample(
                    module,
                    "TownVisit",
                    f"purchase-{key}.payment-failed-{failed}",
                    keys=[key, 27],
                    responses={"PaymentFailed": failed},
                )
        for tile in (4, 48):
            yield sample(
                module,
                "TownVisit",
                f"ship-placement-tile-{tile}",
                keys=[50, 27],
                changes={f"Campaign.Map.0.7.7": tile},
            )
        yield sample(
            module,
            "TownVisit",
            "offer-all-complete",
            keys=[49, 27],
            changes={f"Campaign.Contracts.0.{i}.Island": 100 for i in range(5)},
        )
        yield sample(
            module,
            "TownVisit",
            "accept-contract-after-wrap",
            keys=[49, 27],
            scans=[21, 28],
            changes={"Runtime.CurrentContractOffer": 5},
        )
        yield sample(
            module,
            "TownVisit",
            "town-cached-and-visited",
            keys=[51, 27],
            scans=[1],
            responses={"ArmyReport": 1},
            changes={
                "Runtime.TownPictureLoaded": True,
                "Campaign.VisitedTowns.0.Island": 1,
                "Campaign.VisitedTowns.0.Slot": 1,
            },
        )
