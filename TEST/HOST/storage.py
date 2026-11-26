"""Independent bit-stream oracle for the campaign codec."""

import ctypes as C
from cases import Case, ready
from runtime import linear


def cases(module):
    if module != "KBSAVE":
        return
    def roaming_markers(v):
        g = v.fixture()
        g.Campaign.Island = 5
        g.World.WizardPosition.X, g.World.WizardPosition.Y = 20, 21
        g.World.MagePosition.X, g.World.MagePosition.Y = 22, 23
        for land in (0, 4):
            g.Campaign.Map[land][20][21] = 12
            g.Campaign.Map[land][22][23] = 28
        g.Campaign.Map[4][20][22] = 4
        v.set_game(g)
        return bytes(g.Campaign.Map)

    for strip in (False, True):

        def save_markers(v, strip=strip):
            original_map = roaming_markers(v)
            ready(v, v.invoke("PrepareSave"))
            assert bytes(v.game().Campaign.Map) == original_map
            assert ready(v, v.invoke("WriteCampaign", strip)) == 1
            assert bytes(v.game().Campaign.Map) == original_map
            g = v.game()
            if strip:
                g.Campaign.Map[4][20][21] = 0
                g.Campaign.Map[4][22][23] = 0
            ready(v, v.invoke("ReadCampaign"))
            assert bytes(v.game().Campaign.Map) == bytes(g.Campaign.Map)

        yield Case(f"campaign-save.roaming-markers.strip-{strip}", save_markers)

    for failure in ("create", "short-write", "write", "close"):

        def save_failure(v, failure=failure):
            original_map = roaming_markers(v)
            v.disk.pop("KB2.DAT", None)
            ready(v, v.invoke("PrepareSave"))
            calls = []
            segment = v.r("ds")

            def dos(vm, operation):
                if operation not in (0x3C, 0x40, 0x3E):
                    return False
                calls.append(operation)
                if operation == 0x40:
                    assert vm.r("cx") == 27729
                    assert vm.files[vm.r("bx")][0] == "KB2.DAT"
                if (operation, failure) == (0x40, "short-write"):
                    vm.w("cx", 27728)
                    return False
                if (operation, failure) in (
                    (0x3C, "create"), (0x40, "write"), (0x3E, "close")
                ):
                    vm.carry(True)
                    vm.w("ax", 5)
                    return True
                return False

            v.responses["DOS21"] = dos
            assert ready(v, v.invoke("WriteCampaign", True)) == 0
            assert bytes(v.game().Campaign.Map) == original_map
            assert v.r("ds") == segment
            assert [n for _, n, _ in v.calls].count("LoadResourceFile") == 1
            if failure == "create":
                assert calls == [0x3C]
                assert "KB2.DAT" not in v.disk
            else:
                assert calls == [0x3C, 0x40, 0x3E]
                assert len(v.disk["KB2.DAT"]) == {"short-write": 27728, "write": 0, "close": 27729}[failure]
                if failure != "close":
                    assert not any(f[0] == "KB2.DAT" for f in v.files.values())

        yield Case(f"campaign-save.failure-{failure}", save_failure)

    for label, saved_flag, slots, expected_slots, expected_flag in (
        ("only-zero", True, {0: (0, 0), 9: (29, 0)}, {}, False),
        ("active-survivor", True, {0: (0, 0), 3: (2, 7)}, {3: (2, 7)}, True),
        ("reserve-survivor", False, {1: (0, 0), 9: (29, 4)}, {9: (29, 4)}, True),
        ("empty-with-old-count", True, {2: (100, 7)}, {2: (100, 7)}, False),
    ):
        def load_old_army(v, saved_flag=saved_flag, slots=slots,
                          expected_slots=expected_slots, expected_flag=expected_flag):
            game = v.fixture()
            game.Campaign.Flags.ArmyAvailable = saved_flag
            game.Campaign.Gold = 123456
            for i, (species, count) in slots.items():
                slot = game.Campaign.Army[i]
                slot.Species, slot.Count = species, count
            v.set_game(game)
            assert ready(v, v.invoke("WriteCampaign", False)) == 1
            saved = v.disk["KB2.DAT"]

            v.fixture()
            v.disk["KB2.DAT"] = saved
            ready(v, v.invoke("ReadCampaign"))

            loaded = v.game().Campaign
            actual = [(slot.Species, slot.Count) for slot in loaded.Army]
            assert actual == [expected_slots.get(i, (100, 0)) for i in range(10)], actual
            assert bool(loaded.Flags.ArmyAvailable) == expected_flag, loaded.Flags.ArmyAvailable
            assert loaded.Gold == 123456
            assert v.disk["KB2.DAT"] == saved

        yield Case(f"campaign-load.old-army.{label}", load_old_army)

    def missing_campaign(v):
        game = v.fixture()
        game.Campaign.Army[0].Species = 0
        game.Campaign.Army[0].Count = 2
        v.set_game(game)
        v.disk.pop("KB2.DAT", None)
        ready(v, v.invoke("ReadCampaign"))
        assert bytes(v.game().Campaign) == bytes(game.Campaign)

    yield Case("campaign-load.missing-keeps-army", missing_campaign)

    for pattern in (0, 1, 255, "mixed"):

        def codec(v, pattern=pattern):
            g = v.fixture()
            n = C.sizeof(g.Campaign.Flags)
            flags = bytes(
                (i * 17 % 256 if pattern == "mixed" else pattern) for i in range(n)
            )
            C.memmove(C.addressof(g.Campaign.Flags), flags, n)
            v.set_game(g)
            packed = bytes(
                sum(int(bool(flags[i + j])) << j for j in range(min(8, n - i)))
                for i in range(0, n, 8)
            )
            wanted = packed + bytes(g.Campaign)[n:]
            assert ready(v, v.invoke("WriteCampaign", False)) == 1
            assert v.disk["KB2.DAT"] == wanted
            # Feed the independently encoded stream to the actual reader.
            v.fixture()
            v.disk["KB2.DAT"] = wanted
            ready(v, v.invoke("ReadCampaign"))
            actual = bytes(v.game().Campaign)
            expected_flags = type(g.Campaign.Flags).from_buffer_copy(
                bytes(int(bool(b)) for b in flags)
            )
            expected_flags.ArmyAvailable = False
            assert actual == bytes(expected_flags) + bytes(g.Campaign)[n:]

        yield Case(f"codec.flags-{pattern}", codec)

    def oversized(v):
        g = v.fixture()
        p = linear(g.Runtime.PictureBanks[0])
        v.cpu.mem_write(p + 46800, b"\xee")
        v.disk["KB2.DAT"] = b"\xaa" * 47500
        ready(v, v.invoke("ReadCampaign"))
        assert v.read(p + 46800, 1) == b"\xaa"

    yield Case("B004.oversized-save-overwrites-buffer-canary", oversized)
