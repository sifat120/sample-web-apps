"""
Unit tests for app.search._build_es_client_kwargs — verifies that the
hosted-Elasticsearch auth wiring (basic auth + API key) is honored.

These tests don't talk to Elasticsearch; they only assert that the
correct kwargs are produced from the Settings object so a hosted
provider like Elastic Cloud actually receives credentials.
"""
import pytest

from app import search
from app.config import settings


@pytest.fixture
def restore_settings():
    """Snapshot the auth-related settings and restore them after the test."""
    original = (settings.es_username, settings.es_password, settings.es_api_key)
    yield
    settings.es_username, settings.es_password, settings.es_api_key = original


def test_no_auth_when_settings_empty(restore_settings):
    settings.es_username = None
    settings.es_password = None
    settings.es_api_key = None

    assert search._build_es_client_kwargs() == {}


def test_basic_auth_when_username_and_password_set(restore_settings):
    settings.es_username = "elastic"
    settings.es_password = "hunter2"
    settings.es_api_key = None

    kwargs = search._build_es_client_kwargs()
    assert kwargs == {"basic_auth": ("elastic", "hunter2")}


def test_api_key_takes_precedence_over_basic_auth(restore_settings):
    settings.es_username = "elastic"
    settings.es_password = "hunter2"
    settings.es_api_key = "abc123=="

    kwargs = search._build_es_client_kwargs()
    assert kwargs == {"api_key": "abc123=="}


def test_partial_basic_auth_is_ignored(restore_settings):
    """If only one of username/password is set, no auth is sent (avoids 401 surprises)."""
    settings.es_username = "elastic"
    settings.es_password = None
    settings.es_api_key = None

    assert search._build_es_client_kwargs() == {}
