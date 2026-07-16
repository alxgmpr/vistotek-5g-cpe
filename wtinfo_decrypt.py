#!/usr/bin/env python3
"""Decrypt a Wingtech 'wtinfo' factory blob (WTINFO0001 / wtinfo-des-v1).
Layout:  0x00 "WTINFO" | 0x06 "0001" | 0x0A mac[6] | 0x10 md5-ish[16] | 0x20 DES-CBC(json)
Cipher:  single DES-CBC, zero IV, key = DES_string_to_key("wtinfo-des-v1").
Usage:   python3 wtinfo_decrypt.py <flash_dump> [wtinfo_offset=0x310000]
"""
import ctypes, sys
LIBCRYPTO = "/opt/homebrew/opt/openssl@3/lib/libcrypto.dylib"
def decrypt(blob):
    lib = ctypes.CDLL(LIBCRYPTO)
    key = (ctypes.c_ubyte*8)()
    lib.DES_string_to_key(b"wtinfo-des-v1", ctypes.byref(key))
    sched = (ctypes.c_ubyte*128)()
    lib.DES_set_key_unchecked(ctypes.byref(key), ctypes.byref(sched))
    ct = blob[0x20:]; n = len(ct)-(len(ct)%8)
    out = (ctypes.c_ubyte*n)(); inp=(ctypes.c_ubyte*n).from_buffer_copy(ct[:n])
    iv=(ctypes.c_ubyte*8)()
    lib.DES_ncbc_encrypt(ctypes.byref(inp),ctypes.byref(out),ctypes.c_long(n),
                         ctypes.byref(sched),ctypes.byref(iv),0)
    pt=bytes(out); return pt[:pt.find(b'\x00')] if b'\x00' in pt else pt
if __name__=="__main__":
    off=int(sys.argv[2],0) if len(sys.argv)>2 else 0x310000
    d=open(sys.argv[1],"rb").read()[off:off+0x10000]
    assert d[:6]==b"WTINFO", "not a WTINFO blob"
    print("mac (plaintext hdr):", ":".join("%02X"%b for b in d[0x0A:0x10]))
    print("decrypted:", decrypt(d).decode("latin1"))
