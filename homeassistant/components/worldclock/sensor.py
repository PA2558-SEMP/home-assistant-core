"""Support for sending both Email and Signal messages at specific times."""

from __future__ import annotations

import logging
import aiohttp
import smtplib
from email.mime.text import MIMEText
from datetime import tzinfo, date

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_NAME, CONF_TIME_ZONE
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Existing config keys
CONF_TIME_FORMAT = "time_format"

# Email config
CONF_SENDER = "sender"
CONF_RECEIVER = "receiver"
CONF_PASSWORD = "password"
CONF_SMTP_SERVER = "smtp_server"  # e.g. smtp.gmail.com
CONF_SMTP_PORT = "smtp_port"  # e.g. 587

# Signal config
CONF_SIGNAL_PHONE = "signal_phone"  # callmebot phone or unique ID
CONF_SIGNAL_APIKEY = "signal_apikey"  # callmebot apikey

# Times & messages
CONF_TIME1_HOUR = "time1_hour"
CONF_TIME1_MINUTE = "time1_minute"
CONF_MSG1 = "msg1"

CONF_TIME2_HOUR = "time2_hour"
CONF_TIME2_MINUTE = "time2_minute"
CONF_MSG2 = "msg2"

CONF_TIME3_HOUR = "time3_hour"
CONF_TIME3_MINUTE = "time3_minute"
CONF_MSG3 = "msg3"

DEFAULT_NAME = "Worldclock Sensor"
DEFAULT_TIME_STR_FORMAT = "%H:%M"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_TIME_ZONE): cv.time_zone,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_TIME_FORMAT, default=DEFAULT_TIME_STR_FORMAT): cv.string,
        # Email config
        vol.Optional(CONF_SENDER): cv.string,
        vol.Optional(CONF_RECEIVER): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SMTP_SERVER, default="smtp.gmail.com"): cv.string,
        vol.Optional(CONF_SMTP_PORT, default=587): cv.positive_int,
        # Signal config
        vol.Optional(CONF_SIGNAL_PHONE): cv.string,
        vol.Optional(CONF_SIGNAL_APIKEY): cv.string,
        # Time/message 1
        vol.Optional(CONF_TIME1_HOUR): cv.string,
        vol.Optional(CONF_TIME1_MINUTE): cv.string,
        vol.Optional(CONF_MSG1): cv.string,
        # Time/message 2
        vol.Optional(CONF_TIME2_HOUR): cv.string,
        vol.Optional(CONF_TIME2_MINUTE): cv.string,
        vol.Optional(CONF_MSG2): cv.string,
        # Time/message 3
        vol.Optional(CONF_TIME3_HOUR): cv.string,
        vol.Optional(CONF_TIME3_MINUTE): cv.string,
        vol.Optional(CONF_MSG3): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the combined email + Signal sensor."""
    time_zone = dt_util.get_time_zone(config[CONF_TIME_ZONE])
    name = config.get(CONF_NAME)
    time_format = config.get(CONF_TIME_FORMAT)

    # Email
    sender = config.get(CONF_SENDER)
    receiver = config.get(CONF_RECEIVER)
    password = config.get(CONF_PASSWORD)
    smtp_server = config.get(CONF_SMTP_SERVER)
    smtp_port = config.get(CONF_SMTP_PORT)

    # Signal
    signal_phone = config.get(CONF_SIGNAL_PHONE)
    signal_apikey = config.get(CONF_SIGNAL_APIKEY)

    # Times + messages
    time1_hour = config.get(CONF_TIME1_HOUR)
    time1_minute = config.get(CONF_TIME1_MINUTE)
    msg1 = config.get(CONF_MSG1)

    time2_hour = config.get(CONF_TIME2_HOUR)
    time2_minute = config.get(CONF_TIME2_MINUTE)
    msg2 = config.get(CONF_MSG2)

    time3_hour = config.get(CONF_TIME3_HOUR)
    time3_minute = config.get(CONF_TIME3_MINUTE)
    msg3 = config.get(CONF_MSG3)

    async_add_entities(
        [
            CombinedWorldClockSensor(
                time_zone,
                name,
                time_format,
                sender,
                receiver,
                password,
                smtp_server,
                smtp_port,
                signal_phone,
                signal_apikey,
                time1_hour,
                time1_minute,
                msg1,
                time2_hour,
                time2_minute,
                msg2,
                time3_hour,
                time3_minute,
                msg3,
            )
        ],
        True,
    )


class CombinedWorldClockSensor(SensorEntity):
    """Representation of a World clock sensor that sends both email & Signal messages."""

    _attr_icon = "mdi:clock"

    def __init__(
        self,
        time_zone: tzinfo | None,
        name: str,
        time_format: str,
        sender: str | None,
        receiver: str | None,
        password: str | None,
        smtp_server: str,
        smtp_port: int,
        signal_phone: str | None,
        signal_apikey: str | None,
        time1_hour: str | None,
        time1_minute: str | None,
        msg1: str | None,
        time2_hour: str | None,
        time2_minute: str | None,
        msg2: str | None,
        time3_hour: str | None,
        time3_minute: str | None,
        msg3: str | None,
    ) -> None:
        """Initialize the sensor and store config."""
        self._attr_name = name
        self._time_zone = time_zone
        self._time_format = time_format

        self._sender = sender
        self._receiver = receiver
        self._password = password
        self._smtp_server = smtp_server
        self._smtp_port = smtp_port

        self._signal_phone = signal_phone
        self._signal_apikey = signal_apikey

        self._time1_hour = time1_hour
        self._time1_minute = time1_minute
        self._msg1 = msg1

        self._time2_hour = time2_hour
        self._time2_minute = time2_minute
        self._msg2 = msg2

        self._time3_hour = time3_hour
        self._time3_minute = time3_minute
        self._msg3 = msg3

        # Flags to ensure each time triggers only once per day
        self._time1_sent_date = None
        self._time2_sent_date = None
        self._time3_sent_date = None

    async def async_update(self) -> None:
        """Check the current time and send messages if matched."""
        now_tz = dt_util.now(time_zone=self._time_zone)
        self._attr_native_value = now_tz.strftime(self._time_format)

        current_hour = now_tz.hour
        current_minute = now_tz.minute
        today = now_tz.date()

        # 1) Check time1
        if self._time1_hour and self._time1_minute and self._msg1:
            if int(current_hour) == int(self._time1_hour) and int(
                current_minute
            ) == int(self._time1_minute):
                if self._time1_sent_date != today:
                    await self._send_both("Time1 Reminder", self._msg1)
                    self._time1_sent_date = today

        # 2) Check time2
        if self._time2_hour and self._time2_minute and self._msg2:
            if int(current_hour) == int(self._time2_hour) and int(
                current_minute
            ) == int(self._time2_minute):
                if self._time2_sent_date != today:
                    await self._send_both("Time2 Reminder", self._msg2)
                    self._time2_sent_date = today

        # 3) Check time3
        if self._time3_hour and self._time3_minute and self._msg3:
            if int(current_hour) == int(self._time3_hour) and int(
                current_minute
            ) == int(self._time3_minute):
                if self._time3_sent_date != today:
                    await self._send_both("Time3 Reminder", self._msg3)
                    self._time3_sent_date = today

    async def _send_both(self, subject: str, message: str) -> None:
        """Send both an email (if configured) and a Signal message (if configured)."""
        # 1) Send email if config is present
        if self._sender and self._receiver and self._password:
            await self._send_email(subject, message)

        # 2) Send signal if config is present
        if self._signal_phone and self._signal_apikey:
            await self._send_signal(message)

    async def _send_email(self, subject: str, body: str) -> None:
        """Send an email via SMTP."""
        try:
            server = smtplib.SMTP(self._smtp_server, self._smtp_port)
            server.starttls()
            server.login(self._sender, self._password)

            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self._sender
            msg["To"] = self._receiver

            server.sendmail(self._sender, self._receiver, msg.as_string())
            server.quit()

            _LOGGER.info("Email sent: %s", subject)
        except Exception as exc:
            _LOGGER.error("Error sending email: %s", exc)

    async def _send_signal(self, body: str) -> None:
        """Send a Signal message via callmebot."""
        try:
            # If your phone or ID has hyphens, keep them or remove them as callmebot suggests
            # If your message has spaces, you might need to replace them with '+' or URL-encode
            # E.g. "Hello+World" or use urllib.parse.quote_plus(body)
            base_url = "https://signal.callmebot.com/signal/send.php"
            api_url = f"{base_url}?phone={self._signal_phone}&apikey={self._signal_apikey}&text={body}"

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
