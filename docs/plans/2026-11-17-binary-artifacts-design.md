# Bounded binary-artifact handling

User approved: pin self-test OS for Python 3.9; recognize .pt ZIP,
.tar (ustar header with checksum), and .tgz gzip headers only when suffix
matches. Emit an explicit advisory requiring manual source/license/content
review, never claim internal content was scanned or safe. Do not deserialize
or extract untrusted files. Legacy pickle and unknown binaries remain invalid.
Text with these suffixes remains scanned. Preserve path, size, links, other
scanners, text limit, process limits and stable. Test real Git blobs and
malformed/mismatched headers, limits, and existing regressions before release.
