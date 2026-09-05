"""Load .env into os.environ.

Stdlib rather than python-dotenv: it is ~10 lines, and every dependency added
here is one more thing to install on each machine that shares this folder.

EXISTING VARIABLES ALWAYS WIN. That is standard dotenv behaviour, and here it
is also what keeps the offline test suite offline: every test sets a dummy key
before importing orchestrator, and a real key sitting in .env must not quietly
replace it.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env")

# Per-machine secrets live OUTSIDE the project, in the home directory.
#
# The project folder is shared over a NAS, so any file inside it is one file
# read by both computers — it cannot hold a different API key for each. A
# hostname suffix does not rescue that: both machines here are named the same.
# The home directory is per-machine for free, and it keeps the key off the NAS
# entirely, which is where a credential should not be sitting anyway.
MACHINE_ENV_FILE = os.path.expanduser("~/.autobaseball.env")


def machine_env_file():
    """This computer's own env file. See MACHINE_ENV_FILE."""
    return MACHINE_ENV_FILE


def load(path=None):
    """Set any KEY=VALUE not already in the environment. Returns names set.

    Reads ~/.autobaseball.env FIRST (this machine's own, off the NAS), then the
    project's shared .env for anything it did not define — so a per-machine key
    wins while shared settings like BASEBALL_LOG_DIR still apply to both.

    Missing files are not an error: the variables may come from the shell,
    which is how this project worked before .env existed.
    """
    if path is not None:
        return _load_one(path)
    return _load_one(machine_env_file()) + _load_one(ENV_FILE)


def _load_one(path):
    try:
        with open(path) as fh:
            lines = fh.readlines()
    except OSError:
        return []
    added = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        # Strip one layer of matching quotes, so KEY="v" and KEY=v agree.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            added.append(key)
    return added
