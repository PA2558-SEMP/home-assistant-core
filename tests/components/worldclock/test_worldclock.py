"""Tests for the combined email + Signal Worldclock Sensor."""

import pytest
import smtplib
from unittest.mock import AsyncMock, patch

from datetime import datetime, timedelta

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

# We'll patch the now() method to control time in tests
FAKE_NOW = datetime(2023, 1, 17, 12, 41, 0)  # Jan 17, 2023 12:41:00


@pytest.fixture
def mock_now():
    """Fixture to patch dt_util.now() to a fixed datetime."""
    with patch("homeassistant.util.dt.now") as mock_dt:
        mock_dt.return_value = FAKE_NOW
        yield mock_dt


@pytest.fixture
async def setup_worldclock(hass: HomeAssistant):
    """A helper fixture to set up the combined sensor with a given config."""

    async def _setup(config: dict):
        # This sets up the sensor domain with our custom config
        assert await async_setup_component(
            hass,
            "sensor",
            {"sensor": config},
        )
        await hass.async_block_till_done()

    return _setup


@pytest.mark.asyncio
async def test_basic_setup_no_times(hass: HomeAssistant, setup_worldclock, mock_now):
    """
    Test that the sensor sets up with minimal config (no times).
    Verifies it doesn't crash if time1/time2/time3 are not set.
    """
    config = {
        "platform": "worldclock",
        "time_zone": "Europe/Stockholm",
        # Minimal email config (or partial)
        "sender": "sender@example.com",
        "receiver": "recv@example.com",
        "password": "somepassword",
        # No times for msg1/msg2/msg3
    }

    await setup_worldclock(config)

    # The sensor may be named after 'name' or the default "Worldclock Sensor".
    # If you didn't specify 'name', the entity_id might be sensor.worldclock_sensor
    state = hass.states.get("sensor.my_combined_sensor")
    if state is None:
        state = hass.states.get("sensor.worldclock_sensor")

    assert state is not None, "Sensor should be created even with partial config"
    # We won't test the actual time string here, just that it doesn't crash or fail.


@pytest.mark.asyncio
async def test_no_trigger_when_time_not_matched(
    hass: HomeAssistant, setup_worldclock, mock_now
):
    """
    Test that if the current time does NOT match any configured times,
    there's no email or signal call.
    """
    # Move FAKE_NOW to something that doesn't match 12:41
    mock_now.return_value = FAKE_NOW + timedelta(hours=3)  # e.g., 15:41

    config = {
        "platform": "worldclock",
        "time_zone": "Europe/Stockholm",
        "time1_hour": "12",
        "time1_minute": "41",
        "msg1": "Time+to+have+breakfast",
        "sender": "sender@example.com",
        "receiver": "recv@example.com",
        "password": "somepassword",
        "signal_phone": "somephoneid",
        "signal_apikey": "12345",
    }

    await setup_worldclock(config)

    with (
        patch("smtplib.SMTP", autospec=True) as mock_smtp_cls,
        patch("aiohttp.ClientSession", autospec=True) as mock_session_cls,
    ):
        mock_smtp = mock_smtp_cls.return_value
        mock_smtp.sendmail.return_value = None

        mock_session = mock_session_cls.return_value
        mock_session.get = AsyncMock()

        await hass.helpers.entity_component.async_update_entity(
            "sensor.worldclock_sensor"
        )

        # Because time does not match, no calls
        assert mock_smtp.sendmail.call_count == 0
        assert mock_session.get.call_count == 0


@pytest.mark.asyncio
async def test_time_format(hass: HomeAssistant, setup_worldclock, mock_now):
    """
    Test time_format setting, ensuring sensor state uses that format.
    """
    time_format = "%a, %b %d, %Y %I:%M %p"
    config = {
        "platform": "worldclock",
        "time_zone": "Europe/Stockholm",
        "time_format": time_format,
    }

    await setup_worldclock(config)
    state = hass.states.get("sensor.worldclock_sensor")
    assert state is not None

    expected = FAKE_NOW.strftime(time_format)
    assert state.state == expected


@pytest.mark.asyncio
async def test_custom_name(hass: HomeAssistant, setup_worldclock, mock_now):
    """
    Ensure that if we provide a custom 'name',
    the sensor entity_id is created accordingly.
    """
    config = {
        "platform": "worldclock",
        "time_zone": "Europe/Stockholm",
        "name": "Custom City Sensor",
        # Minimal config
    }

    await setup_worldclock(config)

    # The entity should be "sensor.custom_city_sensor"
    state = hass.states.get("sensor.custom_city_sensor")
    assert state is not None, "Sensor with custom name not created"


@pytest.mark.asyncio
async def test_email_and_signal_config_ignored_if_no_times(
    hass: HomeAssistant, setup_worldclock, mock_now
):
    """
    If we specify email/signal config but do NOT specify any times,
    the sensor won't ever attempt to send anything, and should pass easily.
    """
    config = {
        "platform": "worldclock",
        "time_zone": "Europe/Stockholm",
        "sender": "example@gmail.com",
        "receiver": "receiver@example.com",
        "password": "dummy",
        "signal_phone": "dummyphone",
        "signal_apikey": "dummykey",
        # No time1_hour/time2_hour/time3_hour => no triggers
    }

    await setup_worldclock(config)

    state = hass.states.get("sensor.worldclock_sensor")
    assert state is not None, "Sensor not created"
    