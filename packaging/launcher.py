"""Native executable entry point; installation checks are explicit and documented."""
import sys
from pathlib import Path

from media_wrapper.main import main

if len(sys.argv) == 4 and sys.argv[1] == '--verify-install':
    from media_wrapper.ui.installation_verification import verify_installation
    raise SystemExit(verify_installation(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()))
raise SystemExit(main())
