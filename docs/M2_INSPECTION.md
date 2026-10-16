# M2 robust inspection verification

## M2.1
Immutable Qt-independent MediaFile/MediaStream entities replace raw stream dicts.
Infrastructure translates FFprobe JSON, preserves real indices and optional values,
and parses frame rates as Fraction (average rate with nominal fallback). Invalid
indices/duplicates/shapes fail clearly; absent metadata remains unknown. Existing
Inspect and all-stream Remux use the typed values. 122 tests passed on Linux;
Ruff passed. Windows execution remains pending under M0.4's CI gap.
