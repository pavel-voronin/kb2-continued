"""EGA planar memory adapter for isolated graphics routines."""

import unicorn as uc
from unicorn.x86_const import UC_X86_INS_IN, UC_X86_INS_OUT


class Ega:
    def __init__(self, vm):
        self.vm = vm
        self.reset()
        vm.cpu.hook_add(uc.UC_HOOK_MEM_READ, self.read, None, 0xA0000, 0xAFFFF)
        vm.cpu.hook_add(uc.UC_HOOK_MEM_WRITE, self.write, None, 0xA0000, 0xAFFFF)
        vm.cpu.hook_add(uc.UC_HOOK_INSN, self.input, None, 1, 0, UC_X86_INS_IN)
        vm.cpu.hook_add(uc.UC_HOOK_INSN, self.output, None, 1, 0, UC_X86_INS_OUT)

    def reset(self):
        self.planes = [bytearray(65536) for _ in range(4)]
        self.latch = [0] * 4
        self.seq = [0] * 8
        self.seq[2] = 15
        self.gc = [0] * 16
        self.gc[8] = 255
        self.seq_index = self.gc_index = 0
        self.port_log = []

    def output(self, cpu, port, size, value, user):
        self.port_log.append((port, size, value))
        for offset in range(size):
            p = port + offset
            v = (value >> (offset * 8)) & 255
            if p == 0x3C4:
                self.seq_index = v & 7
            elif p == 0x3C5:
                self.seq[self.seq_index] = v
            elif p == 0x3CE:
                self.gc_index = v & 15
            elif p == 0x3CF:
                self.gc[self.gc_index] = v

    def input(self, cpu, port, size, user):
        if port == 0x3C5:
            return self.seq[self.seq_index]
        if port == 0x3CF:
            return self.gc[self.gc_index]
        return 0

    def read(self, cpu, access, address, size, value, user):
        output = bytearray()
        for i in range(size):
            offset = (address + i - 0xA0000) & 65535
            self.latch = [p[offset] for p in self.planes]
            if self.gc[5] & 8:
                result = 255
                for plane in range(4):
                    if self.gc[7] & (1 << plane):
                        result &= (
                            self.latch[plane]
                            if self.gc[2] & (1 << plane)
                            else self.latch[plane] ^ 255
                        )
            else:
                result = self.latch[self.gc[4] & 3]
            output.append(result)
        cpu.mem_write(address, bytes(output))

    def write(self, cpu, access, address, size, value, user):
        mode = self.gc[5] & 3
        for i in range(size):
            offset = (address + i - 0xA0000) & 65535
            data = (value >> (i * 8)) & 255
            rotation = self.gc[3] & 7
            rotated = ((data >> rotation) | (data << (8 - rotation))) & 255
            for plane in range(4):
                if not self.seq[2] & (1 << plane):
                    continue
                mask = self.gc[8]
                if mode == 1:
                    self.planes[plane][offset] = self.latch[plane]
                    continue
                if mode == 2:
                    source = 255 if data & (1 << plane) else 0
                elif mode == 3:
                    source = 255 if self.gc[0] & (1 << plane) else 0
                    mask &= rotated
                else:
                    source = (
                        (255 if self.gc[0] & (1 << plane) else 0)
                        if self.gc[1] & (1 << plane)
                        else rotated
                    )
                operation = (self.gc[3] >> 3) & 3
                if operation == 1:
                    source &= self.latch[plane]
                elif operation == 2:
                    source |= self.latch[plane]
                elif operation == 3:
                    source ^= self.latch[plane]
                self.planes[plane][offset] = (source & mask) | (
                    self.latch[plane] & (mask ^ 255)
                )

    def snapshot(self):
        return b"".join(self.planes)

    def pixel(self, x, y, page=0):
        offset = page + y * 80 + x // 8
        mask = 0x80 >> (x % 8)
        return sum(1 << i for i, p in enumerate(self.planes) if p[offset] & mask)
