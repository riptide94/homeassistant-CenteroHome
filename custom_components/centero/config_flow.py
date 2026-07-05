"""Config flow for Centero."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CenteroAPI, CenteroApiError
from .const import DOMAIN, LOGGER


class CenteroConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Centero."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""

        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = CenteroAPI(session, host)

            try:
                info = await api.get_info()

            except CenteroApiError:
                LOGGER.error("Failed to connect to Centero gateway %s", host)
                errors["base"] = "cannot_connect"

            else:
                gateway_info = info["XC_SUC"]
                LOGGER.info(
                    "Connected to Centero gateway '%s' (%s)",
                    gateway_info.get("name"),
                    gateway_info.get("mac"),
                )

                return self.async_create_entry(
                    title=gateway_info.get("name", host),
                    data={
                        CONF_HOST: host,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                }
            ),
            errors=errors,
        )
