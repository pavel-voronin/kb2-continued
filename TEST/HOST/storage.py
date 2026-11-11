"""Independent bit-stream oracle for the campaign codec."""

import ctypes as C
from cases import Case, ready
from runtime import linear


def cases(module):
    if module != "KBSAVE":
        return
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
            ready(v, v.invoke("WriteCampaign"))
            assert v.disk["KB2.DAT"] == wanted
            # Feed the independently encoded stream to the actual reader.
            v.fixture()
            v.disk["KB2.DAT"] = wanted
            ready(v, v.invoke("ReadCampaign"))
            actual = bytes(v.game().Campaign)
            assert actual == bytes(int(bool(b)) for b in flags) + bytes(g.Campaign)[n:]

        yield Case(f"codec.flags-{pattern}", codec)

    def oversized(v):
        g = v.fixture()
        p = linear(g.Runtime.PictureBanks[0])
        v.cpu.mem_write(p + 46800, b"\xee")
        v.disk["KB2.DAT"] = b"\xaa" * 47500
        ready(v, v.invoke("ReadCampaign"))
        assert v.read(p + 46800, 1) == b"\xaa"

    yield Case("B004.oversized-save-overwrites-buffer-canary", oversized)
