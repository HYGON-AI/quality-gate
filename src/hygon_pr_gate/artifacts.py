# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Recognize compiled formats by content, not a caller-controlled suffix."""


def review_artifact_format(path, data):
    """Recognize bounded headers, NOT validate or execute archive contents.

    Suffix alone never exempts text. Legacy pickle checkpoints deliberately
    remain unsupported: never deserialize untrusted PR data.
    """
    name = path.lower()
    if not data:
        return None
    if name.endswith('.pt') and len(data) >= 30 and data.startswith(b'PK\x03\x04'):
        return 'ZIP 格式 .pt 制品'
    if name.endswith('.tgz') and len(data) >= 10 and data[:3] == b'\x1f\x8b\x08' and not data[3] & 0xe0:
        return 'gzip 格式 .tgz 归档'
    if name.endswith('.tar') and len(data) >= 512 and data[257:263] in (b'ustar\0', b'ustar '):
        header = data[:512]
        try:
            expected = int(header[148:156].strip(b'\0 '), 8)
        except ValueError:
            return None
        if expected == sum(header[:148]) + 8 * 32 + sum(header[156:]):
            return 'tar 归档'
    return None


def compiled_format(data):
    if not data:
        return None
    if data.startswith(b'\x7fELF'):
        return 'ELF 编译产物（共享库、目标文件或可执行文件）'
    if data.startswith((b'BC\xc0\xde', b'\xde\xc0\x17\x0b')):
        return 'LLVM bitcode 编译产物'
    if data.startswith(b'!<arch>\n'):
        return '静态库归档'
    if data.startswith((b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe')):
        return 'Mach-O 编译产物'
    return None
