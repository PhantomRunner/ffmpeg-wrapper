"""Initialize only container-owned/new empty directories, then drop root."""
import os
import pwd
from pathlib import Path

account = pwd.getpwnam('app')
for name in ('/home/app', '/output', '/tmp/runtime-app', '/tmp/desktop'):
    path = Path(name)
    path.mkdir(parents=True, exist_ok=True)
    # Do not recursively change ownership of mounted user files.
    if path.stat().st_uid == 0 and (name != '/output' or not any(path.iterdir())):
        os.chown(path, account.pw_uid, account.pw_gid)
    if name == '/tmp/runtime-app':
        path.chmod(0o700)
os.initgroups(account.pw_name, account.pw_gid)
os.setgid(account.pw_gid)
os.setuid(account.pw_uid)
os.environ['HOME'] = '/home/app'
if not os.access('/output', os.W_OK):
    raise SystemExit('Output folder is not writable. Set APP_UID/APP_GID to its owner, or choose an empty OUTPUT_DIR.')
os.execv('/usr/bin/supervisord', ['supervisord', '-n', '-c', '/opt/desktop/supervisord.conf'])
