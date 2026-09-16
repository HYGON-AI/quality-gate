# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Recognize compiled formats by content, not a caller-controlled suffix."""


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
