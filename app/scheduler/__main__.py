"""Launch the independent foreground worker with a clear nonzero startup failure."""

import sys

import portalocker

from .runtime import SchedulerRuntime

C_FAILURE_EXIT = 1
C_SUCCESS_EXIT = 0
C_DUPLICATE_MESSAGE = "A scheduler worker already owns this database."
C_STARTUP_MESSAGE = "Scheduler startup failed. Check configuration, dependencies and directory permissions."
C_MAIN_MODULE = "__main__"


def main():
    """Run without importing the web application or accepting arbitrary handler paths."""
    try:
        SchedulerRuntime().run()
    except portalocker.exceptions.LockException:
        print(C_DUPLICATE_MESSAGE, file=sys.stderr)
        return C_FAILURE_EXIT
    except KeyboardInterrupt:
        return C_SUCCESS_EXIT
    except Exception:
        print(C_STARTUP_MESSAGE, file=sys.stderr)
        return C_FAILURE_EXIT
    return C_SUCCESS_EXIT


if __name__ == C_MAIN_MODULE:
    raise SystemExit(main())
