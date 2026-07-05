"""The Centero integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.device_registry as dr

from .api import CenteroAPI, CenteroApiError
from .const import DOMAIN, LOGGER, PLATFORMS
from .coordinator import CenteroCoordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Centero component."""

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Centero from a config entry."""

    host = entry.data[CONF_HOST]

    session = async_get_clientsession(hass)
    api = CenteroAPI(session, host)

    #
    # Fetch gateway information.
    #
    try:
        info = await api.get_info()

    except CenteroApiError as err:
        raise ConfigEntryNotReady(
            f"Failed to connect to Centero gateway {host}: {err}"
        ) from err

    gateway_info = info.get("XC_SUC", {})

    LOGGER.info(
        "Connected to Centero gateway '%s' (%s)",
        gateway_info.get("name"),
        gateway_info.get("mac"),
    )

    #
    # Create coordinator.
    #
    coordinator = CenteroCoordinator(
        hass=hass,
        api=api,
    )

    #
    # Initial refresh.
    #
    try:
        await coordinator.async_config_entry_first_refresh()

    except Exception as err:
        raise ConfigEntryNotReady(f"Initial Centero refresh failed: {err}") from err

    LOGGER.info(
        "Discovered %d ER devices",
        len(coordinator.data),
    )

    for device in coordinator.data.values():
        LOGGER.info(
            "Discovered cover: sid=%s adr=%s state=%s",
            device["sid"],
            device["adr"],
            device["state"],
        )

    #
    # Register gateway device.
    #
    device_registry = dr.async_get(hass)

    gateway_mac = gateway_info.get("mac", host)

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, gateway_mac)},
        manufacturer="Elero",
        model=gateway_info.get("mhv"),
        sw_version=gateway_info.get("mfv"),
        name=gateway_info.get("name", "Centero Gateway"),
    )

    #
    # Store runtime data.
    #
    hass.data.setdefault(DOMAIN, {})

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "gateway_info": gateway_info,
    }

    #
    # Load platforms.
    #
    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    LOGGER.info("Centero setup completed")

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok
