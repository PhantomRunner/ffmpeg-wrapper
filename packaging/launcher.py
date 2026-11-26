"""Native executable entry point; installation checks are explicit and documented."""
import sys
from pathlib import Path

from media_wrapper.infrastructure.process_lifetime import child_entry

def launch() -> int:
    child_status = child_entry(sys.argv)
    if child_status is not None:
        return child_status

    if len(sys.argv) == 4 and sys.argv[1] == '--verify-install':
        from media_wrapper.ui.installation_verification import verify_installation
        return verify_installation(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())

    from media_wrapper.main import main
    return main()


if __name__ == '__main__':
    raise SystemExit(launch())
