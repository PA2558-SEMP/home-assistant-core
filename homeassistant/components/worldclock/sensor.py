"""Support for sending both Email and Signal messages at specific times,
with reminder times taken from input_datetime, dynamic time zone from
input_select.timezone, dynamic email addresses from input_text.email_sender/receiver,
and dynamic messages from input_text.reminder_message_1/2/3.
"""

from __future__ import annotations

import logging
import aiohttp
import smtplib
from email.mime.text import MIMEText
from datetime import tzinfo

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_NAME, CONF_TIME_ZONE
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.dt as dt_util
from urllib.parse import quote_plus

_LOGGER = logging.getLogger(__name__)

CONF_TIME_FORMAT = "time_format"

# Email config
CONF_SENDER = "sender"
CONF_RECEIVER = "receiver"
CONF_PASSWORD = "password"
CONF_SMTP_SERVER = "smtp_server"
CONF_SMTP_PORT = "smtp_port"

# Signal config
CONF_SIGNAL_PHONE = "signal_phone"
CONF_SIGNAL_APIKEY = "signal_apikey"

# Reminder messages (YAML fallback)
CONF_MSG1 = "msg1"
CONF_MSG2 = "msg2"
CONF_MSG3 = "msg3"

DEFAULT_NAME = "Worldclock Sensor"
DEFAULT_TIME_STR_FORMAT = "%H:%M"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_TIME_ZONE): cv.time_zone,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_TIME_FORMAT, default=DEFAULT_TIME_STR_FORMAT): cv.string,
        # Email fallback
        vol.Optional(CONF_SENDER): cv.string,
        vol.Optional(CONF_RECEIVER): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SMTP_SERVER, default="smtp.gmail.com"): cv.string,
        vol.Optional(CONF_SMTP_PORT, default=587): cv.positive_int,
        # Signal fallback
        vol.Optional(CONF_SIGNAL_PHONE): cv.string,
        vol.Optional(CONF_SIGNAL_APIKEY): cv.string,
        # Fallback messages
        vol.Optional(CONF_MSG1): cv.string,
        vol.Optional(CONF_MSG2): cv.string,
        vol.Optional(CONF_MSG3): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the combined Email+Signal sensor with dynamic times, zone, addresses, messages."""
    fallback_tz = dt_util.get_time_zone(config[CONF_TIME_ZONE])
    name = config.get(CONF_NAME)
    time_format = config.get(CONF_TIME_FORMAT)

    # Fallback email & signal
    fallback_sender = config.get(CONF_SENDER)
    fallback_receiver = config.get(CONF_RECEIVER)
    password = config.get(CONF_PASSWORD)
    smtp_server = config.get(CONF_SMTP_SERVER)
    smtp_port = config.get(CONF_SMTP_PORT)

    # Fallback signal
    signal_phone = config.get(CONF_SIGNAL_PHONE)
    signal_apikey = config.get(CONF_SIGNAL_APIKEY)

    # Fallback messages
    msg1 = config.get(CONF_MSG1)
    msg2 = config.get(CONF_MSG2)
    msg3 = config.get(CONF_MSG3)

    async_add_entities(
        [
            CombinedWorldClockSensor(
                hass,
                fallback_tz,
                name,
                time_format,
                fallback_sender,
                fallback_receiver,
                password,
                smtp_server,
                smtp_port,
                signal_phone,
                signal_apikey,
                msg1,
                msg2,
                msg3,
            )
        ],
        True,
    )


class CombinedWorldClockSensor(SensorEntity):
    """World clock sensor that triggers Email & Signal at user-specified times/messages."""

    _attr_icon = "mdi:clock"

    def __init__(
        self,
        hass: HomeAssistant,
        fallback_tz: tzinfo | None,
        name: str,
        time_format: str,
        fallback_sender: str | None,
        fallback_receiver: str | None,
        password: str | None,
        smtp_server: str,
        smtp_port: int,
        signal_phone: str | None,
        signal_apikey: str | None,
        msg1: str | None,
        msg2: str | None,
        msg3: str | None,
    ):
        """Store fallback config and placeholders."""
        self.hass = hass
        self._fallback_tz = fallback_tz
        self._attr_name = name
        self._time_format = time_format

        self._fallback_sender = fallback_sender
        self._fallback_receiver = fallback_receiver
        self._password = password
        self._smtp_server = smtp_server
        self._smtp_port = smtp_port

        self._signal_phone = signal_phone
        self._signal_apikey = signal_apikey

        # Fallback messages if user hasn't set or if input_text is blank
        self._fallback_msg1 = msg1 or "Time to have breakfast"
        self._fallback_msg2 = msg2 or "Time to have lunch"
        self._fallback_msg3 = msg3 or "Time to rest and sleep"

        # We'll track triggers per-minute to allow multiple triggers in same day
        self._time1_last_minute = None
        self._time2_last_minute = None
        self._time3_last_minute = None

    async def async_update(self) -> None:
        """
        1) Dynamic time zone from input_select.timezone (fallback to YAML).
        2) Dynamic email addresses from input_text.email_sender, input_text.email_receiver.
        3) Dynamic messages from input_text.reminder_message_1, etc. (fallback to YAML).
        4) Compare current time to input_datetime.reminder_timeX. Fire once/minute if matched.
        """
        # ---- TIME ZONE ----
        dynamic_tz = self._fallback_tz
        tz_state = self.hass.states.get("input_select.timezone")
        if tz_state and tz_state.state not in ("unknown", "unavailable"):
            chosen_zone = dt_util.get_time_zone(tz_state.state)
            if chosen_zone:
                dynamic_tz = chosen_zone

        now_tz = dt_util.now(time_zone=dynamic_tz)
        self._attr_native_value = now_tz.strftime(self._time_format)

        hour = now_tz.hour
        minute = now_tz.minute

        # ---- EMAIL SENDER/RECEIVER ----
        sender = self._fallback_sender
        receiver = self._fallback_receiver

        sender_state = self.hass.states.get("input_text.email_sender")
        if sender_state and sender_state.state not in ("unknown", "unavailable"):
            if sender_state.state.strip():
                sender = sender_state.state.strip()

        receiver_state = self.hass.states.get("input_text.email_receiver")
        if receiver_state and receiver_state.state not in ("unknown", "unavailable"):
            if receiver_state.state.strip():
                receiver = receiver_state.state.strip()

        # ---- MESSAGES from input_text or fallback ----
        # If user sets input_text.reminder_message_1, we use that; else fallback
        msg1 = (
            self._get_custom_message("input_text.reminder_message_1")
            or self._fallback_msg1
        )
        msg2 = (
            self._get_custom_message("input_text.reminder_message_2")
            or self._fallback_msg2
        )
        msg3 = (
            self._get_custom_message("input_text.reminder_message_3")
            or self._fallback_msg3
        )

        # ---- TIMES from input_datetime ----
        r1_hour, r1_minute = self._get_reminder_time("input_datetime.reminder_time1")
        r2_hour, r2_minute = self._get_reminder_time("input_datetime.reminder_time2")
        r3_hour, r3_minute = self._get_reminder_time("input_datetime.reminder_time3")

        # ---- Compare current hour/minute to each reminder ----
        # Once per minute logic
        if r1_hour is not None and r1_minute is not None and msg1:
            if hour == r1_hour and minute == r1_minute:
                if self._time1_last_minute != (hour, minute):
                    await self._send_both("Time1 Reminder", msg1, sender, receiver)
                    self._time1_last_minute = (hour, minute)
            else:
                self._time1_last_minute = None

        if r2_hour is not None and r2_minute is not None and msg2:
            if hour == r2_hour and minute == r2_minute:
                if self._time2_last_minute != (hour, minute):
                    await self._send_both("Time2 Reminder", msg2, sender, receiver)
                    self._time2_last_minute = (hour, minute)
            else:
                self._time2_last_minute = None

        if r3_hour is not None and r3_minute is not None and msg3:
            if hour == r3_hour and minute == r3_minute:
                if self._time3_last_minute != (hour, minute):
                    await self._send_both("Time3 Reminder", msg3, sender, receiver)
                    self._time3_last_minute = (hour, minute)
            else:
                self._time3_last_minute = None

    def _get_custom_message(self, entity_id: str) -> str | None:
        """Return the user-set text from an input_text, or None if not set."""
        state_obj = self.hass.states.get(entity_id)
        if not state_obj or state_obj.state in ("unknown", "unavailable"):
            return None
        textval = state_obj.state.strip()
        return textval if textval else None

    def _get_reminder_time(self, entity_id: str) -> tuple[int | None, int | None]:
        """Retrieve HH,MM from an input_datetime (HH:MM:SS)."""
        state_obj = self.hass.states.get(entity_id)
        if not state_obj or state_obj.state in ("unknown", "unavailable"):
            return None, None
        try:
            parts = state_obj.state.split(":")
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
        except Exception as e:
            _LOGGER.error("Error parsing time from %s: %s", entity_id, e)
        return None, None

    async def _send_both(
        self, subject: str, message: str, sender: str, receiver: str
    ) -> None:
        """Send both an email and a Signal message if config is present."""
        if sender and receiver and self._password:
            await self._send_email(subject, message, sender, receiver)
        if self._signal_phone and self._signal_apikey:
            await self._send_signal(message)

    async def _send_email(
        self, subject: str, body: str, sender: str, receiver: str
    ) -> None:
        """Send an email via SMTP."""
        try:
            server = smtplib.SMTP(self._smtp_server, self._smtp_port)
            server.starttls()
            server.login(sender, self._password)

            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = receiver

            server.sendmail(sender, receiver, msg.as_string())
            server.quit()
            _LOGGER.info("Email sent to %s (subject: %s)", receiver, subject)
        except Exception as exc:
            _LOGGER.error("Error sending email: %s", exc)

    async def _send_signal(self, body: str) -> None:
        """Send a Signal message via CallMeBot API."""
        try:
            encoded_body = quote_plus(body)
            base_url = "https://signal.callmebot.com/signal/send.php"
            api_url = f"{base_url}?phone={self._signal_phone}&apikey={self._signal_apikey}&text={encoded_body}"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        response_text = await response.text()
                        _LOGGER.info("Signal response: %s", response_text)
                    else:
                        _LOGGER.error(
                            "Signal request failed with status: %s", response.status
                        )
        except Exception as exc:
            _LOGGER.error("Error sending Signal message: %s", exc)
