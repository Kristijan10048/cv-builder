"""Reusable column alignment and shared console output for launcher commands."""

from abc import ABC, abstractmethod
import sys

from . import constants as constants


class BaseOutputFormatter(ABC):
    """Define row formatting independently of command behavior or output destination."""

    @abstractmethod
    def format_rows(self, rows, template, minimum_widths=None):
        """Render named row values with shared widths and optional minimum column sizes."""


class AlignedOutputFormatter(BaseOutputFormatter):
    """Align arbitrary named columns without knowing any services or command names."""

    def format_rows(self, rows, template, minimum_widths=None):
        """Compute widths once per batch and expose each as a template's FIELD_width."""
        rendered_rows = [{name: str(value) for name, value in row.items()} for row in rows]
        widths = dict(minimum_widths or {})
        for row in rendered_rows:
            for name, value in row.items():
                widths[name] = max(widths.get(name, constants.C_ZERO), len(value))
        template_widths = {
            constants.C_OUTPUT_WIDTH_FORMAT.format(name=name): width for name, width in widths.items()
        }
        return [template.format(**row, **template_widths).rstrip() for row in rendered_rows]


class LauncherOutput:
    """Route status, lifecycle results, and errors through the same injectable formatter."""

    def __init__(self, service_names, formatter=None, stream=None):
        """Reserve service-name width before streaming results so later rows stay aligned."""
        self.formatter = formatter or AlignedOutputFormatter()
        self.stream = stream
        names = (*service_names, constants.C_OUTPUT_LAUNCHER_NAME)
        self.minimum_widths = {constants.C_OUTPUT_NAME_FIELD: max(len(name) for name in names)}

    def write_rows(self, rows, template, stream=None):
        """Print a batch using reusable named-column templates, flushing progress immediately."""
        destination = stream if stream is not None else self.stream
        for line in self.formatter.format_rows(rows, template, self.minimum_widths):
            print(line, file=destination, flush=True)

    def result(self, name, detail, stream=None):
        """Print an aligned service result without waiting for other operations to finish."""
        self.write_rows([{
            constants.C_OUTPUT_NAME_FIELD: name,
            constants.C_OUTPUT_DETAIL_FIELD: detail,
        }], constants.C_RESULT_FORMAT, stream)

    def statuses(self, statuses):
        """Render a status snapshot with aligned service, state, health, PID, and details."""
        self.write_rows([{
            constants.C_OUTPUT_NAME_FIELD: status.name,
            constants.C_FIELD_STATE: status.state,
            constants.C_FIELD_HEALTH: status.health,
            constants.C_FIELD_PID: status.pid or constants.C_NO_PID,
            constants.C_OUTPUT_DETAIL_FIELD: status.detail,
        } for status in statuses], constants.C_STATUS_FORMAT)

    def error(self, detail):
        """Write command-wide errors to stderr with the same service-column alignment."""
        self.result(constants.C_OUTPUT_LAUNCHER_NAME, detail, stream=sys.stderr)
