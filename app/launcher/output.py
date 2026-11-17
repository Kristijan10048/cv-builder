"""Reusable column alignment and shared console output for launcher commands."""

from abc import ABC, abstractmethod
import sys

from . import constants as constants
from .presentation import GitRevisionProvider, TerminalCapabilities


class StyledLabel(str):
    """Keep visible text length intact while adding color after template padding."""

    def __new__(cls, value, color):
        """Store plain text as the string value so width calculations exclude ANSI."""
        instance = super().__new__(cls, value)
        instance.color = color
        return instance

    def __format__(self, specification):
        """Style only the label and leave surrounding alignment padding uncolored."""
        plain_text = str(self)
        padded_text = format(plain_text, specification)
        return padded_text.replace(plain_text, self.color + plain_text + constants.C_ANSI_RESET, constants.C_ONE)


class BaseOutputFormatter(ABC):
    """Define row formatting independently of command behavior or output destination."""

    @abstractmethod
    def format_rows(self, rows, template, minimum_widths=None):
        """Render named row values with shared widths and optional minimum column sizes."""


class AlignedOutputFormatter(BaseOutputFormatter):
    """Align arbitrary named columns without knowing any services or command names."""

    def format_rows(self, rows, template, minimum_widths=None):
        """Compute widths once per batch and expose each as a template's FIELD_width."""
        rendered_rows = [{name: value if isinstance(value, StyledLabel) else str(value)
                          for name, value in row.items()} for row in rows]
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

    def __init__(self, service_names, formatter=None, stream=None, terminal=None, revision_provider=None):
        """Reserve service-name width before streaming results so later rows stay aligned."""
        self.formatter = formatter or AlignedOutputFormatter()
        self.stream = stream
        self.terminal = terminal or TerminalCapabilities()
        self.revision_provider = revision_provider or GitRevisionProvider()
        names = (*service_names, constants.C_OUTPUT_LAUNCHER_NAME)
        self.minimum_widths = {constants.C_OUTPUT_NAME_FIELD: max(len(name) for name in names)}

    def write_rows(self, rows, template, stream=None):
        """Print a batch using reusable named-column templates, flushing progress immediately."""
        destination = stream if stream is not None else self.stream
        for line in self.formatter.format_rows(rows, template, self.minimum_widths):
            print(line, file=destination, flush=True)

    def _destination(self, stream=None):
        """Resolve the actual stream at write time, including redirected stdout."""
        if stream is not None:
            return stream
        return self.stream if self.stream is not None else sys.stdout

    def _label(self, label, stream=None):
        """Style known semantic outcomes without parsing diagnostic messages."""
        color = constants.C_STATUS_COLORS.get(label)
        if color and self.terminal.supports_color(self._destination(stream)):
            return StyledLabel(label, color)
        return label

    def header(self):
        """Print the checkout revision and optionally update the terminal title."""
        destination = self._destination()
        title = constants.C_TITLE_FORMAT.format(revision=self.revision_provider.revision())
        if self.terminal.supports_title(destination):
            print(constants.C_TERMINAL_TITLE_FORMAT.format(title=title), end=constants.C_EMPTY,
                  file=destination, flush=True)
        print(title, file=destination, flush=True)

    def result(self, name, detail, stream=None, outcome=None):
        """Print an aligned service result without waiting for other operations to finish."""
        if outcome is not None:
            label = self._label(outcome, stream)
            detail = (format(label) if str(detail) == outcome else
                      constants.C_OUTCOME_DETAIL_FORMAT.format(label=label, detail=detail))
        self.write_rows([{
            constants.C_OUTPUT_NAME_FIELD: name,
            constants.C_OUTPUT_DETAIL_FIELD: detail,
        }], constants.C_RESULT_FORMAT, stream)

    def statuses(self, statuses):
        """Render a status snapshot with aligned service, state, health, PID, and details."""
        self.write_rows([{
            constants.C_OUTPUT_NAME_FIELD: status.name,
            constants.C_FIELD_STATE: self._label(status.state),
            constants.C_FIELD_HEALTH: status.health,
            constants.C_FIELD_PID: status.pid or constants.C_NO_PID,
            constants.C_OUTPUT_DETAIL_FIELD: status.detail,
        } for status in statuses], constants.C_STATUS_FORMAT)

    def error(self, detail):
        """Write command-wide errors to stderr with the same service-column alignment."""
        self.result(constants.C_OUTPUT_LAUNCHER_NAME, detail, stream=sys.stderr)
