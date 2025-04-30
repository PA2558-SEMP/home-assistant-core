"""Calendar platform for a Local Calendar."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from aiohttp import ClientConnectionError, ClientError
from ical.calendar import Calendar
from ical.calendar_stream import IcsCalendarStream
from ical.event import Event
from ical.exceptions import CalendarParseError
from ical.store import EventStore, EventStoreError
from ical.types import Range, Recur
import voluptuous as vol

from homeassistant.components.calendar import (
    EVENT_END,
    EVENT_RRULE,
    EVENT_START,
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_CALENDAR_NAME, CONF_URL_NAME, DOMAIN
from .store import LocalCalendarStore

_LOGGER = logging.getLogger(__name__)

PRODID = "-//homeassistant.io//local_calendar 1.0//EN"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the local calendar platform."""
    store = hass.data[DOMAIN][config_entry.entry_id]
    url = None
    if CONF_URL_NAME not in config_entry.data:
        ics = await store.async_load()
    else:
        url = config_entry.data[CONF_URL_NAME]
        session = async_get_clientsession(hass)
        try:
            async with session.get(url) as response:
                ics = await response.text()
        except ClientConnectionError:
            _LOGGER.error("Connection error while fetching data from API")
        except ClientError as e:
            _LOGGER.error("Client error occurred: %s", e)

    calendar: Calendar = await hass.async_add_executor_job(
        IcsCalendarStream.calendar_from_ics, ics
    )
    calendar.prodid = PRODID

    name = config_entry.data[CONF_CALENDAR_NAME]

    entity: LocalCalendarEntity | IcsCalendarEntity
    if not url:
        entity = LocalCalendarEntity(
            store, calendar, name, unique_id=config_entry.entry_id
        )
    else:
        entity = IcsCalendarEntity(
            calendar, name, unique_id=config_entry.entry_id, url=url
        )

    async_add_entities([entity], True)


class BaseClass:
    """Base Class for these calendar entities, contains shared code."""

    def __init__(self, calendar: Calendar) -> None:
        """Initialize variables."""
        self._calendar = calendar
        self._event: CalendarEvent | None = None

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        return self._event

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Get all events in a specific time frame."""
        return _return_events(self._calendar, start_date, end_date)

    async def async_update(self) -> None:
        """Update entity state with the next upcoming event."""
        self._event = _return_next_event(self._calendar)


class LocalCalendarEntity(BaseClass, CalendarEntity):
    """A calendar entity backed by a local iCalendar file."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT
        | CalendarEntityFeature.DELETE_EVENT
        | CalendarEntityFeature.UPDATE_EVENT
    )

    def __init__(
        self,
        store: LocalCalendarStore,
        calendar: Calendar,
        name: str,
        unique_id: str,
    ) -> None:
        """Initialize LocalCalendarEntity."""
        self._store = store
        self._attr_name = name
        self._attr_unique_id = unique_id
        super().__init__(calendar)

    async def _async_store(self) -> None:
        """Persist the calendar to disk."""
        content = IcsCalendarStream.calendar_to_ics(self._calendar)
        await self._store.async_store(content)

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add a new event to calendar."""
        event = _parse_event(kwargs)
        EventStore(self._calendar).add(event)
        await self._async_store()
        await self.async_update_ha_state(force_refresh=True)

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Delete an event on the calendar."""
        range_value: Range = Range.NONE
        if recurrence_range == Range.THIS_AND_FUTURE:
            range_value = Range.THIS_AND_FUTURE
        try:
            EventStore(self._calendar).delete(
                uid,
                recurrence_id=recurrence_id,
                recurrence_range=range_value,
            )
        except EventStoreError as err:
            raise HomeAssistantError(f"Error while deleting event: {err}") from err
        await self._async_store()
        await self.async_update_ha_state(force_refresh=True)

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Update an existing event on the calendar."""
        new_event = _parse_event(event)
        range_value: Range = Range.NONE
        if recurrence_range == Range.THIS_AND_FUTURE:
            range_value = Range.THIS_AND_FUTURE
        try:
            EventStore(self._calendar).edit(
                uid,
                new_event,
                recurrence_id=recurrence_id,
                recurrence_range=range_value,
            )
        except EventStoreError as err:
            raise HomeAssistantError(f"Error while updating event: {err}") from err
        await self._async_store()
        await self.async_update_ha_state(force_refresh=True)


def _parse_event(event: dict[str, Any]) -> Event:
    """Parse an ical event from a home assistant event dictionary."""
    if rrule := event.get(EVENT_RRULE):
        event[EVENT_RRULE] = Recur.from_rrule(rrule)

    # This function is called with new events created in the local timezone,
    # however ical library does not properly return recurrence_ids for
    # start dates with a timezone. For now, ensure any datetime is stored as a
    # floating local time to ensure we still apply proper local timezone rules.
    # This can be removed when ical is updated with a new recurrence_id format
    # https://github.com/home-assistant/core/issues/87759
    for key in (EVENT_START, EVENT_END):
        if (
            (value := event[key])
            and isinstance(value, datetime)
            and value.tzinfo is not None
        ):
            event[key] = dt_util.as_local(value).replace(tzinfo=None)

    try:
        return Event(**event)
    except CalendarParseError as err:
        _LOGGER.debug("Error parsing event input fields: %s (%s)", event, str(err))
        raise vol.Invalid("Error parsing event input fields") from err


def _get_calendar_event(event: Event) -> CalendarEvent:
    """Return a CalendarEvent from an API event."""
    start: datetime | date
    end: datetime | date
    if isinstance(event.start, datetime) and isinstance(event.end, datetime):
        start = dt_util.as_local(event.start)
        end = dt_util.as_local(event.end)
        if (end - start) <= timedelta(seconds=0):
            end = start + timedelta(minutes=30)
    else:
        start = event.start
        end = event.end
        if (end - start) < timedelta(days=0):
            end = start + timedelta(days=1)

    return CalendarEvent(
        summary=event.summary,
        start=start,
        end=end,
        description=event.description,
        uid=event.uid,
        rrule=event.rrule.as_rrule_str() if event.rrule else None,
        recurrence_id=event.recurrence_id,
        location=event.location,
    )


class IcsCalendarEntity(BaseClass, CalendarEntity):
    """A calendar entity backed by an .ics file on the network."""

    def __init__(
        self,
        calendar: Calendar,
        name: str,
        unique_id: str,
        url: str,
    ) -> None:
        """Initialize IcsCalendarEntity."""
        self._attr_name = name
        self._attr_unique_id = unique_id
        super().__init__(calendar)


def _return_next_event(_calendar: Calendar) -> CalendarEvent | None:
    """Return the next upcoming event."""
    now = dt_util.now()
    events = _calendar.timeline_tz(now.tzinfo).active_after(now)
    if event := next(events, None):
        return _get_calendar_event(event)
    return None


def _return_events(
    _calendar: Calendar, start_date: datetime, end_date: datetime
) -> list[CalendarEvent]:
    """Return all events in the time range."""
    events = _calendar.timeline_tz(start_date.tzinfo).overlapping(start_date, end_date)
    return [_get_calendar_event(event) for event in events]
