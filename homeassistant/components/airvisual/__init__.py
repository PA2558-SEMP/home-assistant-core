"""The AirVisual component."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from math import ceil
from typing import Any

from pyairvisual.cloud_api import (
    CloudAPI,
    InvalidKeyError,
    KeyExpiredError,
    UnauthorizedError,
)
from pyairvisual.errors import AirVisualError

from homeassistant.components import automation
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_COUNTRY,
    CONF_IP_ADDRESS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SHOW_ON_MAP,
    CONF_STATE,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import (
    aiohttp_client,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_CITY,
    CONF_GEOGRAPHIES,
    CONF_INTEGRATION_TYPE,
    DOMAIN,
    INTEGRATION_TYPE_GEOGRAPHY_COORDS,
    INTEGRATION_TYPE_GEOGRAPHY_NAME,
    INTEGRATION_TYPE_NODE_PRO,
    LOGGER,
)

# We use a raw string for the airvisual_pro domain (instead of importing the actual
# constant) so that we can avoid listing it as a dependency:
DOMAIN_AIRVISUAL_PRO = "airvisual_pro"

PLATFORMS = [Platform.SENSOR]

DEFAULT_ATTRIBUTION = "Data provided by AirVisual"


@callback
def async_get_cloud_api_update_interval(
    hass: HomeAssistant, api_key: str, num_consumers: int
) -> timedelta:
    """Get a leveled scan interval for a particular cloud API key."""
    minutes_between_api_calls = ceil(num_consumers * 31 * 24 * 60 / 8500)

    LOGGER.debug(
        "Leveling API key usage (%s): %s consumers, %s minutes between updates",
        api_key,
        num_consumers,
        minutes_between_api_calls,
    )

    return timedelta(minutes=minutes_between_api_calls)


@callback
def async_get_cloud_coordinators_by_api_key(
    hass: HomeAssistant, api_key: str
) -> list[DataUpdateCoordinator]:
    """Get all DataUpdateCoordinator objects related to a particular API key."""
    return [
        coordinator
        for entry_id, coordinator in hass.data[DOMAIN].items()
        if (entry := hass.config_entries.async_get_entry(entry_id))
        and entry.data.get(CONF_API_KEY) == api_key
    ]


@callback
def async_get_geography_id(geography_dict: Mapping[str, Any]) -> str:
    """Generate a unique ID from a geography dict."""
    if CONF_CITY in geography_dict:
        return ", ".join(
            (
                geography_dict[CONF_CITY],
                geography_dict[CONF_STATE],
                geography_dict[CONF_COUNTRY],
            )
        )
    return ", ".join(
        (str(geography_dict[CONF_LATITUDE]), str(geography_dict[CONF_LONGITUDE]))
    )


@callback
def async_sync_geo_coordinator_update_intervals(
    hass: HomeAssistant, api_key: str
) -> None:
    """Sync the update interval for geography-based data coordinators (by API key)."""
    coordinators = async_get_cloud_coordinators_by_api_key(hass, api_key)
    if not coordinators:
        return

    update_interval = async_get_cloud_api_update_interval(hass, api_key, len(coordinators))
    for coordinator in coordinators:
        LOGGER.debug(
            "Updating interval for coordinator: %s, %s",
            coordinator.name,
            update_interval,
        )
        coordinator.update_interval = update_interval


@callback
def _standardize_geography_config_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Ensure that geography config entries have appropriate properties."""
    entry_updates = {}

    if not entry.unique_id:
        entry_updates["unique_id"] = entry.data[CONF_API_KEY]
    if not entry.options:
        entry_updates["options"] = {CONF_SHOW_ON_MAP: True}
    if entry.data.get(CONF_INTEGRATION_TYPE) not in [
        INTEGRATION_TYPE_GEOGRAPHY_COORDS,
        INTEGRATION_TYPE_GEOGRAPHY_NAME,
    ]:
        entry_updates["data"] = {**entry.data}
        if CONF_CITY in entry.data:
            entry_updates["data"][CONF_INTEGRATION_TYPE] = INTEGRATION_TYPE_GEOGRAPHY_NAME
        else:
            entry_updates["data"][CONF_INTEGRATION_TYPE] = INTEGRATION_TYPE_GEOGRAPHY_COORDS

    if entry_updates:
        hass.config_entries.async_update_entry(entry, **entry_updates)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AirVisual as config entry."""
    if CONF_API_KEY not in entry.data:
        # If this is a migrated AirVisual Pro entry, there's no actual setup to do;
        # that will be handled by the `airvisual_pro` domain:
        return False

    _standardize_geography_config_entry(hass, entry)

    websession = aiohttp_client.async_get_clientsession(hass)
    cloud_api = CloudAPI(entry.data[CONF_API_KEY], session=websession)

    async def async_update_data() -> dict[str, Any]:
        """Get new data from the API."""
        if CONF_CITY in entry.data:
            api_coro = cloud_api.air_quality.city(
                entry.data[CONF_CITY],
                entry.data[CONF_STATE],
                entry.data[CONF_COUNTRY],
            )
        else:
            api_coro = cloud_api.air_quality.nearest_city(
                entry.data[CONF_LATITUDE],
                entry.data[CONF_LONGITUDE],
            )

        try:
            return await api_coro
        except (InvalidKeyError, KeyExpiredError, UnauthorizedError) as ex:
            raise ConfigEntryAuthFailed from ex
        except AirVisualError as err:
            raise UpdateFailed(f"Error while retrieving data: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name=async_get_geography_id(entry.data),
        update_interval=timedelta(minutes=5),
        update_method=async_update_data,
    )

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    async_sync_geo_coordinator_update_intervals(hass, entry.data[CONF_API_KEY])
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry."""
    version = entry.version
    LOGGER.debug("Migrating from version %s", version)

    if version == 1:
        await _migrate_v1_to_v2(hass, entry)
        version = 2

    elif version == 2:
        await _migrate_v2_to_v3(hass, entry)
        version = 3

    LOGGER.info("Migration to version %s successful", version)
    return True


async def _migrate_v1_to_v2(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle the migration from version 1 to 2 (one geography per config entry)."""
    geographies = list(entry.data[CONF_GEOGRAPHIES])
    first_geography = geographies.pop(0)
    first_id = async_get_geography_id(first_geography)

    hass.config_entries.async_update_entry(
        entry,
        unique_id=first_id,
        title=f"Cloud API ({first_id})",
        data={CONF_API_KEY: entry.data[CONF_API_KEY], **first_geography},
        version=2,
    )

    for geography in geographies:
        if CONF_LATITUDE in geography:
            source = "geography_by_coords"
        else:
            source = "geography_by_name"

        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data={
                    "import_source": source,
                    CONF_API_KEY: entry.data[CONF_API_KEY],
                    **geography,
                },
            )
        )


async def _migrate_v2_to_v3(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle the migration from version 2 to 3 (move AirVisual Pro to its own domain)."""
    if entry.data[CONF_INTEGRATION_TYPE] == INTEGRATION_TYPE_NODE_PRO:
        await _migrate_v2_to_v3_node_pro(hass, entry)
    else:
        hass.config_entries.async_update_entry(entry, version=3)


async def _migrate_v2_to_v3_node_pro(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle migrating an AirVisual Pro device to the 'airvisual_pro' domain."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    ip_address = entry.data[CONF_IP_ADDRESS]

    old_device_entry = next(
        d_entry
        for d_entry in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    )

    old_entity_entries: dict[str, er.RegistryEntry] = {
        e_entry.unique_id: e_entry
        for e_entry in er.async_entries_for_device(
            entity_registry, old_device_entry.id, include_disabled_entities=True
        )
    }

    new_entry_data = {**entry.data}
    new_entry_data.pop(CONF_INTEGRATION_TYPE)

    hass.async_create_background_task(
        hass.config_entries.async_remove(entry.entry_id),
        name=f"remove config legacy airvisual entry {entry.title}",
    )
    await hass.config_entries.flow.async_init(
        DOMAIN_AIRVISUAL_PRO,
        context={"source": SOURCE_IMPORT},
        data=new_entry_data,
    )

    new_config_entry = next(
        c_entry
        for c_entry in hass.config_entries.async_entries(DOMAIN_AIRVISUAL_PRO)
        if c_entry.data[CONF_IP_ADDRESS] == ip_address
    )
    new_device_entry = next(
        d_entry
        for d_entry in dr.async_entries_for_config_entry(
            device_registry, new_config_entry.entry_id
        )
    )

    device_registry.async_update_device(
        new_device_entry.id,
        area_id=old_device_entry.area_id,
        disabled_by=old_device_entry.disabled_by,
        name_by_user=old_device_entry.name_by_user,
    )

    for new_entity_entry in er.async_entries_for_device(
        entity_registry, new_device_entry.id, include_disabled_entities=True
    ):
        if old_entity_entry := old_entity_entries.get(new_entity_entry.unique_id):
            entity_registry.async_update_entity(
                new_entity_entry.entity_id,
                area_id=old_entity_entry.area_id,
                device_class=old_entity_entry.device_class,
                disabled_by=old_entity_entry.disabled_by,
                hidden_by=old_entity_entry.hidden_by,
                icon=old_entity_entry.icon,
                name=old_entity_entry.name,
                new_entity_id=old_entity_entry.entity_id,
                unit_of_measurement=old_entity_entry.unit_of_measurement,
            )

    if device_automations := automation.automations_with_device(
        hass, old_device_entry.id
    ):
        async_create_issue(
            hass,
            DOMAIN,
            f"airvisual_pro_migration_{entry.entry_id}",
            is_fixable=False,
            is_persistent=True,
            severity=IssueSeverity.WARNING,
            translation_key="airvisual_pro_migration",
            translation_placeholders={
                "ip_address": ip_address,
                "old_device_id": old_device_entry.id,
                "new_device_id": new_device_entry.id,
                "device_automations_string": ", ".join(
                    f"`{automation}`" for automation in device_automations
                ),
            },
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an AirVisual config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if CONF_API_KEY in entry.data:
            async_sync_geo_coordinator_update_intervals(hass, entry.data[CONF_API_KEY])
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle an options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class AirVisualEntity(CoordinatorEntity):
    """Define a generic AirVisual entity."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        description: EntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_extra_state_attributes = {}
        self._entry = entry
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()

        @callback
        def update() -> None:
            """Update the state."""
            self.update_from_latest_data()
            self.async_write_ha_state()

        self.async_on_remove(self.coordinator.async_add_listener(update))
        self.update_from_latest_data()

    @callback
    def update_from_latest_data(self) -> None:
        """Update the entity from the latest data."""
        raise NotImplementedError
