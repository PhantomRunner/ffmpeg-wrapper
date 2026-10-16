# M2 robust inspection verification

## M2.1
Immutable Qt-independent MediaFile/MediaStream entities replace raw stream dicts.
Infrastructure translates FFprobe JSON, preserves real indices and optional values,
and parses frame rates as Fraction (average rate with nominal fallback). Invalid
indices/duplicates/shapes fail clearly; absent metadata remains unknown. Existing
Inspect and all-stream Remux use the typed values. 122 tests passed on Linux;
Ruff passed. Windows execution remains pending under M0.4's CI gap.

## M2.2
Inspection now presents container/duration/size/bitrate and a typed stream table:
real index, codec/subtitle type, language, bitrate, frame size, exact rational FPS,
sample rate, channels and layout. Missing values display unknown. Stream checkboxes
store actual indices, with absent indices unselectable; file changes invalidate
selection. The UI explicitly states that this selection is for future operations
and the current Remux slice still copies all streams. 125 tests passed; Ruff passed.
