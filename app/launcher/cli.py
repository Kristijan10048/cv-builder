"""Public launcher argument validation and human-readable lifecycle output."""

import argparse

import portalocker
import psutil

from . import constants as constants
from .manager import ServiceManager
from .models import LauncherConfiguration
from .output import LauncherOutput
from .services import ServiceRegistry


class LauncherApplication:
    """Expose service-independent flags with explicit mutation targets."""

    def __init__(self):
        """Build the trusted service catalog and argument parser without starting services."""
        self.registry = ServiceRegistry()
        self.output = LauncherOutput(self.registry.definitions)
        self.parser = argparse.ArgumentParser(description=constants.C_DESCRIPTION)
        actions = self.parser.add_mutually_exclusive_group(required=True)
        for action in constants.C_ACTIONS:
            actions.add_argument(constants.C_SHORT_FLAG.format(action), constants.C_LONG_FLAG.format(action),
                                 dest=constants.C_ACTION_DESTINATION, action=constants.C_STORE_CONSTANT, const=action)
        targets = self.parser.add_mutually_exclusive_group()
        targets.add_argument(constants.C_SERVICE_FLAG, choices=self.registry.definitions)
        targets.add_argument(constants.C_ALL_FLAG, action=constants.C_STORE_TRUE)
        self.parser.add_argument(constants.C_FORCE_FLAG, action=constants.C_STORE_TRUE)
        self.parser.add_argument(constants.C_FOREGROUND_FLAG, action=constants.C_STORE_TRUE)

    def run(self, arguments=None):
        """Validate CLI combinations before reading settings or mutating runtime state."""
        options = self.parser.parse_args(arguments)
        if options.action != constants.C_STATUS and not (options.service or options.all):
            self.parser.error(constants.C_TARGET_ERROR)
        if options.force and options.action not in (constants.C_STOP, constants.C_RESTART):
            self.parser.error(constants.C_FORCE_ERROR)
        if options.foreground and options.action != constants.C_START:
            self.parser.error(constants.C_FOREGROUND_ERROR)
        names = [options.service] if options.service else list(self.registry.definitions)
        try:
            manager = ServiceManager(LauncherConfiguration.from_environment(), self.registry, output=self.output)
            if options.action == constants.C_STATUS:
                statuses = [manager.status(name) for name in names]
                self.output.statuses(statuses)
                succeeded = all(status.state in (constants.C_RUNNING, constants.C_STOPPED) for status in statuses)
                return constants.C_SUCCESS if succeeded else constants.C_FAILURE
            if options.foreground:
                return manager.supervise(self.registry.ordered(names))
            return manager.execute(options.action, names, options.force)
        except (OSError, ValueError, RuntimeError, portalocker.exceptions.LockException, psutil.Error) as exception:
            self.output.error(exception)
            return constants.C_FAILURE
        except KeyboardInterrupt:
            return constants.C_FAILURE
