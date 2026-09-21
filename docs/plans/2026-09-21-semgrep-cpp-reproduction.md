# rocSHMEM C++ parser incident verification

## Candidate 1.177.0 validation (2026-09-21)

Official latest release queried from semgrep/semgrep; candidate image pulled
without changing the production policy:
`semgrep/semgrep@sha256:acaac22ffc7b7cc5926de0751b223bce0b2491c33d18422fa72f632c78d81198`.

- Original pinned PR file: same line 1136 `single name expected for simple var`
  warning, exit 0, zero findings. The initial expect-fixed assertion failed.
- Ordinary-loop substitution in full file: no errors, zero findings.
- Minimal structured binding and ordinary loop: C++17 compiler and scanner pass.
- Explicit C++ system(input) control: compiles, scanner exits 1, matches
  hygon.c.system-call; no parse errors. Detection is not globally disabled.
- Four report-parser unit tests rerun and passed.

Conclusion: upgrading to this candidate does not resolve the incident. Do not
change the production image solely for this failure. Next design should narrowly
distinguish confirmed parser compatibility warnings from operational failure,
retain findings and visible incomplete-coverage information, and avoid globally
turning all parse errors into passing scans. No production behavior changed.
Candidate containers used offline execution with version checks disabled;
only the public pinned source download and image pull required network access.

- Incident: HYGON-AI/rocSHMEM-das run 35566088179, job 106228080177.
- Source pinned to a296ec7dad6aefa0103837eff1df98219ac759ad, src/gda/topology.cpp.
- Gate v2.0.5, production Semgrep 1.125.0 (digest in tests/semgrep_cpp_probe.py).
- Reproduced on quality-nmz1 using temporary fixtures, offline scanner containers,
  no execution of PR code, no production runner or policy changes.

## Observed comparisons

1. Minimal map/vector range-for with a C++17 structured binding: g++ with
   `-std=c++17 -pedantic-errors -fsyntax-only` passed; Semgrep also passed.
2. Pinned original PR file: Semgrep exit 0, zero findings, one `Other syntax error`
   (code 2, level warn), line 1136: `single name expected for simple var`.
3. Identical file, replacing only the structured-binding range-for with an entry
   variable and references to `.first` / `.second`: Semgrep exit 0, no errors,
   zero findings. This is a diagnostic control, not a proposed business-code edit.
4. Minimal ordinary range-for: compiler and scanner both passed.
5. Malformed range-for missing a closing parenthesis: compiler rejected it,
   but Semgrep returned exit 0, no errors and no findings. The probe now records
   this existing limitation rather than assuming Semgrep validates C++ syntax.

Conclusion: the failure depends on the structured binding in this file's context;
it is not general lack of support for C++17 structured bindings. The full project
was not compiled by this probe. No claim that all project code is compiler-valid.
Semgrep success also cannot replace the repository's compiler/build checks.

The gate currently converts the coverage warning to a failed scan. Its policy
has not been changed. The probe and report-parser tests characterize the failure,
not a completed fix. Upgrading the scanner still requires separate validation.

## Reproduce

Validation: 130 unit tests passed on Linux/Python 3.9, including the four new
report-parser cases. Windows/Python 3.13 had four platform-related errors
(three os.getuid, one default-encoding read); Linux is the supported gate runtime.
Probe assumptions were corrected from real observations: minimal structured
bindings parse successfully, and the malformed sample is tolerated by Semgrep.

```sh
python3.9 tests/semgrep_cpp_probe.py --gate-root "$PWD"
python3.9 tests/semgrep_cpp_probe.py --gate-root "$PWD" --incident
PYTHONPATH=src python3.9 -m unittest discover -s tests -p test_semgrep_cpp_coverage.py -v
```

The incident mode downloads only the pinned public source; containers have no
network. The fixed-image incident assertion is intentionally a characterization
of the existing bug and must be revised when validating a corrected image.
