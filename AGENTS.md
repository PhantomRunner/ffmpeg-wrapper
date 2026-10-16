# Codex project instructions

Project: cross-platform FFmpeg UI wrapper for advanced Linux and Windows users.

## Current implementation
Python 3.11+, PySide6 Qt Widgets; FFmpeg/FFprobe are subprocesses, NOT linked libraries. MVP starts with binary detection and Inspect; implement remux, transcoding, compression, queue and GPU capabilities incrementally.

## Architectural rules
- Keep `domain/` Qt-independent.
- UI calls application services; never build FFmpeg argument lists inside widgets.
- Infrastructure handles subprocesses and OS APIs.
- Run binaries with argument arrays; never use shell=True.
- Support external PATH/custom folder and bundled binary directory (no automatic hidden fallback).
- Treat codec capabilities as per-build and per-machine, and runtime-test GPU encoders.
- Never silently overwrite source or destination files.
- Long-running FFmpeg/FFprobe calls must not block the Qt event loop.
- Keep Linux and Windows portability in mind; use pathlib.
- Write pytest tests for new parsing, validation and command-generation behavior.
- Implement features in small vertical slices; keep the application runnable.

Read docs/ARCHITECTURE.md and docs/ROADMAP.md before substantial changes. Do not assume unfinished features exist.
