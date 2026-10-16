"""Run Qt tests without requiring a display server."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
