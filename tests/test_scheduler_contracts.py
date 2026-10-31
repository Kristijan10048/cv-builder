"""Offline acceptance tests for frozen scheduler schemas and adapter boundaries."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.scheduler import contracts
from app.scheduler import constants as scheduler_constants
from app.scheduler.errors import C_ERROR_HTTP_STATUS

C_SCHEDULE_PAGE_MODEL = 'SchedulePage'
C_RUN_PAGE_MODEL = 'RunPage'
C_TIMESTAMP = 'timestamp'
C_TRIGGER_KIND = 'trigger_kind'
C_SECONDS = 'seconds'
C_REVISION = 'revision'
C_KEY = 'key'
C_UNTRIMMED_NAME = '  Search  '
C_OFFSET_ANCHOR = '2035-01-01T01:00:00+01:00'
C_MAXIMUM_RESULTS = 1000
C_PAGINATION = 'pagination'
C_VALUE = 'value'
C_FIELD_NAME = 'field_name'
C_TRIGGER = 'trigger'
C_KIND = 'kind'
C_RUN_AT = 'run_at'
C_ONCE = 'once'
C_INTERVAL = 'interval'
C_NAME = 'name'
C_RESULTS_WANTED = 'results_wanted'
C_TRIMMED_NAME = 'Search'
C_UTC_ANCHOR = '2035-01-01T00:00:00Z'
C_ROUTES = 'routes'
C_FAKE_HANDLERS = 'fake_handlers'
C_CREATE_INTERVAL = 'create_interval'
C_PAYLOAD = 'payload'
C_MINIMUM_INTERVAL_SECONDS = 300
C_ONE = 1
C_PAGE = 'page'
C_ZERO = 0
C_PAGE_SIZE = 'page_size'
C_EXCESSIVE_PAGE_SIZE = 101
C_COERCED_PAGE_SIZE = '20'
C_UNKNOWN = 'unknown'
C_CASES = 'cases'
C_GET = 'GET'
C_API_SCHEDULER_STATUS = '/api/scheduler/status'
C_MANUAL_RUN = 'manual_run'
C_SCHEDULED_FOR = 'scheduled_for'
C_IDEMPOTENCY_KEY = 'idempotency_key'
C_SECOND_REVISION = 2
C_EXPIRES_AT = 'expires_at'
C_MODELS = 'models'
C_MODEL = 'model'
C_SCHEMA_ADDITIONAL_PROPERTIES = 'additionalProperties'
C_POPULATED = 'populated'
C_OFFLINE = 'offline'
C_STORAGE_ERROR = 'storage_error'
C_METHOD = 'method'
C_CONFLICT = 'conflict'
C_PATH = 'path'
C_VALIDATION_ERROR = 'validation_error'
C_API_TASK_SCHEDULES_ID = '/api/task-schedules/{id}'
C_EMPTY = 'empty'
C_FIRST_ERROR_STATUS = 400
C_LIFECYCLE_RUNS = 'lifecycle_runs'
C_RUN = 'run'
C_RESULT = 'result'
C_REQUEST_MODEL = 'request_model'
C_RESPONSE_MODEL = 'response_model'
C_NO_CONTENT_STATUS = 204
C_STATUS = 'status'
C_JSON = 'json'
C_RESPONSE = 'response'
C_REQUEST = 'request'
C_CODE = 'code'
C_ERROR = 'error'
C_REJECTED_TRIGGER_FIELDS = [
    {"kind": "cron", "expression": "* * * * *"},
    {"kind": "once", "run_at": "2035-01-01T00:00:00Z", "seconds": 300},
    {"kind": "interval", "starts_at": "2035-01-01T00:00:00Z", "seconds": 300, "callable": "os.system"},
]
C_REJECTED_RUN_FIELDS = [
    ("finished_at", "2030-01-01T00:00:00Z"),
    ("started_at", "2030-01-01T00:00:00Z"),
    ("state", "retrying"),
    ("state", "succeeded"),
    ("state", "running"),
]

C_ROOT = Path(__file__).resolve().parents[1]
C_FIXTURE_PATH = C_ROOT / "docs/roadmap_scheduler/contract_examples.json"
C_ENCODING = "utf-8"
C_NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
C_CONTEXT = {"now": C_NOW}
C_MODEL_REGISTRY = {
    model.__name__: model for model in (
        contracts.CreateScheduleRequest, contracts.ReplaceScheduleRequest,
        contracts.RevisionRequest, contracts.RunNowRequest, contracts.PaginationRequest,
        contracts.ScheduleRecord, contracts.RunRecord, contracts.WorkerStatus,
        contracts.ErrorResponse, contracts.RunNowResponse, contracts.TaskResult,
    )
}
C_MODEL_REGISTRY[C_SCHEDULE_PAGE_MODEL] = contracts.Page[contracts.ScheduleRecord]
C_MODEL_REGISTRY[C_RUN_PAGE_MODEL] = contracts.Page[contracts.RunRecord]
C_EXPECTED_ROUTES = {
    ("GET", "/api/task-schedules"), ("POST", "/api/task-schedules"),
    ("GET", "/api/task-schedules/{id}"), ("PUT", "/api/task-schedules/{id}"),
    ("DELETE", "/api/task-schedules/{id}"), ("POST", "/api/task-schedules/{id}/pause"),
    ("POST", "/api/task-schedules/{id}/resume"), ("POST", "/api/task-schedules/{id}/run-now"),
    ("GET", "/api/task-schedules/{id}/runs"), ("GET", "/api/scheduler/status"),
}
C_INVALID_DEFINITIONS = [
    ("payload_version", True), ("payload_version", "1"), ("payload_version", 1.0),
    ("payload_version", 2), ("task_type", "os.system"), ("name", " "),
    ("name", "x" * 121), ("callable", "subprocess.run"),
]
C_INVALID_PAYLOADS = [
    ("preference_id", True), ("preference_id", "1"), ("preference_id", 0),
    ("results_wanted", True), ("results_wanted", 1.0), ("results_wanted", "50"),
    ("results_wanted", 0), ("results_wanted", 1001), ("sites", []),
    ("sites", ["linkedin", "linkedin"]), ("sites", ["fake"]),
    ("sites", [True]), ("sites", "linkedin"), ("module", "os"),
]
C_INVALID_TIMESTAMPS = ["2035-01-01", "2035-01-01T00:00:00", True, 2051222400,
                        datetime(2035, 1, 1), "not-a-date"]
C_INVALID_INTERVALS = [True, "300", 300.0, 299, 31_536_001]
C_INVALID_REVISIONS = [True, "1", 1.0, 0, -1]
C_INVALID_KEYS = ["", " ", "key with spaces", "../key", "ä", "k" * 129, True]
C_DATE_FIELD = "starts_at"


class FixtureReader:
    """Read the same concrete fixture artifact consumed by later API and UI work."""

    @staticmethod
    def read() -> dict:
        """Return a fresh copy so rejection tests cannot alter subsequent examples."""
        return json.loads(C_FIXTURE_PATH.read_text(encoding=C_ENCODING))

    @classmethod
    def definition(cls) -> dict:
        """Return the populated interval create body."""
        return cls.read()[C_MODELS][C_CREATE_INTERVAL][C_VALUE]


class FrozenClock(contracts.BaseClock):
    """Supply deterministic offline fixture time to fake task handlers."""

    def now(self) -> datetime:
        """Return the fixed fixture instant."""
        return C_NOW


class FixtureTaskHandler(contracts.BaseTaskHandler):
    """Return a fixture result without importing a scraper or contacting a board."""

    def __init__(self, result: contracts.TaskResult) -> None:
        """Inject one success/partial/failure outcome."""
        self.result = result

    def execute(self, run, repository, clock) -> contracts.TaskResult:
        """Validate the dispatcher boundary and return the independent fixture result."""
        assert run.state == scheduler_constants.C_RUN_RUNNING
        assert clock.now() == C_NOW
        return self.result.model_copy(deep=True)


class TestSchedulerContracts:
    """Exercise strict request parsing, lifecycle vocabulary, and fixture coverage."""

    @pytest.mark.parametrize((C_FIELD_NAME, C_VALUE), C_INVALID_DEFINITIONS)
    def test_reject_invalid_definition(self, field_name, value):
        """Reject arbitrary handler selection and invalid top-level values."""
        definition = FixtureReader.definition()
        definition[field_name] = value
        with pytest.raises(ValidationError):
            contracts.CreateScheduleRequest.model_validate(definition, context=C_CONTEXT)

    @pytest.mark.parametrize((C_FIELD_NAME, C_VALUE), C_INVALID_PAYLOADS)
    def test_reject_invalid_payload(self, field_name, value):
        """Reject coercion, unsupported boards and extra handler payload fields."""
        definition = FixtureReader.definition()
        definition[C_PAYLOAD][field_name] = value
        with pytest.raises(ValidationError):
            contracts.CreateScheduleRequest.model_validate(definition, context=C_CONTEXT)

    @pytest.mark.parametrize(C_TIMESTAMP, C_INVALID_TIMESTAMPS)
    @pytest.mark.parametrize(C_TRIGGER_KIND, [C_INTERVAL, C_ONCE])
    def test_reject_naive_or_coerced_dates(self, timestamp, trigger_kind):
        """Both trigger variants require an actual offset-bearing date/time."""
        definition = FixtureReader.definition()
        definition[C_TRIGGER] = {C_KIND: C_ONCE, C_RUN_AT: timestamp}
        if trigger_kind == C_INTERVAL:
            definition[C_TRIGGER] = {C_KIND: trigger_kind, C_SECONDS: C_MINIMUM_INTERVAL_SECONDS, C_DATE_FIELD: timestamp}
        with pytest.raises(ValidationError):
            contracts.CreateScheduleRequest.model_validate(definition, context=C_CONTEXT)

    @pytest.mark.parametrize(C_SECONDS, C_INVALID_INTERVALS)
    def test_reject_interval_limits(self, seconds):
        """Intervals reject out-of-range values and boolean/numeric coercion."""
        definition = FixtureReader.definition()
        definition[C_TRIGGER][C_SECONDS] = seconds
        with pytest.raises(ValidationError):
            contracts.CreateScheduleRequest.model_validate(definition, context=C_CONTEXT)

    @pytest.mark.parametrize(C_REVISION, C_INVALID_REVISIONS)
    def test_revision_is_strict(self, revision):
        """Revision-check requests require positive exact integers."""
        with pytest.raises(ValidationError):
            contracts.RevisionRequest(revision=revision)

    @pytest.mark.parametrize(C_KEY, C_INVALID_KEYS)
    def test_manual_key_is_bounded(self, key):
        """Manual keys cannot contain ambiguous whitespace, Unicode, or path syntax."""
        with pytest.raises(ValidationError):
            contracts.RunNowRequest(revision=C_ONE, idempotency_key=key)

    def test_utc_normalization_and_boundaries(self):
        """Preserve instants, trim names, accept inclusive limits, and use one Z."""
        definition = FixtureReader.definition()
        definition[C_NAME] = C_UNTRIMMED_NAME
        definition[C_TRIGGER][C_DATE_FIELD] = C_OFFSET_ANCHOR
        definition[C_TRIGGER][C_SECONDS] = scheduler_constants.C_MAX_INTERVAL_SECONDS
        definition[C_PAYLOAD][C_RESULTS_WANTED] = C_MAXIMUM_RESULTS
        request = contracts.CreateScheduleRequest.model_validate(definition, context=C_CONTEXT)
        assert request.name == C_TRIMMED_NAME
        assert request.model_dump(mode=C_JSON)[C_TRIGGER][C_DATE_FIELD] == C_UTC_ANCHOR
        assert contracts.CreateScheduleRequest.model_validate_json(request.model_dump_json(), context=C_CONTEXT) == request

    def test_defaults_reuse_manual_search(self):
        """Fetch payload defaults continue to match JobSearchInput."""
        from app.models import JobSearchInput
        assert contracts.FetchJobsPayload(preference_id=C_ONE).model_dump() == JobSearchInput(preference_id=C_ONE).model_dump()

    @pytest.mark.parametrize(C_TRIGGER, C_REJECTED_TRIGGER_FIELDS)
    def test_reject_unknown_trigger_fields(self, trigger):
        """Reject cron, cross-variant properties and executable trigger fields."""
        definition = FixtureReader.definition()
        definition[C_TRIGGER] = trigger
        with pytest.raises(ValidationError):
            contracts.CreateScheduleRequest.model_validate(definition, context=C_CONTEXT)

    @pytest.mark.parametrize((C_FIELD_NAME, C_VALUE), C_REJECTED_RUN_FIELDS)
    def test_reject_inconsistent_run_state(self, field_name, value):
        """History cannot report completion or running without its required evidence."""
        run = FixtureReader.read()[C_MODELS][C_MANUAL_RUN][C_VALUE]
        run[field_name] = value
        with pytest.raises(ValidationError):
            contracts.RunRecord.model_validate(run)

    def test_create_and_changed_trigger_require_future(self):
        """A name-only edit can preserve a past anchor; changing it requires a future one."""
        definition = FixtureReader.definition()
        definition[C_TRIGGER][C_DATE_FIELD] = C_NOW
        with pytest.raises(ValidationError):
            contracts.CreateScheduleRequest.model_validate(definition, context=C_CONTEXT)
        current = contracts.ScheduleDefinition.model_validate(definition)
        replacement = contracts.ReplaceScheduleRequest.model_validate({**definition, C_REVISION: C_ONE})
        replacement.validate_against(current, C_NOW)
        replacement.trigger.seconds += scheduler_constants.C_ONE
        with pytest.raises(ValueError):
            replacement.validate_against(current, C_NOW)

    @pytest.mark.parametrize(C_PAGINATION, [{C_PAGE: True}, {C_PAGE: C_ZERO}, {C_PAGE_SIZE: C_EXCESSIVE_PAGE_SIZE},
                                             {C_PAGE_SIZE: C_COERCED_PAGE_SIZE}, {C_UNKNOWN: C_ONE}])
    def test_pagination_rejects_invalid_input(self, pagination):
        """The list envelope uses strict, bounded page parameters."""
        with pytest.raises(ValidationError):
            contracts.PaginationRequest.model_validate(pagination)

    def test_every_route_and_model_fixture(self):
        """Validate reusable examples and require applicable route/state coverage."""
        fixtures = FixtureReader.read()
        for fixture in fixtures[C_MODELS].values():
            model = C_MODEL_REGISTRY[fixture[C_MODEL]]
            model.model_validate(fixture[C_VALUE], context=C_CONTEXT)
            assert model.model_json_schema()[C_SCHEMA_ADDITIONAL_PROPERTIES] is False
        assert {(route[C_METHOD], route[C_PATH]) for route in fixtures[C_ROUTES]} == C_EXPECTED_ROUTES
        for route in fixtures[C_ROUTES]:
            cases = route[C_CASES]
            assert {C_POPULATED, C_OFFLINE, C_STORAGE_ERROR} <= set(cases)
            if route[C_METHOD] != C_GET:
                assert C_CONFLICT in cases
            if route[C_PATH] != C_API_SCHEDULER_STATUS:
                assert C_VALIDATION_ERROR in cases
            if route[C_METHOD] == C_GET and route[C_PATH] != C_API_TASK_SCHEDULES_ID:
                assert C_EMPTY in cases
            for scenario, case in cases.items():
                if case[C_REQUEST_MODEL] is not None:
                    model = C_MODEL_REGISTRY[case[C_REQUEST_MODEL]]
                    if scenario == C_VALIDATION_ERROR:
                        with pytest.raises(ValidationError):
                            model.model_validate(case[C_REQUEST], context=C_CONTEXT)
                    else:
                        model.model_validate(case[C_REQUEST], context=C_CONTEXT)
                if case[C_RESPONSE_MODEL] is None:
                    assert case[C_STATUS] == C_NO_CONTENT_STATUS
                    assert case[C_RESPONSE] is None
                else:
                    C_MODEL_REGISTRY[case[C_RESPONSE_MODEL]].model_validate(case[C_RESPONSE], context=C_CONTEXT)
                if case[C_STATUS] >= C_FIRST_ERROR_STATUS:
                    assert C_ERROR_HTTP_STATUS[case[C_RESPONSE][C_ERROR][C_CODE]] == case[C_STATUS]
        states = {contracts.RunRecord.model_validate(value).state for value in fixtures[C_LIFECYCLE_RUNS]}
        assert states == scheduler_constants.C_ACTIVE_STATES | scheduler_constants.C_TERMINAL_STATES

    def test_fake_handler_fixtures(self):
        """Every injected handler outcome works without database or board access."""
        for fixture in FixtureReader.read()[C_FAKE_HANDLERS]:
            run = contracts.RunRecord.model_validate(fixture[C_RUN])
            result = contracts.TaskResult.model_validate(fixture[C_RESULT])
            assert FixtureTaskHandler(result).execute(run, None, FrozenClock()) == result

    def test_run_keys_and_snapshot_identity(self):
        """Manual keys cannot alias timed occurrences or a different claimed revision."""
        run = FixtureReader.read()[C_MODELS][C_MANUAL_RUN][C_VALUE]
        for field_name, value in [(C_SCHEDULED_FOR, C_NOW), (C_IDEMPOTENCY_KEY, None),
                                  (C_REVISION, C_SECOND_REVISION), (C_EXPIRES_AT, None)]:
            candidate = deepcopy(run)
            candidate[field_name] = value
            with pytest.raises(ValidationError):
                contracts.RunRecord.model_validate(candidate)

    def test_abstract_boundaries_cannot_be_started(self):
        """Contracts cannot accidentally instantiate production work or storage."""
        for abstract_class in (contracts.BaseClock, contracts.BaseTaskHandler, contracts.BaseExecutor,
                               contracts.BaseExecutionReservation, contracts.BaseScheduleRepository):
            with pytest.raises(TypeError):
                abstract_class()
