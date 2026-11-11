"""Independent PCX/packer fixtures, including current rejection behaviour."""

import struct
from cases import Case, ready
from runtime import linear

PALETTE = bytes(
    (
        0,
        0,
        0,
        0,
        0,
        170,
        0,
        170,
        0,
        0,
        170,
        170,
        170,
        0,
        0,
        170,
        0,
        170,
        170,
        85,
        0,
        170,
        170,
        170,
        85,
        85,
        85,
        85,
        85,
        255,
        85,
        255,
        85,
        85,
        255,
        255,
        255,
        85,
        85,
        255,
        85,
        255,
        255,
        255,
        85,
        255,
        255,
        255,
    )
)


def pcx(width, height, pattern=0, runs=True):
    header = bytearray(128)
    header[:4] = bytes((10, 5, 1, 1))
    struct.pack_into("<6H", header, 4, 0, 0, width - 1, height - 1, 640, 350)
    header[16:64] = PALETTE
    header[65] = 4
    struct.pack_into("<HH", header, 66, width // 8, 1)
    data = bytearray()
    if runs:
        remaining = width // 8 * height * 4
        while remaining:
            size = min(63, remaining)
            data.extend((0xC0 | size, pattern))
            remaining -= size
    else:
        for i in range(width // 8 * height * 4):
            value = 1 + i % 190
            data.append(value)
    return bytes(header) + data


def load(v, data):
    v.disk["UNIT.PCX"] = data
    return v.invoke(
        "LoadPcx", v.string_arg("UNIT.PCX"), instructions=500_000_000, seconds=60
    )


def cases(module):
    if module != "RSPACK":
        return

    def padded_font(v):
        v.fixture()
        header = bytearray(pcx(128, 120)[:128])
        struct.pack_into("<H", header, 66, 18)
        ready(v, load(v, bytes(header) + (bytes(16) + bytes((17, 34))) * 4 * 120))
        ready(v, v.invoke("PackFont"))
        assert v.disk["KB2.FNT"] == bytes(1920)
        ready(v, v.invoke("FreeImage"))

    yield Case("font.ignores-pcx-scanline-padding", padded_font)

    def mixed_screen(v):
        v.fixture()
        remaining = 111999
        payload = bytearray()
        while remaining:
            size = min(remaining, 63)
            payload.extend((192 | size, 0))
            remaining -= size
        payload.append(1)
        ready(v, load(v, pcx(640, 350)[:128] + payload))
        ready(
            v,
            v.invoke(
                "PackScreen", v.string_arg("UNIT"), instructions=200_000_000, seconds=30
            ),
        )
        expected = struct.pack("<H", 4) + b"\x00" + struct.pack("<H", 27999) + b"\x01"
        expected += (struct.pack("<H", 3) + b"\x00" + struct.pack("<H", 28000)) * 3
        assert v.disk["UNIT.PIC"] == expected
        ready(v, v.invoke("FreeImage"))

    yield Case("screen.compressed-literal-tail", mixed_screen)
    for text, wanted, rest in (
        ("", "", ""),
        ("   ", "", ""),
        ("ARMY", "ARMY", ""),
        ("  T ARMY0 15", "T", "ARMY0 15"),
        ("T  A", "T", " A"),
    ):

        def token(v, text=text, wanted=wanted, rest=rest):
            v.fixture()
            p = v.string_arg(text)
            assert ready(v, v.invoke("Token", p)) == wanted
            address = linear(p)
            size = v.read(address, 1)[0]
            assert v.read(address + 1, size).decode("cp866") == rest

        yield Case("token." + repr(text), token)
    for size in (0, 1, 4095, 4096, 4097, 8192):

        def output(v, size=size):
            v.fixture()
            ready(v, v.invoke("OpenOutput", v.string_arg("UNIT.BIN")))
            for i in range(size):
                ready(v, v.invoke("PutByte", i % 256))
            ready(v, v.invoke("CloseOutput"))
            assert v.disk["UNIT.BIN"] == bytes(i % 256 for i in range(size))

        yield Case(f"output.byte-stream.{size}", output)

    def words(v):
        v.fixture()
        ready(v, v.invoke("OpenOutput", v.string_arg("UNIT.BIN")))
        for word in (0, 1, 255, 256, 65535):
            ready(v, v.invoke("PutWord", word))
        ready(v, v.invoke("CloseOutput"))
        assert v.disk["UNIT.BIN"] == struct.pack("<5H", 0, 1, 255, 256, 65535)

    yield Case("output.words-little-endian", words)
    for value in (0, 255):

        def screen(v, value=value):
            v.fixture()
            ready(v, load(v, pcx(640, 350, value)))
            ready(
                v,
                v.invoke(
                    "PackScreen",
                    v.string_arg("UNIT"),
                    instructions=50_000_000,
                    seconds=15,
                ),
            )
            assert (
                v.disk["UNIT.PIC"]
                == (struct.pack("<H", 3) + bytes([value]) + struct.pack("<H", 28000))
                * 4
            )
            ready(v, v.invoke("FreeImage"))

        yield Case(f"screen.solid.{value}", screen)

    def raw_screen(v):
        v.fixture()
        ready(v, load(v, pcx(640, 350, runs=False)))
        ready(
            v,
            v.invoke(
                "PackScreen", v.string_arg("UNIT"), instructions=500_000_000, seconds=60
            ),
        )
        expected = b"".join(
            struct.pack("<H", 28000)
            + bytes(
                1 + ((y * 4 + 3 - p) * 80 + x) % 190
                for y in range(350)
                for x in range(80)
            )
            for p in range(4)
        )
        assert v.disk["UNIT.PIC"] == expected
        ready(v, v.invoke("FreeImage"))

    yield Case("screen.raw-planar", raw_screen)
    for count in (1, 4, 5, 15):

        def tiles(v, count=count):
            v.fixture()
            ready(v, load(v, pcx(384, ((count + 3) // 4) * 60)))
            ready(
                v,
                v.invoke(
                    "PackTiles",
                    v.string_arg("UNIT"),
                    count,
                    instructions=50_000_000,
                    seconds=15,
                ),
            )
            assert v.disk["UNIT.PIC"] == bytes(count * 2880)
            ready(v, v.invoke("FreeImage"))

        yield Case(f"tiles.{count}", tiles)

    def font(v):
        v.fixture()
        ready(v, load(v, pcx(128, 120)))
        ready(v, v.invoke("PackFont"))
        assert v.disk["KB2.FNT"] == bytes(1920)
        ready(v, v.invoke("FreeImage"))

    yield Case("font.black-bitmap", font)
    changes = {
        "manufacturer": (0, 9),
        "encoding": (2, 0),
        "bpp": (3, 8),
        "planes": (65, 1),
        "width-order": (8, 0),
        "height-order": (10, 0),
        "width-limit": (9, 255),
        "stride-small": (66, 0),
        "stride-large": (67, 255),
        "palette": (16, 1),
    }
    for name, (offset, value) in changes.items():

        def reject(v, offset=offset, value=value, name=name):
            v.fixture()
            data = bytearray(pcx(8, 8))
            if name == "width-order":
                struct.pack_into("<H", data, 4, 1)
            if name == "height-order":
                struct.pack_into("<H", data, 6, 1)
            data[offset] = value
            result = load(v, bytes(data))
            assert result[1] == {"kind": "exit", "code": 1}, result
            assert "ERROR:" in v.output

        yield Case("reject.header." + name, reject)
    for name, pixels in (("zero-run", b"\xc0\x00"), ("truncated", b"")):

        def reject_data(v, pixels=pixels):
            v.fixture()
            result = load(v, pcx(8, 1)[:128] + pixels)
            assert result[1] == {"kind": "exit", "code": 1}, result
            assert "ERROR:" in v.output

        yield Case("reject.pixels." + name, reject_data)
    for name, suffix in (
        ("run-overflow", b"\xc5\x00"),
        ("trailing-data", b"\xc4\x00X"),
    ):

        def reject_tail(v, suffix=suffix):
            v.fixture()
            result = load(v, pcx(8, 1)[:128] + suffix)
            assert result[1] == {"kind": "exit", "code": 1}, result

        yield Case("reject.tail." + name, reject_tail)
    for routine, args in (
        ("PackScreen", ["UNIT"]),
        ("PackTiles", ["UNIT", 0]),
        ("PackTiles", ["UNIT", 1]),
        ("PackFont", []),
    ):

        def dimensions(v, routine=routine, args=args):
            v.fixture()
            ready(v, load(v, pcx(8, 8)))
            values = [v.string_arg(a) if isinstance(a, str) else a for a in args]
            result = v.invoke(routine, *values)
            assert result[1] == {"kind": "exit", "code": 1}, result

        yield Case("reject.dimensions." + routine + str(args), dimensions)

    def colored_font(v):
        v.fixture()
        data = pcx(128, 120, runs=False)
        ready(v, load(v, data))
        result = v.invoke("PackFont")
        assert result[1] == {"kind": "exit", "code": 1}, result

    yield Case("reject.font.colors", colored_font)
    for name, text, width, height in (
        ("empty", "", 8, 8),
        ("blank", "\r\n", 8, 8),
        ("bad-count", "T UNIT bad\r\n", 8, 8),
        ("bad-kind", "Q UNIT 1\r\n", 8, 8),
        ("tiles", "T UNIT 1\r\n", 384, 60),
        ("font", "F UNIT 0\r\n", 128, 120),
        ("screen", "S UNIT 0\r\n", 640, 350),
    ):

        def program(v, name=name, text=text, width=width, height=height):
            v.fixture()
            v.disk["PACK.LST"] = text.encode("ascii")
            v.disk["UNIT.PCX"] = pcx(width, height)
            result = v.invoke("UMain", instructions=200_000_000, seconds=40)
            if name.startswith("bad-"):
                assert result[1] == {"kind": "exit", "code": 1}, result
            else:
                ready(v, result)
                assert "Resources built." in v.output
                output = {
                    "tiles": ("UNIT.PIC", 2880),
                    "font": ("KB2.FNT", 1920),
                    "screen": ("UNIT.PIC", 20),
                }.get(name)
                if output:
                    assert len(v.disk[output[0]]) == output[1]

        yield Case("program.list." + name, program)
