# R5 — Dual timelines

Implemented 2026-10-18. Processing uses a QAbstractTableModel with stable task
identities and a progress delegate. It displays operation/codecs, output, state,
actual percentage, speed and ETA. Missing values stay unknown; unknown progress
has a dashed track without artificial fill or animation. The same native table
exposes text equivalents to keyboard/accessibility clients. Cancel, retry, CPU
retry, definitions and expandable logs remain bound to existing queue services;
context menu actions mirror their enabled states. Verified completed output can
be opened in the OS file manager without a shell.

Media Timeline uses QGraphicsScene for a real container-duration ruler and stream
lanes, plus a keyboard-accessible lane list. Lane selection displays stream details
without changing export choices. Widths explicitly represent the container span;
individual stream timestamps were not collected by the existing parser. Missing
or invalid duration produces an explicit untimed fallback. No waveform, thumbnail,
editing or unsupported seek is fabricated. Tab selection persists through R3's
layout store; switching preserves queue and source state.

Validation: 346 tests passed in the full phase suite; after adding verified-output
coverage, all 3 timeline tests passed. These cover unknown/determinate progress,
stable updates, real stream indices, unknown duration, selection, tab switching,
and verified-only output actions. Ruff/diff checks passed. Six-mode layout smoke
passed at three sizes and 100%/200% scaling; inspected the real audio timeline.
Native Windows verification remains pending. R6 follows with fallback/polish,
parity review, final regression coverage and rollout documentation.
