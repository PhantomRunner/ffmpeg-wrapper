# M8 advanced workflows

Tests and integrity verification run at the end of this milestone, as requested.
Native Windows and successful physical GPU execution remain unverified.

## M8.1 implementation
Strict version-1 JSON profile files store encoding choices and real track indices,
not source/destination or executable paths. Save/export refuses existing files;
import rejects unknown versions/fields and validates against the current media
and selected build on a worker. Import applies editable choices without running.
