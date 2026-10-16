"""Regression checks for the simplified, vendor-neutral settings form."""

from functools import partial

import httpx
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app.main import app

C_HOME_URL = "/"
C_SETTINGS_URL = "/api/settings"
C_MODELS_URL = "/api/lm-studio/models"
C_SERVER_URL = "http://llm.example.test/v1"
C_URL_KEY = "lm_studio_url"
C_MODEL_KEY = "lm_studio_model"
C_SAVED_MODEL = "saved-model"
C_HTTP_OK = 200
C_HTTP_BAD_REQUEST = 400
C_HTTP_BAD_GATEWAY = 502
C_SETTINGS_SELECTOR = "#settingsView"
C_HTML_PARSER = "html.parser"
C_INPUT_SELECTOR = "input"
C_INPUT_ID = "id"
C_URL_INPUT_ID = "llmServerUrl"
C_URL_LABEL = "LLM server API URL"
C_VENDOR_NAME = "LM Studio"
C_TRAILING_SLASH = "/"
C_EMPTY_MODEL = ""
C_INVALID_URL = "file:///invalid"
C_DETAIL_KEY = "detail"
C_URL_ERROR = "LLM server API URL must start with http:// or https://"
C_CONNECTION_ERROR = "Could not connect to the LLM server API."
C_ASYNC_CLIENT_ATTRIBUTE = "AsyncClient"
C_MODELS_SUFFIX = "/models"
C_MODELS_RESPONSE = {"data": [{"id": C_SAVED_MODEL}]}
C_NETWORK_ERROR = "Connection unavailable"


class TestLlmSettings:
    """Verify the visible form and its backward-compatible API behavior."""

    def test_form_contains_only_the_server_url(self):
        """Present a generic URL setting without the redundant model override."""
        with TestClient(app) as client:
            response = client.get(C_HOME_URL)
        assert response.status_code == C_HTTP_OK
        settings_view = BeautifulSoup(response.text, C_HTML_PARSER).select_one(
            C_SETTINGS_SELECTOR
        )
        assert settings_view is not None
        assert C_VENDOR_NAME not in str(settings_view)
        assert C_URL_LABEL in settings_view.get_text()
        assert [element[C_INPUT_ID] for element in settings_view.select(C_INPUT_SELECTOR)] == [
            C_URL_INPUT_ID
        ]

    def test_url_only_save_preserves_existing_model(self):
        """Save the simplified form without erasing an existing model override."""
        with TestClient(app) as client:
            original = client.put(
                C_SETTINGS_URL,
                json={C_URL_KEY: C_SERVER_URL, C_MODEL_KEY: C_SAVED_MODEL},
            )
            assert original.status_code == C_HTTP_OK
            response = client.put(
                C_SETTINGS_URL, json={C_URL_KEY: C_SERVER_URL + C_TRAILING_SLASH}
            )
            assert response.status_code == C_HTTP_OK
            assert response.json() == {
                C_URL_KEY: C_SERVER_URL,
                C_MODEL_KEY: C_SAVED_MODEL,
            }
            assert client.get(C_SETTINGS_URL).json() == response.json()
            # Legacy API clients can still explicitly clear the model override.
            cleared = client.put(C_SETTINGS_URL, json={C_MODEL_KEY: C_EMPTY_MODEL})
            assert cleared.status_code == C_HTTP_OK
            assert cleared.json() == {
                C_URL_KEY: C_SERVER_URL,
                C_MODEL_KEY: C_EMPTY_MODEL,
            }

    def test_invalid_url_uses_generic_error(self):
        """Report URL validation failures without exposing a vendor name."""
        with TestClient(app) as client:
            original = client.get(C_SETTINGS_URL).json()
            response = client.put(C_SETTINGS_URL, json={C_URL_KEY: C_INVALID_URL})
            assert response.status_code == C_HTTP_BAD_REQUEST
            assert response.json()[C_DETAIL_KEY] == C_URL_ERROR
            assert client.get(C_SETTINGS_URL).json() == original

    def test_connection_returns_available_models(self, monkeypatch):
        """Probe the configured server using its OpenAI-compatible models endpoint."""
        requested_urls = []

        def respond(request):
            """Capture the upstream URL and return a deterministic model list."""
            requested_urls.append(str(request.url))
            return httpx.Response(C_HTTP_OK, json=C_MODELS_RESPONSE)

        with TestClient(app) as client:
            client.put(C_SETTINGS_URL, json={C_URL_KEY: C_SERVER_URL})
            monkeypatch.setattr(
                httpx,
                C_ASYNC_CLIENT_ATTRIBUTE,
                partial(httpx.AsyncClient, transport=httpx.MockTransport(respond)),
            )
            response = client.get(C_MODELS_URL)
        assert response.status_code == C_HTTP_OK
        assert response.json() == C_MODELS_RESPONSE
        assert requested_urls == [C_SERVER_URL + C_MODELS_SUFFIX]

    def test_connection_failure_uses_generic_error(self, monkeypatch):
        """Report an unavailable LLM server without mentioning a specific vendor."""
        def fail_connection(request):
            """Simulate an unreachable upstream API without making a network request."""
            raise httpx.ConnectError(C_NETWORK_ERROR, request=request)

        with TestClient(app) as client:
            monkeypatch.setattr(
                httpx,
                C_ASYNC_CLIENT_ATTRIBUTE,
                partial(httpx.AsyncClient, transport=httpx.MockTransport(fail_connection)),
            )
            response = client.get(C_MODELS_URL)
        assert response.status_code == C_HTTP_BAD_GATEWAY
        assert response.json()[C_DETAIL_KEY] == C_CONNECTION_ERROR
