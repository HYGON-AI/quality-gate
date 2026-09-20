# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Conservative comment-header recognition, not an originality classifier.

Reference notice texts: SPDX license-list-data text/MIT.txt, BSD-3-Clause.txt;
Apache-2.0 appendix (also included in this repository's LICENSE).
Unknown/partial variants are deliberately not inferred from a license name.
"""
import re
from typing import List, Tuple


MIT_NOTICE = '''Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.'''

BSD_NOTICE = '''Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
this list of conditions and the following disclaimer in the documentation
and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
may be used to endorse or promote products derived from this software without
specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.'''

APACHE_NOTICE = '''Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.'''

TRADITIONAL_NOTICES = {'MIT': MIT_NOTICE, 'BSD-3-Clause': BSD_NOTICE, 'Apache-2.0': APACHE_NOTICE}
COPYRIGHT_START = re.compile(r'^(?:portions\s+)?copyright\b', re.I)
BOUNDARY = re.compile(
    r'^(?:(?:portions\s+)?copyright\b|SPDX-License-Identifier:|Modified by\b|'
    r'All rights reserved\b|Licensed\b|Permission\b|Redistribution\b|'
    r'THE SOFTWARE\b|THIS SOFTWARE\b|MIT License\b|BSD|Apache|This file\b|See\b)', re.I)


def normalize(text: str) -> str:
    """Whitespace only: never discard names, punctuation, years or clauses."""
    return ' '.join(text.split())


def comment_header(text: str, limit: int) -> str:
    """Extract comment text with original line positions; ignore code literals.

    Supports line comments, C blocks and standalone triple-quoted headers.
    Executable lines and blank lines separate declarations. This intentionally
    does not attempt to parse arbitrary language-specific string syntax.
    """
    result: List[str] = []
    closing = None
    for raw in text.splitlines()[:limit]:
        line = raw.strip().lstrip('\ufeff')
        if closing:
            content, sep, _ = line.partition(closing)
            if sep:
                closing = None
            if line.startswith('*'):
                content = re.sub(r'^\* ?', '', content)
        elif line.startswith(('/*', '<!--', '"""', "'''")):
            opener = next(p for p in ('/*', '<!--', '"""', "'''") if line.startswith(p))
            end = {'/*': '*/', '<!--': '-->'}.get(opener, opener)
            content, sep, _ = line[len(opener):].partition(end)
            closing = None if sep else end
        else:
            match = re.match(r'^(?:\#+|//+|;+|--)\s?(.*)$', line)
            content = match.group(1) if match else ''
        result.append(content.strip())
    return '\n'.join(result)


def declarations(header: str) -> List[str]:
    """Copyright paragraphs (including wrapped holders) and SPDX statements."""
    lines = header.splitlines()
    result = []
    for index, line in enumerate(lines):
        if COPYRIGHT_START.match(line):
            parts = [line]
            for following in lines[index + 1:]:
                if not following or BOUNDARY.match(following):
                    break
                # A completed sentence normally ends an attribution paragraph.
                if parts[-1].endswith('.'):
                    break
                parts.append(following)
            result.append(normalize(' '.join(parts)))
    for match in re.finditer(r'^SPDX-License-Identifier:\s*([^\n]+)', header, re.M | re.I):
        result.append('SPDX-License-Identifier: ' + normalize(match.group(1)))
    return result


def contains_declaration(header: str, original: str) -> bool:
    # Whitespace-bounded comparison avoids matching "Owner" inside "OwnerTwo".
    return ' ' + normalize(original) + ' ' in ' ' + normalize(header) + ' '


def _notice_text(header: str) -> str:
    # BSD commonly uses bullets instead of numbered conditions. Retain all
    # clause words/order; normalize only those three known list prefixes.
    header = normalize(header)
    for prefix in ('Redistributions of source code', 'Redistributions in binary form', 'Neither the name'):
        header = re.sub(r'(?<!\S)(?:[1-3][.)]|[*-])\s+(' + prefix + ')', r'\1', header)
    return normalize(header)


def traditional_notices(header: str) -> List[Tuple[str, str]]:
    """Return only complete recognized bodies, never a keyword-only match."""
    candidate = _notice_text(header)
    found = []
    for license_id, body in TRADITIONAL_NOTICES.items():
        pattern = re.escape(_notice_text(body))
        if license_id == 'Apache-2.0':
            pattern = pattern.replace('http://', 'https?://')
        for match in re.finditer(pattern, candidate, re.I):
            found.append((license_id, match.group()))
    return found


def preserves_traditional(header: str, original_body: str) -> bool:
    return _notice_text(original_body).casefold() in _notice_text(header).casefold()
