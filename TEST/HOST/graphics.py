"""Pixel and memory oracles for the original assembly drawing routines."""

from cases import Case, ready
from runtime import linear
import struct


def cases(module):
    if module != "KBGFX":
        return
    for raw in (False, True):

        def screen(v, raw=raw):
            g = v.fixture()
            name = b"UNIT.PIC"
            g.Runtime.PictureFileName[:] = (
                bytes([len(name)])
                + name
                + bytes(len(g.Runtime.PictureFileName) - len(name) - 1)
            )
            v.set_game(g)
            if raw:
                v.disk["UNIT.PIC"] = b"".join(
                    struct.pack("<H", 28000) + bytes([p + 1]) * 28000 for p in range(4)
                )
            else:
                v.disk["UNIT.PIC"] = (
                    (struct.pack("<H", 3) + b"\x00" + struct.pack("<H", 28000)) * 3
                    + struct.pack("<H", 4)
                    + b"\x00"
                    + struct.pack("<H", 27999)
                    + b"\x04"
                )
            ready(
                v, v.invoke("LoadScreenPicture", instructions=120_000_000, seconds=15)
            )
            for plane in range(4):
                wanted = (
                    bytes([4 - plane]) * 28000
                    if raw
                    else bytes(27999) + bytes([4 if plane == 0 else 0])
                )
                assert v.ega.planes[plane][:28000] == wanted

        yield Case(f"screen.raw-{raw}.literal-tail", screen)

    def invalid_file_handle(v):
        g = v.fixture()
        name = b"UNIT.PIC"
        g.Runtime.PictureFileName[:] = (
            bytes([len(name)])
            + name
            + bytes(len(g.Runtime.PictureFileName) - len(name) - 1)
        )
        v.set_game(g)
        v.disk["UNIT.PIC"] = (
            struct.pack("<H", 4) + b"\x00" + struct.pack("<H", 27999) + b"\x01"
        ) * 4
        try:
            v.invoke("LoadScreenPicture", instructions=120_000_000, seconds=15)
        except KeyError as error:
            assert (
                error.args == (0xFF05,)
                and v.r("bx") == 0xFF05
                and v.r("ax") >> 8 == 0x3F
            ), error
            assert 5 in v.files and 0xFF05 not in v.files
        else:
            raise AssertionError("Expected BH to corrupt the next DOS file handle")

    yield Case("B018.literal-tail-corrupts-next-plane-file-handle", invalid_file_handle)
    for mask in (1, 2, 4, 8):

        def masked(v, mask=mask):
            g = v.fixture()
            v.cpu.mem_write(linear(g.Runtime.PictureBanks[0]), bytes(2880))
            for plane in v.ega.planes:
                plane[:] = b"\x55" * 65536
            ready(v, v.invoke("DrawMaskedTile", 802, 0, mask))
            for p in range(4):
                for y in range(60):
                    assert (
                        v.ega.planes[p][802 + y * 80 : 814 + y * 80]
                        == bytes([255 if mask & (1 << p) else 85]) * 12
                    )

        yield Case(f"masked-tile.plane-{mask}", masked)
    for highlighted in (False, True):

        def text(v, highlighted=highlighted):
            g = v.fixture()
            g.Runtime.Font[65][:] = bytes((128, 64, 32, 16, 8, 4, 2, 1))
            v.set_game(g)
            ready(v, v.invoke("DrawText", highlighted, 2, 3, v.string_arg("AA")))
            for plane in range(4):
                for row in range(8):
                    for col in (2, 3):
                        assert v.ega.planes[plane][(3 + row) * 80 + col] == (
                            255 if highlighted and plane == 2 else 128 >> row
                        )

        yield Case(f"text.glyph.highlighted-{highlighted}", text)
    for mask in range(16):

        def planes(v, mask=mask):
            g = v.fixture()
            source = b"".join(bytes([31 * (p + 1)]) * 720 for p in range(4))
            v.cpu.mem_write(linear(g.Runtime.PictureBanks[0]), source)
            for p in v.ega.planes:
                p[:] = b"\xff" * 65536
            ready(v, v.invoke("DrawPicturePlanes", 802, 0, mask))
            for plane in range(4):
                assert (
                    v.ega.planes[plane][802:814]
                    == bytes([31 * (4 - plane) if mask & (1 << plane) else 255]) * 12
                )
            ready(v, v.invoke("ClearPicturePlanes", 802, mask))
            for plane in range(4):
                assert (
                    v.ega.planes[plane][802:814]
                    == bytes([0 if mask & (1 << plane) else 255]) * 12
                )

        yield Case(f"planes.select-mask-{mask}", planes)

    def transparent(v):
        g = v.fixture()
        address = linear(g.Runtime.PictureBanks[0])
        terrain = b"".join(
            bytes([255 if 4 & (1 << (3 - p)) else 0]) * 720 for p in range(4)
        )
        sprite = bytearray(2880)
        for p in range(4):
            for y in range(60):
                for x in range(96):
                    if (x % 16) & (1 << (3 - p)):
                        sprite[p * 720 + y * 12 + x // 8] |= 128 >> (x % 8)
        v.cpu.mem_write(address, terrain + bytes(sprite))
        ready(v, v.invoke("DrawTile", 802, 0, 1))
        for y in range(10, 70):
            for x in range(16, 112):
                color = (x - 16) % 16
                assert v.ega.pixel(x, y) == (4 if color == 10 else color), (
                    x,
                    y,
                    v.ega.pixel(x, y),
                )

    yield Case("tile.transparent-color-ten", transparent)
    for color in range(16):
        for coordinates in (
            (1, 1, 3, 1),
            (1, 1, 1, 3),
            (7, 2, 9, 2),
            (19, 3, 2, 3),
            (4, 5, 4, 2),
            (8, 1, 8, 1),
            (8, 2, 17, 2),
        ):

            def line(v, color=color, coordinates=coordinates):
                v.fixture()
                for plane in v.ega.planes:
                    plane[:] = b"\xff" * 65536
                ready(v, v.invoke("DrawLine", *coordinates, color))
                x1, y1, x2, y2 = coordinates
                x1, x2 = sorted((x1, x2))
                y1, y2 = sorted((y1, y2))
                for y in range(max(0, y1 - 1), y2 + 2):
                    for x in range(max(0, x1 - 1), x2 + 2):
                        wanted = color if x1 <= x <= x2 and y1 <= y <= y2 else 15
                        assert v.ega.pixel(x, y) == wanted, (
                            coordinates,
                            color,
                            x,
                            y,
                            wanted,
                            v.ega.pixel(x, y),
                        )

            yield Case(f"line.{color}." + ".".join(map(str, coordinates)), line)
    for width in (0, 1, 15, 16, 17, 31, 32, 48):

        def clear(v, width=width):
            v.fixture()
            for plane in v.ega.planes:
                plane[:] = b"\xff" * 65536
            ready(v, v.invoke("ClearRectangle", 8, 2, 8 + width, 4))
            end = 8 + (width // 16) * 16
            for y in range(1, 6):
                for x in range(0, 64):
                    assert v.ega.pixel(x, y) == (
                        0 if 2 <= y <= 4 and 8 <= x < end else 15
                    )

        yield Case(f"clear.quantized-width.{width}", clear)
    for picture in (0, 1, 15, 16, 96, 160, 224):

        def portrait(v, picture=picture):
            g = v.fixture()
            bank = picture >> 4
            index = picture & 15
            address = linear(g.Runtime.PictureBanks[bank]) + index * 2880
            source = b"".join(bytes([31 * (i + 1)]) * 720 for i in range(4))
            v.cpu.mem_write(address, source)
            ready(v, v.invoke("DrawPictureTile", 802, picture))
            for p in range(4):
                for y in range(60):
                    assert (
                        v.ega.planes[3 - p][802 + y * 80 : 814 + y * 80]
                        == bytes([31 * (p + 1)]) * 12
                    )

        yield Case(f"portrait.{picture}", portrait)
    for picture in (0, 1, 15, 16, 96):

        def mirror(v, picture=picture):
            g = v.fixture()
            address = (
                linear(g.Runtime.PictureBanks[picture >> 4]) + (picture & 15) * 2880
            )
            raw = bytes(i % 251 for i in range(2880))
            v.cpu.mem_write(address, raw)
            ready(v, v.invoke("MirrorTileArt", picture))
            expected = b"".join(
                bytes(int(f"{b:08b}"[::-1], 2) for b in raw[i : i + 12][::-1])
                for i in range(0, 2880, 12)
            )
            assert v.read(address, 2880) == expected
            ready(v, v.invoke("MirrorTileArt", picture))
            assert v.read(address, 2880) == raw

        yield Case(f"mirror.involution.{picture}", mirror)
    for packet in range(5):

        def store(v, packet=packet):
            g = v.fixture()
            text = b"ARMY5.PIC"
            g.Runtime.ReservePictureFileName[:] = (
                bytes([len(text)])
                + text
                + bytes(len(g.Runtime.ReservePictureFileName) - len(text) - 1)
            )
            v.set_game(g)
            v.disk["ARMY5.PIC"] = b"\xaa" * 43200
            source = bytearray(i % 251 for i in range(8640))
            address = linear(g.Runtime.PictureBanks[10])
            v.cpu.mem_write(address, bytes(source))
            source[2160:2880] = bytes(720)
            ready(v, v.invoke("StoreMutantFrames", packet, 0))
            expected = (
                b"\xaa" * (packet * 8640)
                + bytes(source)
                + b"\xaa" * ((4 - packet) * 8640)
            )
            assert v.disk["ARMY5.PIC"] == expected

        yield Case(f"store-mutant.packet.{packet}", store)
