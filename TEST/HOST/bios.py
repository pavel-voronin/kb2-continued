"""Assert the exact BIOS requests made by the video leaf routines."""

import unicorn as uc
from cases import Case, ready


def cases(module):
    if module not in ("KBGFX", "KBSESS"):
        return
    for value in (0, 1, 255):

        def request(v, value=value, module=module):
            v.fixture()
            observed = []

            def interrupt(cpu, number, unused):
                if number == 0x10:
                    observed.append(v.r("ax"))

            hook = v.cpu.hook_add(uc.UC_HOOK_INTR, interrupt)
            try:
                routine = "SetVideoPage" if module == "KBGFX" else "SetGraphicsMode"
                ready(v, v.invoke(routine, value))
            finally:
                v.cpu.hook_del(hook)
            expected = 0x500 | value if module == "KBGFX" else (16 if value else 2)
            assert observed == [expected], observed

        yield Case(f"bios.video-request.{value}", request)
