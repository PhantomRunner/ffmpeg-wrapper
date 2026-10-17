# M8 advanced workflows

Tests and integrity verification run at the end of this milestone, as requested.
Native Windows and successful physical GPU execution remain unverified.

## M8.1 implementation
Strict version-1 JSON profile files store encoding choices and real track indices,
not source/destination or executable paths. Save/export refuses existing files;
import rejects unknown versions/fields and validates against the current media
and selected build on a worker. Import applies editable choices without running.

## M8.2 implementation
Convert/Compress can batch selected Files rows using {stem}, {index}, {ext}.
Worker re-probes and validates every input/output before adding any job; template
paths/expressions, existing output, source collisions, case-insensitive name
collisions and queued output reservations are rejected. Real track indices apply
per source; missing/incompatible tracks reject the entire batch. No jobs start
until the user starts Queue. Tests deferred to milestone end.

## M8.3 implementation
Convert/Compress accept explicit output order of selected real indices and
per-track copy/omit/text-subtitle encoding. Bitmap-to-text conversion is rejected.
Remux/Convert/Compress explicitly preserve or strip global/track metadata and
chapters. FFprobe now returns typed chapters and container tags; publication
checks the requested chapter count/removal. Metadata preservation is limited by
the destination container; encoder/muxer-generated tags may remain when stripping.
Tests deferred to milestone end.

## M8.4 implementation
Settings persists the chosen DEBUG/INFO/WARNING/ERROR local logging level.
Diagnostics export defaults to an allowlisted task summary without paths,
metadata, raw errors or arguments. A clearly labeled opt-in adds private task
paths, arguments and retained logs. Exports refuse overwrite and run on a worker.
Tests deferred to milestone end.

## M8.5 implementation
Convert/Compress profiles and previews support only -threads (1–64) and
-max_muxing_queue_size (1–65536), once each. The pure domain parser rejects
all other options, duplicates and nonnumeric values. The command builder
validates again and emits separate argument-array entries before the fixed
container/output. No shell, input, mapping, filter, protocol or overwrite flags
can be supplied. Tests deferred to milestone end.

## M8.6 implementation
Queue explicitly saves unfinished definitions to a new version-1 JSON file.
Files contain local paths, source size/mtime and typed operation settings, never
executable paths, process IDs, temporary outputs or previous task statuses.
Load uses the currently selected FFmpeg, re-probes sources, validates all plans
and output reservations before adding fresh pending attempts. Changed/missing
sources and existing/conflicting outputs reject the import. Start is explicit;
GPU runtime checks still run before execution. Files are local to the operating
system whose absolute paths they contain; no checkpoint or automatic persistence.
Tests deferred to milestone end.
