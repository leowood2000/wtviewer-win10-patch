import hashlib
import struct
import sys
from pathlib import Path


source, destination = map(Path, sys.argv[1:3])
data = bytearray(source.read_bytes())
assert hashlib.sha256(data).hexdigest() == 'ebc1ce26fb83a6c781d2d37e6acc862376e5ee26e1da1b67055f6e4de6f15c11', 'unsupported WtViewer.exe build'
nt, = struct.unpack_from('<I', data, 0x3c)
section_count, = struct.unpack_from('<H', data, nt + 6)
optional_size, = struct.unpack_from('<H', data, nt + 20)
section_table = nt + 24 + optional_size
base, = struct.unpack_from('<I', data, nt + 24 + 28)
sections = [struct.unpack_from('<8sIIII', data, section_table + i * 40) for i in range(section_count)]


def offset(rva):
    return next(raw + rva - start for _, _, start, size, raw in sections if start <= rva < start + size)


# getARange (VA 0x158c6f0) computes the current display range. For internal
# model enum 5/6 with range index < 6 it multiplies the table value by 0.01
# (fmul qword ptr [0x1624a48]) to scale external current sensor inputs.
# A WT210 (IDN product code 760401) is classified as model 6 although it uses
# direct current inputs, shrinking the amperage axis by 100x. Remove the
# multiply: 6 bytes of NOP. The other model branches never execute it.
rva = 0x158c975 - base
pos = offset(rva)
expected = bytes.fromhex('dc0d484a6201')
assert bytes(data[pos:pos + 6]) == expected, 'unexpected bytes at patch site'
data[pos:pos + 6] = b'\x90' * 6
destination.write_bytes(data)
print(f'{destination} | sha256 {hashlib.sha256(data).hexdigest()}')
