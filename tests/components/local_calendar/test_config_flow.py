"""Test the Local Calendar config flow."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.components.local_calendar.const import (
    CONF_CALENDAR_NAME,
    CONF_STORAGE_KEY,
    CONF_URL_NAME,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry


async def test_form(hass: HomeAssistant) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] is None

    with patch(
        "homeassistant.components.local_calendar.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_CALENDAR_NAME: "My Calendar",
            },
        )
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is None
        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_CALENDAR_NAME: "My ICS Calendar",
                CONF_URL_NAME: "ICS url link",
            },
        )
        await hass.async_block_till_done()
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "My Calendar"
    assert result2["data"] == {
        CONF_CALENDAR_NAME: "My Calendar",
        CONF_STORAGE_KEY: "my_calendar",
    }

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == "My ICS Calendar"
    assert result3["data"] == {
        CONF_CALENDAR_NAME: "My ICS Calendar",
        CONF_STORAGE_KEY: "my_ics_calendar",
        CONF_URL_NAME: "ICS url link",
    }

    assert len(mock_setup_entry.mock_calls) == 2


async def test_duplicate_name(
    hass: HomeAssistant, setup_integration: None, config_entry: MockConfigEntry
) -> None:
    """Test two calendars cannot be added with the same name."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert not result.get("errors")

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            # Pick a name that has the same slugify value as an existing config entry
            CONF_CALENDAR_NAME: "light schedule",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
