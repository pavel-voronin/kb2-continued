"""Short orchestration protocols; the game loop is never a playthrough."""

from cases import Case, ready
from characterise import preset, tree, projection
from runtime import INDEX


def cases(module):
    if module == "KBHERO":

        def unpopulated_row(v):
            g = preset(v)
            g.Campaign.Army[1].Species = 0
            g.Campaign.Army[1].Count = 3
            g.Campaign.Flags.ArmyAvailable = True
            v.set_game(g)
            entry = next(
                p["id"]
                for p in INDEX["points"]
                if p["file"] == "KBHERO.PAS"
                and p["routine"] == "DismissArmy"
                and p["kind"] == "routine"
            )

            def stack_background(vm):
                ss = vm.r("ss") * 16
                child = vm.r("bp")
                parent = vm.word(ss + child)
                low = child + 8
                assert 10 <= parent - low < 1024
                vm.cpu.mem_write(ss + low, b"\x09" * (parent - low))

            v.entry_probes[entry] = stack_background
            ready(v, v.invoke("DismissArmy", keys=[57]))
            assert (
                v.game().Campaign.Army[1].Species == 0
                and v.game().Campaign.Flags.ArmyAvailable
            )

        yield Case(
            "dismiss.unpopulated-row-with-defined-stack-background", unpopulated_row
        )
    elif module == "KBAPP":

        def loop(v):
            preset(v)
            commands = iter((72, 68, 68))
            answers = iter((0, 1))
            v.mock_own = {
                "WaitForCommand",
                "DispatchCommand",
                "UpdateHeroFacing",
                "ResolveMovement",
                "AdvanceAdventureTime",
                "ConfirmExit",
            }

            def command(vm, args):
                g = vm.game()
                g.Runtime.LastScan = next(commands)
                vm.set_game(g)
                return 0

            v.responses.update(
                WaitForCommand=command, ConfirmExit=lambda vm, args: next(answers)
            )
            before = tree(v.game())
            disk = v.disk.copy()
            tables = v.read(v.addresses[1][0], 540)
            result = v.invoke("RunGame")
            ready(v, result)
            assert sum(name == "WaitForCommand" for _, name, _ in v.calls) == 3
            assert sum(name == "ConfirmExit" for _, name, _ in v.calls) == 2
            return projection(v, before, [], result, disk, tables)

        yield Case("loop.command-then-rejected-exit-then-confirmed-exit", loop)

        def grace(v):
            g = preset(v)
            g.Runtime.LastScan = 72
            g.Campaign.EnemyGrace = 1
            v.set_game(g)

            def expire(vm, args):
                state = vm.game()
                state.Campaign.EnemyGrace = 0
                vm.set_game(state)
                return 0

            v.responses["AdvanceNearbyRoamers"] = expire
            ready(v, v.invoke("ResolveMovement"))
            assert any(
                name == "CopyRecord" and args[:3] == [0, 5, 2880]
                for _, name, args in v.calls
            )

        yield Case("movement.grace-expiry-refreshes-army-art", grace)
        from matrix import sample

        yield sample(
            module, "WaitForCommand", "idle-below-million", rich=False, idle_polls=3
        )
    elif module == "KBMAP":
        from matrix import sample

        yield sample(
            module,
            "MapVisit",
            "printer-unavailable-local-io-disabled",
            values=[1],
            scans=[63, 1],
        )
        yield sample(
            module,
            "MapVisit",
            "undiscovered-printer-and-unmapped-tile",
            values=[1],
            scans=[63, 1],
            printer=True,
            changes={
                "Campaign.Flags.Discovery.0.30.30": True,
                "Campaign.Map.0.30.30": 16,
            },
        )
        yield sample(
            module,
            "MapVisit",
            "unsupported-island-zero",
            values=[0],
            scans=[63, 1],
            printer=True,
        )

        def blink(v):
            preset(v)
            polls = 0

            def pressed(vm, args):
                nonlocal polls
                polls += 1
                return int(polls > 1)

            v.responses["BIOSKeyPressed"] = pressed
            v.scans.append(1)
            ready(v, v.invoke("MapVisit", 1, instructions=120_000_000, seconds=30))
            assert polls == 2

        yield Case("map.cursor-blinks-until-key", blink)
