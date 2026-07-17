"""Fixtures for Centero tests."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.centero.const import DOMAIN

from .common import MockCenteroAPI


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""

    yield


@pytest.fixture
def mock_api():
    """Replace the gateway API with a controllable mock."""

    api = MockCenteroAPI()

    with patch("custom_components.centero.CenteroAPI", return_value=api):
        yield api


@pytest.fixture
def config_entry(hass: HomeAssistant, mock_api) -> MockConfigEntry:
    """Create a config entry, not yet set up."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1"},
    )

    entry.add_to_hass(hass)

    return entry
