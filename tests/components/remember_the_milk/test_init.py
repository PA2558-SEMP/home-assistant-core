"""Tests for the Remember The Milk component."""

from unittest.mock import Mock, mock_open, patch

import homeassistant.components.remember_the_milk as rtm
from homeassistant.core import Event, HomeAssistant

from .const import JSON_STRING, PROFILE, TOKEN


def test_create_new(hass: HomeAssistant) -> None:
    """Test creating a new config file."""
    with (
        patch("builtins.open", mock_open()),
        patch("os.path.isfile", Mock(return_value=False)),
        patch.object(rtm.RememberTheMilkConfiguration, "save_config"),
    ):
        config = rtm.RememberTheMilkConfiguration(hass)
        config.set_token(PROFILE, TOKEN)
    assert config.get_token(PROFILE) == TOKEN


def test_load_config(hass: HomeAssistant) -> None:
    """Test loading an existing token from the file."""
    with (
        patch("builtins.open", mock_open(read_data=JSON_STRING)),
        patch("os.path.isfile", Mock(return_value=True)),
    ):
        config = rtm.RememberTheMilkConfiguration(hass)
    assert config.get_token(PROFILE) == TOKEN


def test_invalid_data(hass: HomeAssistant) -> None:
    """Test starts with invalid data and should not raise an exception."""
    with (
        patch("builtins.open", mock_open(read_data="random characters")),
        patch("os.path.isfile", Mock(return_value=True)),
    ):
        config = rtm.RememberTheMilkConfiguration(hass)
    assert config is not None


def test_id_map(hass: HomeAssistant) -> None:
    """Test the hass to rtm task is mapping."""
    hass_id = "hass-id-1234"
    list_id = "mylist"
    timeseries_id = "my_timeseries"
    rtm_id = "rtm-id-4567"
    with (
        patch("builtins.open", mock_open()),
        patch("os.path.isfile", Mock(return_value=False)),
        patch.object(rtm.RememberTheMilkConfiguration, "save_config"),
    ):
        config = rtm.RememberTheMilkConfiguration(hass)

        assert config.get_rtm_id(PROFILE, hass_id) is None
        config.set_rtm_id(PROFILE, hass_id, list_id, timeseries_id, rtm_id)
        assert (list_id, timeseries_id, rtm_id) == config.get_rtm_id(PROFILE, hass_id)
        config.delete_rtm_id(PROFILE, hass_id)
        assert config.get_rtm_id(PROFILE, hass_id) is None


def test_load_key_map(hass: HomeAssistant) -> None:
    """Test loading an existing key map from the file."""
    with (
        patch("builtins.open", mock_open(read_data=JSON_STRING)),
        patch("os.path.isfile", Mock(return_value=True)),
    ):
        config = rtm.RememberTheMilkConfiguration(hass)
    assert config.get_rtm_id(PROFILE, "1234") == ("0", "1", "2")


def test_handle_zone_leave_home_zone(hass: HomeAssistant) -> None:
    """Test handle_zone_leave triggers notify_tasks_due_today on leaving home zone."""
    mock_rtm_entity = Mock()
    account_name = "test_account"
    hass.data = {"remember_the_milk": {account_name: mock_rtm_entity}}

    event_data = {
        "event_data": {"zone": "zone.home", "entity_id": "device_tracker.myphone"}
    }
    event = Event("zone.leave", event_data)

    rtm.handle_zone_leave(event, hass, account_name)
    mock_rtm_entity.notify_tasks_due_today.assert_called_once()


def test_handle_zone_leave_non_home_zone(hass: HomeAssistant) -> None:
    """Test handle_zone_leave does nothing when leaving a non-home zone."""
    mock_rtm_entity = Mock()
    account_name = "test_account"
    hass.data = {"remember_the_milk": {account_name: mock_rtm_entity}}

    event_data = {
        "event_data": {"zone": "zone.work", "entity_id": "device_tracker.myphone"}
    }
    event = Event("zone.leave", event_data)

    rtm.handle_zone_leave(event, hass, account_name)
    mock_rtm_entity.notify_tasks_due_today.assert_not_called()
