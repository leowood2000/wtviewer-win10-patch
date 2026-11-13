import hashlib
import struct
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent / 'diagnostics-python'))
from keystone import Ks, KS_ARCH_X86, KS_MODE_32


source, destination = map(Path, sys.argv[1:3])
data = bytearray(source.read_bytes())
assert hashlib.sha256(data).hexdigest() == '5bc57668140e6d075acdbab12f2a979594b5b5aa5d173b948745d2bcb2bbfd01'
nt, = struct.unpack_from('<I', data, 0x3c)
section_count, = struct.unpack_from('<H', data, nt + 6)
optional_size, = struct.unpack_from('<H', data, nt + 20)
optional = nt + 24
section_table = optional + optional_size
base, section_alignment, file_alignment = struct.unpack_from('<III', data, optional+28)
header_size, = struct.unpack_from('<I', data, optional+60)
sections = [struct.unpack_from('<8sIIII', data, section_table+i*40) for i in range(section_count)]


def align(value, quantum):
    return (value + quantum - 1) // quantum * quantum


def offset(rva):
    return next(raw+rva-start for _, _, start, size, raw in sections if start <= rva < start+size)


patch_rva = align(max(rva+max(virtual_size, raw_size) for _,virtual_size,rva,raw_size,_ in sections),section_alignment)
location = base + patch_rva
# Cache complete blocks per TMCTL session (128 slots). Normal WT210/230 and
# harmonic responses fit in 16 KiB. A full scratch buffer or malformed block fails.
cache_rva = align(patch_rva + 0x1000, section_alignment)
cache_size = 128 * 0x4010
asm = f'''
    call header_base
header_base:
    pop eax
    sub eax, {patch_rva+5}
    lea edx, [eax+0x3f89c]
    cmp [ecx], edx
    jne header_original
    push ebx
    push esi
    push edi
    push ebp
    mov esi, ecx
    mov ebp, [esp+20]
    mov ebx, 128
    lea edi, [eax+{cache_rva}]
header_slot:
    cmp dword ptr [edi], esi
    je header_found
    xor eax, eax
    lock cmpxchg dword ptr [edi], esi
    je header_found
    add edi, 0x4010
    dec ebx
    jnz header_slot
    jmp header_error
header_found:
    mov dword ptr [edi+4], 0
    mov dword ptr [esi+0x24], 0
    push dword ptr [esi+0x10]
    mov dword ptr [esi+0x10], 3
    sub esp, 4
    mov dword ptr [esp], 0
    lea edx, [esp]
    lea ebx, [edi+16]
    push edx
    push 16384
    push ebx
    mov ecx, esi
    call {base+0x11840}
    pop ecx
    pop edx
    mov [esi+0x10], edx
    test eax, eax
    jne header_error
    cmp ecx, 3
    jb header_error
    cmp ecx, 16384
    jae header_error
    cmp byte ptr [ebx], 35
    jne header_error
    movzx edx, byte ptr [ebx+1]
    sub edx, 49
    cmp edx, 8
    ja header_error
    inc edx
    sub ecx, 2
    cmp ecx, edx
    jb header_error
    sub ecx, edx
    push ecx
    add ebx, 2
    xor eax, eax
digits:
    movzx ecx, byte ptr [ebx]
    sub ecx, 48
    cmp ecx, 9
    ja digits_error
    imul eax, eax, 10
    add eax, ecx
    inc ebx
    dec edx
    jnz digits
    pop ecx
    cmp eax, ecx
    ja header_error
    test eax, eax
    je header_empty
    mov [edi+4], eax
    mov [edi+8], ebx
    mov [ebp], eax
    xor eax, eax
    jmp header_finish
header_empty:
    mov dword ptr [edi], 0
    mov [ebp], eax
    jmp header_finish
digits_error:
    pop ecx
header_error:
    test ebx, ebx
    jz no_slot
    mov dword ptr [edi], 0
no_slot:
    mov dword ptr [ebp], 0
    mov dword ptr [esi+0x20], 0x400
    mov eax, 1
header_finish:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret 4
header_original:
    sub esp, 0x84
    jmp {base+0x143f6}
'''
assembler = Ks(KS_ARCH_X86, KS_MODE_32)
header, _ = assembler.asm(asm, location, as_bytes=True)
payload_rva = patch_rva + len(header)
payload, _ = assembler.asm(f'''
    call payload_base
payload_base:
    pop eax
    sub eax, {payload_rva+5}
    lea edx, [eax+0x3f89c]
    cmp [ecx], edx
    jne payload_original
    push ebx
    push esi
    push edi
    push ebp
    mov ebx, 128
    lea ebp, [eax+{cache_rva}]
payload_slot:
    cmp [ebp], ecx
    je payload_found
    add ebp, 0x4010
    dec ebx
    jnz payload_slot
    pop ebp
    pop edi
    pop esi
    pop ebx
    jmp payload_original
payload_found:
    mov ecx, [esp+24]
    mov eax, [ebp+4]
    cmp ecx, eax
    cmova ecx, eax
    mov edi, [esp+20]
    mov esi, [ebp+8]
    mov eax, [esp+32]
    mov [eax], ecx
    sub [ebp+4], ecx
    rep movsb
    mov [ebp+8], esi
    mov edx, [esp+28]
    xor eax, eax
    cmp [ebp+4], eax
    sete al
    mov [edx], eax
    test eax, eax
    je payload_finish
    mov dword ptr [ebp], 0
payload_finish:
    pop ebp
    pop edi
    pop esi
    pop ebx
    xor eax, eax
    ret 16
payload_original:
    mov eax, [esp+16]
    push ebx
    jmp {base+0x14535}
''', base+payload_rva, as_bytes=True)
code = header + payload
assert len(code) < 0x1000

for hook, target, original in [
    (0x143f0, patch_rva, '81ec84000000'),
    (0x14530, payload_rva, '8b44241053'),
]:
    expected = bytes.fromhex(original)
    start = offset(hook)
    assert data[start:start+len(expected)] == expected
    redirect, _ = assembler.asm(f'jmp {base+target}', base+hook, as_bytes=True)
    data[start:start+len(expected)] = redirect.ljust(len(expected), b'\x90')

new_header = section_table+section_count*40
assert new_header+80 <= header_size
new_offset = align(len(data), file_alignment)
raw_size = align(len(code), file_alignment)
data.extend(b'\x00' * (new_offset-len(data)))
data.extend(code.ljust(raw_size, b'\x00'))
struct.pack_into('<8sIIIIIIHHI', data, new_header, b'.wtfix',len(code),patch_rva,raw_size,new_offset,0,0,0,0,0x60000020)
struct.pack_into('<8sIIIIIIHHI', data, new_header+40, b'.wtbuf',cache_size,cache_rva,0,0,0,0,0,0,0xc0000080)
struct.pack_into('<H', data, nt+6, section_count+2)
size_code, size_initialized, size_uninitialized = struct.unpack_from('<III', data, optional+4)
struct.pack_into('<III', data, optional+4, size_code+raw_size,size_initialized,size_uninitialized+cache_size)
struct.pack_into('<I', data, optional+56, align(cache_rva+cache_size,section_alignment))
struct.pack_into('<I', data, optional+64, 0)
destination.write_bytes(data)
print(f'{destination} | entry RVA {patch_rva:#x} | sha256 {hashlib.sha256(data).hexdigest()}')
