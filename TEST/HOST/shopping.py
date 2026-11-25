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
    if module == "KBWIZARD":
        for key, field, price in ((49, "Carpenters", 500), (50, "Woodcutters", 1000),
                                  (51, "Diggers", 500), (52, "Stonecutters", 2000)):
            for count, power, enough in ((0, 0, True), (65534, 0, True),
                                        (65534, 1, True), (65534, 255, True),
                                        (65280, 255, True), (65535, 255, True),
                                        (65535, 0, False), (65534, 255, False)):

                def hire_limit(v, key=key, field=field, price=price,
                               count=count, power=power, enough=enough):
                    g = preset(v)
                    g.Campaign.MagicPower = power
                    g.Campaign.Gold = 10000 if enough else price - 1
                    setattr(g.Campaign, field, count)
                    v.set_game(g)
                    before = {name: getattr(g.Campaign, name) for name in
                              ("Carpenters", "Woodcutters", "Diggers", "Stonecutters")}
                    payments = []

                    def pay(vm, args):
                        assert list(args) == [price]
                        payments.append(price)
                        state = vm.game()
                        if state.Campaign.Gold < price:
                            return 1
                        state.Campaign.Gold -= price
                        vm.set_game(state)
                        return 0

                    v.responses["PaymentFailed"] = pay
                    ready(v, v.invoke("WizardVisit", keys=[49, key]))
                    paid = count < 65535 and enough
                    expected = dict(before)
                    expected[field] = min(65535, count + max(1, power)) if paid else count
                    assert {name: getattr(v.game().Campaign, name) for name in before} == expected
                    assert v.game().Campaign.Gold == g.Campaign.Gold - (price if paid else 0)
                    assert payments == ([price] if count < 65535 else [])

                yield Case(f"worker-hire.{field}.count-{count}.power-{power}.enough-{enough}", hire_limit)
    if module == "KBTOWN":
        for scan, field, stock_index, price in ((2, "Carpenters", 0, 500),
                                               (3, "Woodcutters", 1, 500),
                                               (4, "Diggers", 3, 800),
                                               (5, "Stonecutters", 2, 800)):
            for count, expected_capacity in ((65535, None), (65534, 1), (65530, 3)):

                def town_limit(v, scan=scan, field=field, stock_index=stock_index,
                               price=price, count=count, expected_capacity=expected_capacity):
                    g = preset(v)
                    g.Campaign.Gold = 10000
                    setattr(g.Campaign, field, count)
                    g.Campaign.Towns[0][0].Workers[stock_index] = 3
                    v.set_game(g)
                    purchases = []

                    def buy(vm, args):
                        capacity, cost, destination, stock = args
                        assert (capacity, cost) == (expected_capacity, price)
                        assert vm.word(linear(destination)) == count
                        assert vm.read(linear(stock), 1) == b"\x03"
                        purchases.append(capacity)
                        # Existing quantity buyer accepts one worker within the supplied capacity.
                        vm.cpu.mem_write(linear(destination), struct.pack("<H", count + 1))
                        vm.cpu.mem_write(linear(stock), b"\x02")
                        state = vm.game()
                        state.Campaign.Gold -= price
                        vm.set_game(state)
                        return 0

                    v.responses["BuyByteQuantity"] = buy
                    v.scans.extend([scan, 1])
                    ready(v, v.invoke("TownVisit", keys=[54, 27]))
                    paid = expected_capacity is not None
                    assert purchases == ([expected_capacity] if paid else [])
                    assert getattr(v.game().Campaign, field) == count + int(paid)
                    assert v.game().Campaign.Towns[0][0].Workers[stock_index] == 3 - int(paid)
                    assert v.game().Campaign.Gold == 10000 - (price if paid else 0)

                yield Case(f"town-worker-limit.{field}.count-{count}", town_limit)
    if module == "KBECON":
        for wanted in (1, 2):

            def quantity_limit(v, wanted=wanted):
                g = v.fixture()
                g.Campaign.Gold = 10000
                v.set_game(g)
                destination = v.alloc(struct.pack("<H", 65534))
                stock = v.alloc(b"\x03")
                ready(v, v.invoke("BuyByteQuantity", 1, 500, destination, stock,
                                  keys=[48 + wanted, 13]))
                assert v.word(linear(destination)) == (65535 if wanted == 1 else 65534)
                assert v.read(linear(stock), 1) == (b"\x02" if wanted == 1 else b"\x03")
                assert v.game().Campaign.Gold == (9500 if wanted == 1 else 10000)

            yield Case(f"worker-capacity.quantity-{wanted}", quantity_limit)
    if module == "KBWIZARD":
        for bonus, gold in ((0, 100000), (63535, 100000), (64535, 100000),
                            (64536, 100000), (65000, 100000), (65534, 100000),
                            (65535, 200000), (65535, 0), (65000, 99999)):

            def damage_purchase(v, bonus=bonus, gold=gold):
                g = preset(v)
                g.Campaign.DamageBonus = bonus
                g.Campaign.Gold = gold
                g.Campaign.WizardRelations[0] = 5
                v.set_game(g)
                payments = []

                def pay(vm, args):
                    assert list(args) == [100000]
                    payments.append(100000)
                    state = vm.game()
                    if state.Campaign.Gold < 100000:
                        return 1
                    state.Campaign.Gold -= 100000
                    vm.set_game(state)
                    return 0

                v.responses["PaymentFailed"] = pay
                seed = next(s for s in range(20000)
                            if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) == 5)
                v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))
                ready(v, v.invoke("WizardVisit", keys=[54]))
                paid = bonus < 65535 and gold >= 100000
                assert v.game().Campaign.Gold == gold - (100000 if paid else 0)
                assert v.game().Campaign.DamageBonus == (min(65535, bonus + 1000) if paid else bonus)
                assert payments == ([100000] if bonus < 65535 else [])
                assert any(n == "DrawText" and a[3] ==
                           "*) Усиление воинов достигло максимума"
                           for _, n, a in v.calls) == (bonus == 65535)
                assert any(n == "DrawText" and a[3] == "6) Усилить воинов($100000)"
                           for _, n, a in v.calls) == (bonus < 65535)

            yield Case(f"damage-purchase.bonus-{bonus}.gold-{gold}", damage_purchase)
    if module == "KBWIZARD":
        for charges, gold, affinity in ((0, 10000, 4), (1, 10000, 4),
                                        (254, 10000, 4), (254, 9999, 4),
                                        (255, 20000, 4), (255, 0, 4),
                                        (254, 20000, 3), (255, 20000, 3)):

            def tornado_purchase(v, charges=charges, gold=gold, affinity=affinity):
                g = preset(v)
                g.Campaign.TornadoCharges = charges
                g.Campaign.Gold = gold
                g.Campaign.WizardRelations[0] = affinity
                v.set_game(g)
                payments = []

                def pay(vm, args):
                    assert list(args) == [10000]
                    payments.append(10000)
                    state = vm.game()
                    if state.Campaign.Gold < 10000:
                        return 1
                    state.Campaign.Gold -= 10000
                    vm.set_game(state)
                    return 0

                v.responses["PaymentFailed"] = pay
                ready(v, v.invoke("WizardVisit", keys=[53]))
                allowed = charges < 255 and affinity > 3
                paid = allowed and gold >= 10000
                after = v.game().Campaign
                assert after.Gold == gold - (10000 if paid else 0)
                assert after.TornadoCharges == charges + int(paid)
                assert payments == ([10000] if allowed else [])
                assert any(n == "DrawText" and a[3] ==
                           "*) Запас смерчей достиг максимума"
                           for _, n, a in v.calls) == (charges == 255 and affinity > 3)
                assert any(n == "DrawText" and a[3] == "5) Дать СМЕРЧ.($10000)"
                           for _, n, a in v.calls) == allowed

            yield Case(f"tornado-purchase.charges-{charges}.gold-{gold}.affinity-{affinity}", tornado_purchase)
    if module == "KBWIZARD":
        for power, gold in ((0, 5000), (1, 5000), (254, 5000),
                            (254, 4999), (255, 5000), (255, 0)):

            def power_purchase(v, power=power, gold=gold):
                g = preset(v)
                g.Campaign.MagicPower = power
                g.Campaign.Gold = gold
                g.Campaign.WizardRelations[0] = 1
                v.set_game(g)
                charges = []

                def pay(vm, args):
                    assert list(args) == [5000]
                    charges.append(5000)
                    state = vm.game()
                    if state.Campaign.Gold < 5000:
                        return 1
                    state.Campaign.Gold -= 5000
                    vm.set_game(state)
                    return 0

                v.responses["PaymentFailed"] = pay
                ready(v, v.invoke("WizardVisit", keys=[50]))
                paid = power < 255 and gold >= 5000
                after = v.game().Campaign
                assert after.Gold == gold - (5000 if paid else 0)
                assert after.MagicPower == power + int(paid)
                assert charges == ([5000] if power < 255 else [])
                assert any(n == "DrawText" and a[3] ==
                           "*) Волшебная сила достигла максимума"
                           for _, n, a in v.calls) == (power == 255)
                assert any(n == "RefreshMagic" for _, n, _ in v.calls) == paid

            yield Case(f"power-purchase.power-{power}.gold-{gold}", power_purchase)
    if module == "KBCASTLE":
        for amount, key in ((5, 51), (8, 52)):
            for power in (0, 1, 246, 247, 248, 249, 250, 251, 254, 255):

                def power_reward(v, amount=amount, key=key, power=power):
                    g = preset(v)
                    g.Campaign.MagicPower = power
                    g.Campaign.QuestFlags[0] = 0
                    g.Campaign.WizardVisited[0] = 1
                    g.Campaign.MapParts = 0
                    v.set_game(g)
                    ready(v, v.invoke("CastleVisit", keys=[50, key, 27]))
                    after = v.game().Campaign
                    assert after.MagicPower == min(255, power + amount)
                    assert after.Gold == g.Campaign.Gold
                    assert after.ScrollCapacity == g.Campaign.ScrollCapacity + (10 if amount == 5 else 15)
                    assert after.Leadership == g.Campaign.Leadership + (0 if amount == 5 else 1000)
                    assert after.MapParts == int(amount == 5)
                    assert after.QuestFlags[0] == 100
                    assert after.Income == g.Campaign.Income + 2000

                yield Case(f"power-reward.amount-{amount}.power-{power}", power_reward)
    if module == "KBWIZARD":
        for island in (1, 5):
            for missing, gold in [(None, 300000), (None, 0), ("above", 300000)] + [
                    (slot, 200000) for slot in range(8)] + [
                    (7, 199999), ("mixed", 300000), ("mixed", 199999)]:

                def dwelling_restock(v, island=island, missing=missing, gold=gold):
                    g = preset(v, True)
                    g.Campaign.Island = island
                    g.Campaign.Gold = gold
                    species = [0, 1, 5, 10, 15, 19, 22, 24]
                    capacities = [1000, 400, 200, 100, 30, 70, 30, 30]
                    for i, dwelling in enumerate(g.Campaign.Dwellings[island - 1]):
                        dwelling.Species = species[i]
                        dwelling.Count = capacities[i] + int(missing == "above")
                    if isinstance(missing, int):
                        g.Campaign.Dwellings[island - 1][missing].Count -= 1
                    if missing == "mixed":
                        g.Campaign.Dwellings[island - 1][0].Count += 50
                        g.Campaign.Dwellings[island - 1][7].Count -= 1
                    other = 4 if island == 1 else 0
                    for dwelling in g.Campaign.Dwellings[other]:
                        dwelling.Count = 0
                    v.set_game(g)
                    before = [[(d.Species, d.Count) for d in land]
                              for land in g.Campaign.Dwellings]
                    charges = []

                    def pay(vm, args):
                        assert list(args) == [200000]
                        charges.append(200000)
                        state = vm.game()
                        if state.Campaign.Gold < 200000:
                            return 1
                        state.Campaign.Gold -= 200000
                        vm.set_game(state)
                        return 0

                    v.responses["PaymentFailed"] = pay
                    seed = next(s for s in range(20000)
                                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) == 3)
                    v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))
                    ready(v, v.invoke("WizardVisit", keys=[54]))
                    needed = isinstance(missing, int) or missing == "mixed"
                    paid = needed and gold >= 200000
                    assert charges == ([200000] if needed else [])
                    assert v.game().Campaign.Gold == gold - (200000 if paid else 0)
                    expected = before
                    if paid:
                        expected[island - 1] = list(zip(species, capacities))
                        if missing == "mixed":
                            expected[island - 1][0] = (species[0], capacities[0] + 50)
                    assert [[(d.Species, d.Count) for d in land]
                            for land in v.game().Campaign.Dwellings] == expected
                    assert any(n == "DrawText" and a[3] ==
                               "*) Воинов во всех жилищах достаточно"
                               for _, n, a in v.calls) == (not needed)

                yield Case(f"dwelling-restock.island-{island}.missing-{missing}.gold-{gold}", dwelling_restock)
        worker_caps = {
            1: [[2, 3, 1, 2], [2, 3, 0, 1], [0, 2, 1, 2], [1, 1, 3, 1], [2, 1, 1, 1]],
            5: [[1, 0, 5, 1], [1, 1, 5, 0], [1, 0, 4, 2], [2, 0, 7, 3], [0, 1, 5, 0]],
        }
        for island, capacities in worker_caps.items():
            deficits = [(i, j) for i, row in enumerate(capacities)
                        for j, count in enumerate(row) if count > 0]
            for missing, gold in [(None, 300000), (None, 0)] + [
                    (cell, 200000) for cell in deficits] + [(deficits[-1], 199999)]:

                def worker_restock(v, island=island, capacities=capacities,
                                   missing=missing, gold=gold):
                    g = preset(v, True)
                    g.Campaign.Island = island
                    g.Campaign.Gold = gold
                    for town, row in zip(g.Campaign.Towns[island - 1], capacities):
                        for j, count in enumerate(row):
                            town.Workers[j] = count
                    if missing is not None:
                        i, j = missing
                        g.Campaign.Towns[island - 1][i].Workers[j] -= 1
                    # Another island is empty: it must neither enable this purchase
                    # nor receive the workers bought for the current island.
                    other = 4 if island == 1 else 0
                    for town in g.Campaign.Towns[other]:
                        for j in range(4):
                            town.Workers[j] = 0
                    v.set_game(g)
                    before = [[list(t.Workers) for t in towns] for towns in g.Campaign.Towns]
                    charges = []

                    def pay(vm, args):
                        assert list(args) == [200000]
                        charges.append(200000)
                        state = vm.game()
                        if state.Campaign.Gold < 200000:
                            return 1
                        state.Campaign.Gold -= 200000
                        vm.set_game(state)
                        return 0

                    v.responses["PaymentFailed"] = pay
                    seed = next(s for s in range(20000)
                                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) == 2)
                    v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))
                    ready(v, v.invoke("WizardVisit", keys=[54]))
                    paid = missing is not None and gold >= 200000
                    assert charges == ([200000] if missing is not None else [])
                    assert v.game().Campaign.Gold == gold - (200000 if paid else 0)
                    expected = before
                    if paid:
                        expected[island - 1] = capacities
                    assert [[list(t.Workers) for t in towns]
                            for towns in v.game().Campaign.Towns] == expected
                    assert any(n == "DrawText" and a[3] ==
                               "*) Работников во всех городах достаточно"
                               for _, n, a in v.calls) == (missing is None)

                yield Case(f"worker-restock.island-{island}.missing-{missing}.gold-{gold}", worker_restock)
        for power in (0, 1):
            for offer, owned in ((1, False), (2, False), (2, True),
                                 (3, False), (4, False), (6, False)):

                def other_offer(v, power=power, offer=offer, owned=owned):
                    g = preset(v, True)
                    g.Campaign.MagicPower = power
                    g.Campaign.Gold = 1000000
                    g.Campaign.MapParts = int(owned)
                    g.Campaign.WizardVisited[0] = 3 if owned else 1
                    g.Campaign.DamageBonus = 25
                    for town in g.Campaign.Towns[0]:
                        town.Scroll = 13
                        for i in range(4):
                            town.Workers[i] = 0
                    for i, dwelling in enumerate(g.Campaign.Dwellings[0]):
                        dwelling.Species = i
                        dwelling.Count = 0
                    v.set_game(g)
                    charged = []
                    price = {1: 100000, 2: 500000, 3: 200000,
                             4: 200000, 6: 100000}[offer]

                    def pay(vm, args):
                        assert list(args) == [price]
                        charged.append(price)
                        state = vm.game()
                        state.Campaign.Gold -= price
                        vm.set_game(state)
                        return 0

                    v.responses["PaymentFailed"] = pay
                    seed = next(s for s in range(20000)
                                if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) == offer - 1)
                    v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))
                    ready(v, v.invoke("WizardVisit", keys=[54]))
                    after = v.game().Campaign
                    assert charged == ([] if owned else [price])
                    assert after.Gold == 1000000 - (0 if owned else price)
                    assert after.MagicPower == power
                    assert not any(n == "TransmuteDwellings" for _, n, _ in v.calls)
                    assert not any(n == "DrawText" and a[3] ==
                                   "*) Для изменения воинов нужна волшебная сила 2"
                                   for _, n, a in v.calls)
                    if offer == 1:
                        assert all(0 <= t.Scroll <= 12 for t in after.Towns[0])
                    elif offer == 2:
                        assert after.MapParts == 1
                        assert after.WizardVisited[0] == 3
                        assert any(n == "RefreshMapParts" for _, n, _ in v.calls) == (not owned)
                    elif offer == 3:
                        assert [list(t.Workers) for t in after.Towns[0]] == [
                            [2, 3, 1, 2], [2, 3, 0, 1], [0, 2, 1, 2],
                            [1, 1, 3, 1], [2, 1, 1, 1]]
                    elif offer == 4:
                        assert [d.Species for d in after.Dwellings[0]] == list(range(8))
                        assert [d.Count for d in after.Dwellings[0]] == [
                            1000, 400, 500, 500, 500, 200, 200, 200]
                    elif offer == 6:
                        assert after.DamageBonus == 1025

                yield Case(f"other-offer-{offer}.power-{power}.owned-{owned}", other_offer)
        for power, gold in ((0, 500000), (1, 500000), (2, 400000), (2, 399999)):

            def transmute_purchase(v, power=power, gold=gold):
                g = preset(v)
                g.Campaign.MagicPower = power
                g.Campaign.Gold = gold
                g.Campaign.WizardRelations[0] = 5
                v.set_game(g)
                before = bytes(g.Campaign.Dwellings)
                operations = []

                def pay(vm, args):
                    assert list(args) == [400000]
                    operations.append("payment")
                    state = vm.game()
                    if state.Campaign.Gold < 400000:
                        return 1
                    state.Campaign.Gold -= 400000
                    vm.set_game(state)
                    return 0

                def transmute(vm, args):
                    assert list(args) == [1]
                    assert operations == ["payment"]
                    assert vm.game().Campaign.Gold == gold - 400000
                    operations.append("transmute")
                    return 0

                v.responses.update(PaymentFailed=pay, TransmuteDwellings=transmute)
                seed = next(s for s in range(20000)
                            if (((s * 134775813 + 1) & 0xFFFFFFFF) * 10 >> 32) == 4)
                v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", seed))
                ready(v, v.invoke("WizardVisit", keys=[54]))
                paid = power >= 2 and gold >= 400000
                assert v.game().Campaign.Gold == gold - (400000 if paid else 0)
                assert operations == (["payment", "transmute"] if paid else
                                      ["payment"] if power >= 2 else [])
                assert bytes(v.game().Campaign.Dwellings) == before
                assert any(n == "DrawText" and a[3] ==
                           "*) Для изменения воинов нужна волшебная сила 2"
                           for _, n, a in v.calls) == (power < 2)

            yield Case(f"transmute-purchase.power-{power}.gold-{gold}", transmute_purchase)
        for active, gold in ((False, 2000), (False, 0), (True, 1000), (True, 999)):

            def contract_hint(v, active=active, gold=gold):
                g = preset(v)
                g.Campaign.MagicPower = 1
                g.Campaign.WizardRelations[0] = 3
                g.Campaign.ContractIsland = 1 if active else 100
                g.Campaign.ContractSlot = 1
                g.Campaign.Gold = gold
                v.set_game(g)
                charged = []

                def pay(vm, args):
                    assert list(args) == [1000]
                    charged.append(1000)
                    state = vm.game()
                    if state.Campaign.Gold < 1000:
                        return 1
                    state.Campaign.Gold -= 1000
                    vm.set_game(state)
                    return 0

                v.responses["PaymentFailed"] = pay
                v.scans.extend([1])
                ready(v, v.invoke("WizardVisit", keys=[52]))
                paid = active and gold >= 1000
                assert v.game().Campaign.Gold == gold - (1000 if paid else 0)
                assert charged == ([1000] if active else [])
                assert any(n == "ShowNotice" and list(a) == [8]
                           for _, n, a in v.calls) == (not active)
                assert any(n == "DrawText" and a[3] == "ЗАМОК ПО КОНТРАКТУ"
                           for _, n, a in v.calls) == paid

            yield Case(f"contract-hint.active-{active}.gold-{gold}", contract_hint)
        for label, keys, gold, attempted, travelled in (
            ("cancel", [51, 27], 20000, False, False),
            ("locked-then-cancel", [51, 53, 27], 20000, False, False),
            ("success", [51, 50], 20000, True, True),
            ("locked-then-success", [51, 53, 50], 5000, True, True),
            ("insufficient", [51, 50], 4999, True, False),
        ):

            def travel(v, keys=keys, gold=gold, attempted=attempted, travelled=travelled):
                g = preset(v)
                g.Campaign.Gold = gold
                g.Campaign.WizardRelations[0] = 2
                g.Campaign.UnlockedIslands = 1
                g.Campaign.HighestVisitedIsland = 1
                g.Campaign.Flags.ShipOwned = True
                g.Campaign.ShipIsland = 5
                v.set_game(g)
                operations = []

                def pay(vm, args):
                    assert list(args) == [5000]
                    assert vm.game().Runtime.LastScan == 50
                    operations.append("payment")
                    state = vm.game()
                    if state.Campaign.Gold < 5000:
                        return 1
                    state.Campaign.Gold -= 5000
                    vm.set_game(state)
                    return 0

                def enter(vm, args):
                    assert list(args) == [2]
                    assert operations == ["payment"]
                    state = vm.game()
                    assert state.Campaign.ShipIsland == 1
                    state.Campaign.Island = 2
                    vm.set_game(state)
                    operations.append("enter")
                    return 0

                def land(vm, args):
                    state = vm.game()
                    state.Campaign.Hero.X = 20
                    state.Campaign.Hero.Y = 21
                    vm.set_game(state)
                    operations.append("land")
                    return 0

                v.responses.update(PaymentFailed=pay, EnterIsland=enter, RandomHeroLanding=land)
                ready(v, v.invoke("WizardVisit", keys=keys))
                after = v.game().Campaign
                assert operations == (["payment", "enter", "land"] if travelled else
                                      ["payment"] if attempted else [])
                assert after.Gold == gold - (5000 if travelled else 0)
                assert after.Island == (2 if travelled else 1)
                assert after.ShipIsland == (1 if travelled else 5)
                assert after.UnlockedIslands == (2 if travelled else 1)
                assert after.HighestVisitedIsland == (2 if travelled else 1)
                assert (after.Hero.X, after.Hero.Y) == (
                    (20, 21) if travelled else (g.Campaign.Hero.X, g.Campaign.Hero.Y))
                if not travelled:
                    assert after.WizardRelations[0] == 3

            yield Case(f"travel-payment.{label}", travel)
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

            for count, expected, alternate in (
                (32767, 65534, False),
                (32768, 65535, False),
                (65535, 65535, True),
            ):

                def castle_army_reward(v, count=count, expected=expected, alternate=alternate):
                    g = preset(v)
                    g.Campaign.QuestFlags[0] = 0
                    g.Campaign.Army[0].Species = 0
                    g.Campaign.Army[0].Count = count
                    g.Campaign.Flags.ArmyAvailable = True
                    v.set_game(g)

                    keys = [50, 50, 49, 27] if alternate else [50, 50, 27]
                    ready(v, v.invoke("CastleVisit", keys=keys))

                    if alternate:
                        notice, = (
                            i for i, (_, name, args) in enumerate(v.calls)
                            if name == "ShowNotice" and args == [26]
                        )
                        before, after = (
                            i for i, (_, name, args) in enumerate(v.calls)
                            if name == "DrawText" and args[3] == "2) Войско"
                        )
                        assert before < notice < after

                    after = v.game().Campaign
                    assert after.Army[0].Count == expected, after.Army[0].Count
                    assert after.Army[0].Species == 0
                    assert after.Gold == g.Campaign.Gold + (500000 if alternate else 0)
                    assert after.Income == g.Campaign.Income + 2000
                    assert after.QuestFlags[0] == 100

                yield Case(f"ruler-reward.army-count-{count}", castle_army_reward)

            for label, count, expected, remaining in (
                ("fits", 20, 25, 0),
                ("partial", 65533, 65535, 3),
                ("full", 65535, 65535, 5),
            ):

                def transfer_garrison(v, count=count, expected=expected, remaining=remaining):
                    g = preset(v)
                    g.Campaign.Army[0].Species = 0
                    g.Campaign.Army[0].Count = count
                    castle = g.Campaign.Castles[0][0]
                    castle.Owned = True
                    castle.Species[0] = 0
                    castle.Counts[0] = 5
                    v.set_game(g)

                    ready(v, v.invoke("CastleVisit", keys=[49, 27]))

                    after = v.game().Campaign
                    guard = after.Castles[0][0]
                    assert after.Army[0].Count == expected, after.Army[0].Count
                    assert after.Army[0].Species == 0
                    assert guard.Species[0] == (0 if remaining else 100), guard.Species[0]
                    if remaining:
                        assert guard.Counts[0] == remaining, guard.Counts[0]
                    notices = [args for _, name, args in v.calls if name == "ShowNotice"]
                    assert notices == ([[27]] if count == 65535 else []), notices

                yield Case(f"garrison-transfer.{label}", transfer_garrison)
    if module == "KBUI":

        for label, notice, column, message in (
            ("ruler-reward", 26, 13, "Отряд полон. Выберите другую награду."),
            ("garrison-transfer", 27, 25, "Отряд полон."),
        ):

            def full_army_notice(v, notice=notice, column=column, message=message):
                v.fixture()
                v.scans.append(57)
                ready(v, v.invoke("ShowNotice", notice))
                assert v.calls[0][1:] == ("ClearRectangle", [8, 230, 488, 320])
                assert v.calls[-2][1:] == ("DrawText", [0, column, 272, message]), v.calls[-2]
                assert v.calls[-1][1] == "ReadScanCode"
                assert v.game().Runtime.LastScan == 57

            yield Case(f"{label}.full-army-notice", full_army_notice)
    if module == "KBDWELL":
        for wanted in (0, 11):

            def recruit_without_purchase(v, wanted=wanted):
                g = preset(v)
                g.Campaign.Dwellings[0][0].Count = 10
                g.Campaign.EnemyGrace = 7
                v.set_game(g)

                # Run KBEcon in the same game state as DwellingVisit.
                economy = {
                    address: entry
                    for address, entry in v.functions.items()
                    if entry[0] == "KBECON"
                }
                assert any(meta["name"] == "BuyQuantity" for _, meta in economy.values())
                for address in economy:
                    del v.functions[address]
                keys = [ord(digit) for digit in str(wanted)] + [13, 27]
                try:
                    ready(v, v.invoke("DwellingVisit", keys=keys))
                finally:
                    v.functions.update(economy)

                after = v.game().Campaign
                assert after.Army[0].Species == 100, after.Army[0].Species
                assert after.Army[0].Count == 0
                assert not after.Flags.ArmyAvailable
                assert after.EnemyGrace == 7
                assert after.Dwellings[0][0].Count == 10
                assert after.Gold == g.Campaign.Gold

            yield Case(f"recruit.no-purchase.stock-10.quantity-{wanted}", recruit_without_purchase)
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
