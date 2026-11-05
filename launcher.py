"""Start, stop, restart, or inspect registered CV Builder application services."""

from app.launcher.cli import LauncherApplication
from app.launcher.constants import C_MAIN_MODULE


if __name__ == C_MAIN_MODULE:
    raise SystemExit(LauncherApplication().run())
