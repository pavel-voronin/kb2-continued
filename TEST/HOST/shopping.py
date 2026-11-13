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
    if module in ("KBCASTLE", "KBWIZARD"):
        wizard = module == "KBWIZARD"
        seed = next(s for s in range(20000)
                    if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) == 1)
        for island in (1, 5):
            for mode in ("first-and-repeat", "owned", "insufficient", "other-island"):

                def map_purchase(v, island=island, mode=mode, wizard=wizard, seed=seed):
                    g = preset(v)
                    slot = island - 1
                    price = 500000 if wizard else island * 3000
                    g.Campaign.Island = island
                    g.Campaign.Gold = price - 1 if mode == "insufficient" else price * 3
                    g.Campaign.MapParts = 1 if mode in ("owned", "other-island") else 0
                    g.Campaign.WizardRelations[slot] = 10
                    g.Campaign.QuestFlags[slot] = 1
                    g.Campaign.Castles[slot][0].Owned = False
                    g.World.GenerationX = g.Campaign.Castles[slot][0].X
                    g.World.GenerationY = g.Campaign.Castles[slot][0].Y
                    g.Campaign.Hero.Y = g.World.GenerationY + 1
                    for i in range(5):
                        g.Campaign.Flags.LocalMapOwned[i] = False
                        g.Campaign.WizardVisited[i] = 1
                    owned_slot = slot if mode == "owned" else (slot + 1) % 5
                    if mode in ("owned", "other-island"):
                        g.Campaign.Flags.LocalMapOwned[owned_slot] = True
                        g.Campaign.WizardVisited[owned_slot] |= 2
                    v.set_game(g)
                    charged = []

                    def pay(vm, args):
                        cost, = args
                        charged.append(cost)
                        state = vm.game()
                        if state.Campaign.Gold < cost:
                            return 1
                        state.Campaign.Gold -= cost
                        vm.set_game(state)
                        return 0

                    v.responses["PaymentFailed"] = pay

                    def visit():
                        v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))
                        ready(v, v.invoke("WizardVisit" if wizard else "CastleVisit",
                                          keys=[54] if wizard else [49, 49, 27]))

                    visit()
                    visit()  # Re-enter with the state left by the first visit.
                    bought = mode not in ("owned", "insufficient")
                    expected_owned = mode != "insufficient"
                    after = v.game().Campaign
                    assert after.Gold == g.Campaign.Gold - (price if bought else 0)
                    if wizard:
                        assert bool(after.WizardVisited[slot] & 2) == expected_owned
                        assert after.WizardVisited[slot] & 1
                        assert after.MapParts == g.Campaign.MapParts + int(bought)
                        if expected_owned:
                            assert any(n == "DrawText" and a[3] ==
                                       "*) Часть древней карты уже получена"
                                       for _, n, a in v.calls)
                    else:
                        assert bool(after.Flags.LocalMapOwned[slot]) == expected_owned
                    attempts = (2 if wizard else 4) if mode == "insufficient" else int(bought)
                    assert charged == [price] * attempts
                    if mode == "other-island":
                        assert after.Flags.LocalMapOwned[owned_slot]
                        assert after.WizardVisited[owned_slot] & 2

                yield Case(f"map-purchase.island-{island}.{mode}", map_purchase)
        if not wizard:

            def castle_map_reward(v):
                g = preset(v)
                g.Campaign.QuestFlags[0] = 0
                g.Campaign.WizardVisited[0] = 1
                g.Campaign.MapParts = 0
                v.set_game(g)
                ready(v, v.invoke("CastleVisit", keys=[50, 51, 27]))
                assert v.game().Campaign.WizardVisited[0] == 3
                assert v.game().Campaign.MapParts == 1

            yield Case("map-part.castle-reward-sets-ownership", castle_map_reward)
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
        for label, owned, gold, presses, expected_gold, expected_owned, payments in (
            ("first-and-repeat", False, 9000, 2, 6000, True, 1),
            ("already-owned", True, 9000, 1, 9000, True, 0),
            ("insufficient-gold", False, 2999, 1, 2999, False, 1),
        ):

            def siege(v, owned=owned, gold=gold, presses=presses,
                      expected_gold=expected_gold, expected_owned=expected_owned,
                      payments=payments):
                g = preset(v)
                g.Campaign.Flags.SiegeEngineOwned = owned
                g.Campaign.Gold = gold
                v.set_game(g)
                charged = []

                def pay(vm, args):
                    cost, = args
                    charged.append(cost)
                    state = vm.game()
                    if state.Campaign.Gold < cost:
                        return 1
                    state.Campaign.Gold -= cost
                    vm.set_game(state)
                    return 0

                v.responses["PaymentFailed"] = pay
                ready(v, v.invoke("TownVisit", keys=[53] * presses + [27]))
                after = v.game().Campaign
                assert after.Gold == expected_gold
                assert bool(after.Flags.SiegeEngineOwned) == expected_owned
                assert charged == [3000] * payments

                def menu_rows(calls):
                    rows = []
                    cleared = False
                    for _, name, args in calls:
                        if name == "DrawDialog" and list(args) == [8, 230, 488, 320]:
                            cleared = True
                        if name == "DrawText" and list(args[:3]) == [0, 2, 288]:
                            assert cleared, "Menu must be cleared before drawing the row"
                            rows.append(args[3])
                            cleared = False
                    return rows

                available = "5) Купить стенобитное оpудие ($3000)"
                purchased = "*) Стенобитное орудие куплено"
                assert menu_rows(v.calls) == [purchased if owned else available] + [
                    purchased if expected_owned else available
                ] * presses
                previous_calls = len(v.calls)
                ready(v, v.invoke("TownVisit", keys=[27]))
                assert menu_rows(v.calls[previous_calls:]) == [
                    purchased if expected_owned else available
                ]

            yield Case(f"siege.{label}", siege)
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
