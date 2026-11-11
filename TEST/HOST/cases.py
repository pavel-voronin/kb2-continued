"""Unit cases. Expected behaviour is asserted independently of coverage."""

from dataclasses import dataclass
import ctypes as C
import struct
from runtime import linear, Creature, INDEX


@dataclass
class Case:
    name: str
    run: object
    identity: str = ""


def ready(vm, result):
    assert result[1] == {"kind": "ready"}, result
    return result[0]


def cases(module):
    if module == "KBRANDOM":

        def initialization(v):
            points = {
                p["id"]
                for p in INDEX["points"]
                if p["file"] == "KBRANDOM.PAS" and p["routine"] == "$init"
            }
            assert points and points <= v.boot_hits.keys()
            v.reset()
            v.cpu.mem_write(v.addresses[2][0], struct.pack("<i", 12345))
            ready(v, v.invoke("RandomizeGame"))
            assert v.read(v.addresses[2][0], 4) != struct.pack("<i", 12345)

        yield Case("initialization.clock-seed-enabled", initialization)
    if module == "KBECON":
        for function in ("BuyQuantity", "BuyByteQuantity"):

            def cancelled(v, function=function):
                v.fixture()
                dest = v.alloc(b"\x05\x00")
                stock = v.alloc(b"\x0a\x00")
                ready(v, v.invoke(function, 1, 100, dest, stock, keys=[27]))
                assert (
                    v.read(linear(dest), 2) == b"\x05\x00"
                    and v.read(linear(stock), 2) == b"\x0a\x00"
                )

            yield Case(function + ".cancelled-quantity", cancelled)
    if module == "KBINPUT":

        def pending_key(v):
            v.fixture()
            v.queue.append((72, 0))
            assert ready(v, v.invoke("BIOSKeyPressed")) == 1
            assert ready(v, v.invoke("BIOSKeyPressed")) == 1
            assert ready(v, v.invoke("ReadScanCode")) == 72
            assert ready(v, v.invoke("BIOSKeyPressed")) == 0

        yield Case("bios.peek-does-not-consume-extended-key", pending_key)
    if module == "KBART":

        def artwork(v):
            v.fixture()
            ready(v, v.invoke("AllocateArtwork"))
            g = v.game()
            blocks = (
                (11, 8640),
                (10, 43200),
                (12, 11520),
                (14, 2880),
                (13, 5760),
                (0, 46800),
                (1, 46800),
                (2, 46800),
                (3, 46800),
                (4, 46800),
                (5, 46800),
            )
            ranges = sorted(
                (linear(g.Runtime.PictureBanks[i]), size) for i, size in blocks
            )
            assert sum(size for _, size in ranges) == 352800
            assert all(a + size <= b for (a, size), (b, _) in zip(ranges, ranges[1:]))
            for alias, bank in ((6, 11), (7, 10), (8, 12)):
                assert g.Runtime.PictureBanks[alias] == g.Runtime.PictureBanks[bank]
            ready(v, v.invoke("ReleaseArtwork"))
            ready(v, v.invoke("AllocateArtwork"))
            assert bytes(v.game().Runtime.PictureBanks) == bytes(g.Runtime.PictureBanks)
            ready(v, v.invoke("ReleaseArtwork"))

        yield Case("artwork.allocate-release-no-overlap", artwork)
    if module == "KBBDRAW":
        for x in range(6):
            for y in range(5):

                def find(v, x=x, y=y):
                    g = v.fixture()
                    g.Runtime.BattleField[x][y] = 118
                    v.set_game(g)
                    px = v.alloc(b"\xff")
                    py = v.alloc(b"\xff")
                    ready(v, v.invoke("FindUnitCell", 2, 112, px, py))
                    assert v.read(linear(px), 1) == bytes([x]) and v.read(
                        linear(py), 1
                    ) == bytes([y])

                yield Case(f"find-unit.{x}.{y}", find)
    layouts = {
        "KBTYPES": {
            "TDirection": 2,
            "TPosition": 2,
            "TContract": 2,
            "TRelic": 2,
            "TCreatureDefinition": 18,
            "TCreatureCost": 2,
        },
        "KBBTYPE": {
            "TReserveState": 78,
            "TEnemyAIState": 68,
            "TCombatUnit": 15,
            "TBattleState": 360,
        },
        "KBSTATE": {
            "TGameState": 50592,
            "TCampaignState": 46816,
            "TCampaignFlags": 21814,
        },
        "KBTABLES": {"CreatureDefinitions": 540},
    }
    if module in layouts:
        for typ, size in layouts[module].items():

            def layout(v, typ=typ, size=size):
                v.fixture()
                assert ready(v, v.invoke("SizeOf" + typ)) == size

            yield Case("layout." + typ, layout)
    elif module == "KBECON":
        for gold, cost in (
            (0, 0),
            (0, 1),
            (100, 99),
            (100, 100),
            (100, 101),
            (100, -1),
            (2147483647, 2147483647),
            (-1, 0),
        ):

            def payment(v, gold=gold, cost=cost):
                g = v.fixture()
                g.Campaign.Gold = gold
                g.Runtime.PicturePage = 32768
                v.set_game(g)
                result = ready(v, v.invoke("PaymentFailed", cost))
                failed = gold < cost
                assert bool(result) == failed
                assert v.game().Campaign.Gold == (
                    gold if failed else C.c_int32(gold - cost).value
                )
                assert v.game().Runtime.PicturePage == 32768
                assert any(
                    n == ("ShowNotice" if failed else "RefreshGold")
                    for _, n, _ in v.calls
                )

            yield Case(f"payment.{gold}.{cost}", payment)
        for text, expected, accepted in (
            ([49, 50, 8, 51, 13], 13, True),
            ([8, 52, 13], 4, True),
            ([27], 0, False),
            ([13], 0, True),
            ([65, 50, 13], 2, True),
            ([49, 50, 51, 52, 53, 54], 123456, True),
        ):

            def quantity(v, text=text, expected=expected, accepted=accepted):
                v.fixture()
                p = v.alloc(struct.pack("<i", 999))
                result = ready(v, v.invoke("ReadQuantity", p, keys=text))
                assert bool(result) == accepted
                assert struct.unpack("<i", v.read(linear(p), 4))[0] == expected

            yield Case("quantity." + ".".join(map(str, text)), quantity)
        for stock, capacity, wanted, gold, price in (
            (10, 10, 3, 10000, 100),
            (2, 10, 3, 10000, 100),
            (10, 2, 3, 10000, 100),
            (10, 10, 3, 10000, 5000),
            (10, 10, 0, 10000, 100),
            (10, 10, 3, 0, 0),
            (10, 10, 3, 5000, 100),
            (255, 255, 254, 100000, 1),
        ):
            for function, stockfmt in (("BuyQuantity", "H"), ("BuyByteQuantity", "B")):

                def buy(
                    v,
                    stock=stock,
                    capacity=capacity,
                    wanted=wanted,
                    gold=gold,
                    price=price,
                    function=function,
                    stockfmt=stockfmt,
                ):
                    g = v.fixture()
                    g.Campaign.Gold = gold
                    v.set_game(g)
                    destination = v.alloc(struct.pack("<H", 7))
                    supply = v.alloc(struct.pack("<" + stockfmt, stock))
                    ready(
                        v,
                        v.invoke(
                            function,
                            capacity,
                            price,
                            destination,
                            supply,
                            keys=[ord(ch) for ch in str(wanted)] + [13],
                        ),
                    )
                    received = (
                        struct.unpack("<H", v.read(linear(destination), 2))[0] - 7
                    )
                    remaining = struct.unpack(
                        "<" + stockfmt,
                        v.read(
                            linear(supply),
                            C.sizeof(C.c_uint16) if stockfmt == "H" else 1,
                        ),
                    )[0]
                    assert received + remaining == stock
                    if (
                        wanted > min(capacity, stock)
                        or gold > 5000
                        and price * wanted > gold
                    ):
                        assert received == 0
                    else:
                        assert received == wanted
                        if gold > 5000:
                            assert v.game().Campaign.Gold == gold - price * wanted
                        else:
                            assert 0 <= gold - v.game().Campaign.Gold <= price * wanted

                yield Case(
                    f"{function}.{stock}.{capacity}.{wanted}.{gold}.{price}", buy
                )
    elif module == "KBWORLD":

        def discovery(v):
            g = v.fixture()
            C.memset(
                C.addressof(g.Campaign.Flags.Discovery),
                1,
                C.sizeof(g.Campaign.Flags.Discovery),
            )
            v.set_game(g)
            ready(v, v.invoke("ForgetDiscovery"))
            assert not any(bytes(v.game().Campaign.Flags.Discovery))

        yield Case("discovery.clear", discovery)
        for island in range(1, 6):

            def enter(v, island=island):
                v.fixture()
                ready(v, v.invoke("EnterIsland", island))
                assert v.game().Campaign.Island == island

            yield Case(f"enter.{island}", enter)

            def place(v, island=island):
                v.fixture()
                p = v.alloc(bytes((0, 0)))
                ready(v, v.invoke("PlaceRoamingObject", island, 12, p))
                x, y = v.read(linear(p), 2)
                assert v.game().Campaign.Map[island - 1][x][y] == 12

            yield Case(f"place.{island}", place)

            def relocate(v, island=island):
                v.fixture()
                ready(v, v.invoke("RelocateArmy", island, 0))
                a = v.game().Campaign.WanderingArmies[island - 1][0]
                assert v.game().Campaign.Map[island - 1][a.X][a.Y] == 5

            yield Case(f"relocate.{island}", relocate)
    elif module == "KBRANDOM":
        for seed in (0, 1, -1, 12345, 2147483647):

            def setseed(v, seed=seed):
                v.fixture()
                ready(v, v.invoke("UseRandomSeed", seed))
                assert struct.unpack("<i", v.read(v.addresses[2][0], 4))[0] == seed
                ready(v, v.invoke("RandomizeGame"))
                assert struct.unpack("<i", v.read(v.addresses[2][0], 4))[0] == seed

            yield Case(f"fixed.{seed}", setseed)

        def clock(v):
            v.fixture()
            ready(v, v.invoke("UseClockSeed"))
            before = v.read(v.addresses[2][0], 4)
            ready(v, v.invoke("RandomizeGame"))
            assert before == v.read(v.addresses[2][0], 4)

        yield Case("clock.fixed-bios-time", clock)
    elif module == "KBFILES":
        for si, di, size in ((0, 0, 0), (0, 0, 1), (1, 2, 7), (3, 1, 16), (0, 0, 511)):

            def copy(v, si=si, di=di, size=size):
                v.fixture()
                source = v.alloc(bytes(i % 256 for i in range(2048)))
                dest = v.alloc(bytes([255]) * 2048)
                ready(v, v.invoke("CopyRecord", si, di, size, source, dest))
                copied = size // 2 * 2
                assert v.read(linear(dest) + di * size, copied) == v.read(
                    linear(source) + si * size, copied
                )
                if size % 2:
                    assert v.read(linear(dest) + di * size + copied, 1) == b"\xff"
                assert v.read(linear(dest), di * size) == bytes([255]) * (di * size)

            yield Case(f"copy.{si}.{di}.{size}", copy)
        for size in (0, 1, 511, 4096):

            def load(v, size=size):
                v.fixture()
                payload = bytes(i % 251 for i in range(size))
                v.disk["UNIT.BIN"] = payload
                buffer = v.alloc(bytes([255]) * (size + 8))
                name = v.string_arg("UNIT.BIN")
                ready(v, v.invoke("LoadResourceFile", buffer, name))
                assert v.read(linear(buffer), size) == payload
                assert v.read(linear(buffer) + size, 8) == bytes([255]) * 8

            yield Case(f"load.{size}", load)
        for packet in range(5):

            def frames(v, packet=packet):
                v.fixture()
                v.disk["UNIT.PIC"] = b"".join(bytes([i]) * 8640 for i in range(5))
                buffer = v.alloc(bytes(8640))
                name = v.string_arg("UNIT.PIC")
                ready(v, v.invoke("LoadCreatureFrames", packet, buffer, name))
                assert v.read(linear(buffer), 8640) == bytes([packet]) * 8640

            yield Case(f"frames.{packet}", frames)
    elif module == "KBBDMG":
        for species in range(30):
            for hp, damage in (
                (0, 0),
                (100, 0),
                (100, 1),
                (100, 100),
                (100, 101),
                (10000, 65535),
            ):

                def damage_case(v, species=species, hp=hp, damage=damage):
                    v.fixture()
                    defs = (Creature * 30).from_buffer_copy(
                        v.read(v.addresses[1][0], 540)
                    )
                    if species >= 25:
                        defs[species] = defs[0]
                        v.cpu.mem_write(v.addresses[1][0], bytes(defs))
                    p = v.alloc(struct.pack("<i", hp))
                    killed = ready(v, v.invoke("ApplyDamage", species, damage, p))
                    after = struct.unpack("<i", v.read(linear(p), 4))[0]
                    assert after == max(0, hp - damage)
                    defense = defs[species].Defense
                    assert killed == (
                        65535
                        if damage >= hp
                        else (hp + defense - 1) // defense
                        - (after + defense - 1) // defense
                    )

                yield Case(f"damage.{species}.{hp}.{damage}", damage_case)
    elif module == "KBADVENT":
        for mask in range(256):

            def count(v, mask=mask):
                g = v.fixture()
                for i in range(8):
                    g.Campaign.Flags.SpellAvailable[i] = bool(mask & (1 << i))
                v.set_game(g)
                assert ready(v, v.invoke("CountRitualSpells")) == mask.bit_count()

            yield Case(f"ritual-count.{mask}", count)
        for mask in (0, 1, 127, 254, 255):

            def hidden(v, mask=mask):
                g = v.fixture()
                for i in range(8):
                    g.Campaign.Flags.SpellAvailable[i] = bool(mask & (1 << i))
                v.set_game(g)
                ready(v, v.invoke("PlaceHiddenSpell"))
                c = v.game().Campaign
                if mask == 255:
                    assert c.HiddenSpellIsland == 100
                else:
                    assert 1 <= c.HiddenSpellIsland <= 5 and not mask & (
                        1 << c.HiddenSpellEffect
                    )
                    assert (
                        c.Map[c.HiddenSpellIsland - 1][c.HiddenSpellPosition.X][
                            c.HiddenSpellPosition.Y
                        ]
                        == 0
                    )

            yield Case(f"hidden.{mask}", hidden)
        for power in (0, 1, 2, 5, 6, 10, 11, 20, 21, 255):

            def transmute(v, power=power):
                g = v.fixture()
                g.Campaign.MagicPower = power
                old = bytes(g.Campaign.Dwellings)
                v.set_game(g)
                ready(v, v.invoke("TransmuteDwellings", 1))
                d = v.game().Campaign.Dwellings
                if power < 2:
                    assert bytes(d) == old
                else:
                    assert all(0 <= a.Species <= 24 and a.Count > 0 for a in d[0])
                assert bytes(d)[C.sizeof(d[0]) :] == old[C.sizeof(d[0]) :]

            yield Case(f"dwellings.power.{power}", transmute)
        for grace in (0, 1, 40):

            def roaming(v, grace=grace):
                g = v.fixture()
                g.Campaign.EnemyGrace = grace
                v.set_game(g)
                ready(v, v.invoke("RefreshRoamingArmyArt"))
                call = next(args for _, name, args in v.calls if name == "CopyRecord")
                assert call[2] == 2880

            yield Case(f"army-art.{grace}", roaming)

        def abandon(v):
            g = v.fixture()
            g.Campaign.Flags.ShipOwned = True
            g.Campaign.ShipBackground = 51
            g.Campaign.Map[0][25][25] = 14
            v.set_game(g)
            ready(v, v.invoke("AbandonShip"))
            c = v.game().Campaign
            assert not c.Flags.ShipOwned and c.Map[0][25][25] == 51

        yield Case("abandon-ship", abandon)
        for sailing in (False, True):

            def landing(v, sailing=sailing):
                g = v.fixture()
                g.Runtime.ShipAbandonBlocked = sailing
                g.World.GenerationX = 20
                g.World.GenerationY = 21
                v.set_game(g)
                ready(v, v.invoke("EncounterLanding"))
                a = v.game()
                assert (a.Campaign.Hero.X, a.Campaign.Hero.Y) == (20, 21)
                assert not a.Runtime.ShipAbandonBlocked
                assert any(name == "PlaceShip" for _, name, _ in v.calls) == sailing

            yield Case(f"landing.{sailing}", landing)
    elif module == "KBGEN":
        for level in range(4):

            def generation(v, level=level):
                v.fixture()
                v.cpu.mem_write(v.addresses[2][0], struct.pack("<I", 12345 + level))
                ready(v, v.invoke("PrepareCampaign", level))
                ready(
                    v,
                    v.invoke(
                        "GenerateWorld", level, instructions=100_000_000, seconds=25
                    ),
                )
                ready(v, v.invoke("PlaceInitialHero", level))
                c = v.game().Campaign
                assert c.Difficulty == 6 - level and 1 <= c.Island <= 5, (
                    "level",
                    level,
                    c.Difficulty,
                    c.Island,
                )
                for island in range(5):
                    assert len({(x.X, x.Y) for x in c.Castles[island]}) == 5, (
                        "castles",
                        level,
                        island,
                    )
                    assert len({(x.X, x.Y) for x in c.Towns[island]}) == 5, (
                        "towns",
                        level,
                        island,
                    )
                    for castle in c.Castles[island]:
                        assert c.Map[island][castle.X][castle.Y] == 2, (
                            "castle-tile",
                            level,
                            island,
                            castle.X,
                            castle.Y,
                            c.Map[island][castle.X][castle.Y],
                        )
                        assert all(n >= 2 for n in castle.Counts), (
                            "garrison",
                            level,
                            island,
                            list(castle.Counts),
                        )
                    for town in c.Towns[island]:
                        # B014: this fixed seed places a castle wall over a town.
                        known = (level, island, town.X, town.Y) == (1, 4, 60, 42)
                        wanted = 3 if known else 7
                        assert c.Map[island][town.X][town.Y] == wanted, (
                            "town-tile",
                            level,
                            island,
                            town.X,
                            town.Y,
                        )
                if level == 1:
                    assert any(t.X == 60 and t.Y == 42 for t in c.Towns[4])
                assert 0 <= c.Hero.X < 66 and 0 <= c.Hero.Y < 66

            yield Case(f"world.level.{level}", generation)
