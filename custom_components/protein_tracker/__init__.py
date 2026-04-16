"""Protein Tracker custom integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change

from .const import (
    ATTR_USER_ID,
    CONF_CALORIE_GOAL,
    CONF_GOAL,
    CONF_ID,
    CONF_NAME,
    CONF_USERS,
    DEFAULT_CALORIE_GOAL,
    DATA_ENTRIES,
    DATA_MANAGER,
    DATA_SERVICES_REGISTERED,
    DATA_UNSUB_RESET,
    DEFAULT_GOAL,
    DOMAIN,
    FIELD_CALORIES,
    FIELD_CALORIES_PER_100G,
    FIELD_ENTITY_ID,
    FIELD_FOOD_GRAMS,
    FIELD_GOAL_CALORIES,
    FIELD_GOAL_GRAMS,
    FIELD_GRAMS,
    FIELD_PROTEIN_PER_100G,
    FIELD_USER_ID,
    SERVICE_ADD_CALORIE_FOOD,
    SERVICE_ADD_CALORIES,
    SERVICE_ADD_FOOD,
    SERVICE_ADD_PROTEIN,
    SERVICE_RESET_CALORIES,
    SERVICE_RESET_USER,
    SERVICE_SET_CALORIE_GOAL,
    SERVICE_SET_GOAL,
    STORAGE_KEY,
)
from .manager import ProteinTrackerManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ID): cv.slug,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_GOAL, default=DEFAULT_GOAL): vol.Coerce(float),
        vol.Optional(CONF_CALORIE_GOAL, default=DEFAULT_CALORIE_GOAL): vol.Coerce(float),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERS): vol.All(
                    cv.ensure_list,
                    [USER_SCHEMA],
                    vol.Length(min=1),
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_SCHEMA_ADD_PROTEIN = vol.Schema(
    {
        vol.Optional(FIELD_USER_ID): cv.slug,
        vol.Optional(FIELD_ENTITY_ID): cv.entity_id,
        vol.Required(FIELD_GRAMS): vol.Coerce(float),
    }
)

SERVICE_SCHEMA_ADD_FOOD = vol.Schema(
    {
        vol.Optional(FIELD_USER_ID): cv.slug,
        vol.Optional(FIELD_ENTITY_ID): cv.entity_id,
        vol.Required(FIELD_FOOD_GRAMS): vol.Coerce(float),
        vol.Required(FIELD_PROTEIN_PER_100G): vol.Coerce(float),
    }
)

SERVICE_SCHEMA_ADD_CALORIES = vol.Schema(
    {
        vol.Optional(FIELD_USER_ID): cv.slug,
        vol.Optional(FIELD_ENTITY_ID): cv.entity_id,
        vol.Required(FIELD_CALORIES): vol.Coerce(float),
    }
)

SERVICE_SCHEMA_ADD_CALORIE_FOOD = vol.Schema(
    {
        vol.Optional(FIELD_USER_ID): cv.slug,
        vol.Optional(FIELD_ENTITY_ID): cv.entity_id,
        vol.Required(FIELD_FOOD_GRAMS): vol.Coerce(float),
        vol.Required(FIELD_CALORIES_PER_100G): vol.Coerce(float),
    }
)

SERVICE_SCHEMA_SET_GOAL = vol.Schema(
    {
        vol.Optional(FIELD_USER_ID): cv.slug,
        vol.Optional(FIELD_ENTITY_ID): cv.entity_id,
        vol.Required(FIELD_GOAL_GRAMS): vol.Coerce(float),
    }
)

SERVICE_SCHEMA_SET_CALORIE_GOAL = vol.Schema(
    {
        vol.Optional(FIELD_USER_ID): cv.slug,
        vol.Optional(FIELD_ENTITY_ID): cv.entity_id,
        vol.Required(FIELD_GOAL_CALORIES): vol.Coerce(float),
    }
)

SERVICE_SCHEMA_RESET_USER = vol.Schema(
    {
        vol.Optional(FIELD_USER_ID): cv.slug,
        vol.Optional(FIELD_ENTITY_ID): cv.entity_id,
    }
)

SERVICE_SCHEMA_RESET_CALORIES = vol.Schema(
    {
        vol.Optional(FIELD_USER_ID): cv.slug,
        vol.Optional(FIELD_ENTITY_ID): cv.entity_id,
    }
)

_SENSOR_ENTITY_PATTERN = re.compile(
    rf"^sensor\.(?:{DOMAIN}_)?(?P<id>[a-z0-9_]+?)(?:_(?:today|protein|calories))?(?:_[0-9]+)?$"
)
_NUMBER_ENTITY_PATTERN = re.compile(
    rf"^number\.(?:{DOMAIN}_)?(?P<id>[a-z0-9_]+?)(?:_(?:protein_goal|calorie_goal|calories_goal|protein|calories|goal))?(?:_[0-9]+)?$"
)


def _ensure_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {
            DATA_ENTRIES: {},
            DATA_SERVICES_REGISTERED: False,
        }
    return hass.data[DOMAIN]


def _ensure_target(call_data: dict[str, Any]) -> None:
    if FIELD_USER_ID in call_data or FIELD_ENTITY_ID in call_data:
        return
    raise HomeAssistantError("Provide either 'user_id' or 'entity_id'")


def _resolve_user_id(hass: HomeAssistant, call_data: dict[str, Any]) -> str:
    if FIELD_USER_ID in call_data:
        return str(call_data[FIELD_USER_ID])

    if FIELD_ENTITY_ID not in call_data:
        raise HomeAssistantError("Provide either 'user_id' or 'entity_id'")

    entity_id = str(call_data[FIELD_ENTITY_ID]).strip()
    state = hass.states.get(entity_id)
    if state is not None:
        state_user_id = state.attributes.get(ATTR_USER_ID)
        if isinstance(state_user_id, str) and state_user_id:
            return state_user_id

    sensor_match = _SENSOR_ENTITY_PATTERN.match(entity_id)
    if sensor_match:
        return sensor_match.group("id")

    number_match = _NUMBER_ENTITY_PATTERN.match(entity_id)
    if number_match:
        return number_match.group("id")

    raise HomeAssistantError(
        "entity_id must match sensor.<id>_protein / sensor.<id>_calories "
        "or number.<id>_protein / number.<id>_calories "
        "(or legacy protein_tracker naming)"
    )


def _get_manager_for_user_id(hass: HomeAssistant, user_id: str) -> ProteinTrackerManager:
    domain_data = _ensure_domain_data(hass)
    entries: dict[str, dict[str, Any]] = domain_data[DATA_ENTRIES]

    for entry_data in entries.values():
        manager: ProteinTrackerManager = entry_data[DATA_MANAGER]
        if user_id in manager.user_ids():
            return manager

    raise HomeAssistantError(f"Unknown tracker id '{user_id}'")


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Protein Tracker from YAML and trigger config-entry imports."""
    _ensure_domain_data(hass)

    conf = config.get(DOMAIN)
    if conf is None:
        return True

    seen_ids: set[str] = set()
    for user in conf[CONF_USERS]:
        user_id = user[CONF_ID]
        if user_id in seen_ids:
            _LOGGER.error("Duplicate user id in %s config: %s", DOMAIN, user_id)
            return False
        seen_ids.add(user_id)

        import_data = {
            CONF_ID: user_id,
            CONF_NAME: user.get(CONF_NAME, user_id),
            CONF_GOAL: float(user.get(CONF_GOAL, DEFAULT_GOAL)),
            CONF_CALORIE_GOAL: float(
                user.get(CONF_CALORIE_GOAL, DEFAULT_CALORIE_GOAL)
            ),
        }
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=import_data,
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Protein Tracker from config entry."""
    domain_data = _ensure_domain_data(hass)

    tracker_id = str(entry.data[CONF_ID])
    tracker_name = str(entry.data.get(CONF_NAME, tracker_id))
    goal = float(entry.data.get(CONF_GOAL, DEFAULT_GOAL))
    calorie_goal = float(entry.data.get(CONF_CALORIE_GOAL, DEFAULT_CALORIE_GOAL))

    manager = ProteinTrackerManager(
        hass,
        users_config=[
            {
                CONF_ID: tracker_id,
                CONF_NAME: tracker_name,
                CONF_GOAL: goal,
                CONF_CALORIE_GOAL: calorie_goal,
            }
        ],
        storage_key=f"{STORAGE_KEY}.{tracker_id}",
    )
    await manager.async_initialize()

    async def _handle_day_change(_now) -> None:
        await manager.async_daily_rollover()

    unsub_reset = async_track_time_change(
        hass,
        _handle_day_change,
        hour=0,
        minute=0,
        second=0,
    )

    domain_data[DATA_ENTRIES][entry.entry_id] = {
        DATA_MANAGER: manager,
        DATA_UNSUB_RESET: unsub_reset,
    }

    if not domain_data[DATA_SERVICES_REGISTERED]:
        await _register_services(hass)
        domain_data[DATA_SERVICES_REGISTERED] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Protein Tracker config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    domain_data = _ensure_domain_data(hass)
    entry_data = domain_data[DATA_ENTRIES].pop(entry.entry_id, None)
    if entry_data and DATA_UNSUB_RESET in entry_data:
        entry_data[DATA_UNSUB_RESET]()

    if not domain_data[DATA_ENTRIES] and domain_data[DATA_SERVICES_REGISTERED]:
        for service in (
            SERVICE_ADD_PROTEIN,
            SERVICE_ADD_FOOD,
            SERVICE_ADD_CALORIES,
            SERVICE_ADD_CALORIE_FOOD,
            SERVICE_SET_GOAL,
            SERVICE_SET_CALORIE_GOAL,
            SERVICE_RESET_USER,
            SERVICE_RESET_CALORIES,
        ):
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)
        domain_data[DATA_SERVICES_REGISTERED] = False

    return True


async def _register_services(hass: HomeAssistant) -> None:
    async def handle_add_protein(call: ServiceCall) -> None:
        _ensure_target(call.data)
        user_id = _resolve_user_id(hass, call.data)
        manager = _get_manager_for_user_id(hass, user_id)
        await manager.async_add_protein(
            user_id,
            float(call.data[FIELD_GRAMS]),
        )

    async def handle_add_food(call: ServiceCall) -> None:
        _ensure_target(call.data)
        user_id = _resolve_user_id(hass, call.data)
        manager = _get_manager_for_user_id(hass, user_id)
        await manager.async_add_food(
            user_id,
            float(call.data[FIELD_FOOD_GRAMS]),
            float(call.data[FIELD_PROTEIN_PER_100G]),
        )

    async def handle_add_calories(call: ServiceCall) -> None:
        _ensure_target(call.data)
        user_id = _resolve_user_id(hass, call.data)
        manager = _get_manager_for_user_id(hass, user_id)
        await manager.async_add_calories(
            user_id,
            float(call.data[FIELD_CALORIES]),
        )

    async def handle_add_calorie_food(call: ServiceCall) -> None:
        _ensure_target(call.data)
        user_id = _resolve_user_id(hass, call.data)
        manager = _get_manager_for_user_id(hass, user_id)
        await manager.async_add_calorie_food(
            user_id,
            float(call.data[FIELD_FOOD_GRAMS]),
            float(call.data[FIELD_CALORIES_PER_100G]),
        )

    async def handle_set_goal(call: ServiceCall) -> None:
        _ensure_target(call.data)
        user_id = _resolve_user_id(hass, call.data)
        manager = _get_manager_for_user_id(hass, user_id)
        await manager.async_set_goal(
            user_id,
            float(call.data[FIELD_GOAL_GRAMS]),
        )

    async def handle_set_calorie_goal(call: ServiceCall) -> None:
        _ensure_target(call.data)
        user_id = _resolve_user_id(hass, call.data)
        manager = _get_manager_for_user_id(hass, user_id)
        await manager.async_set_calorie_goal(
            user_id,
            float(call.data[FIELD_GOAL_CALORIES]),
        )

    async def handle_reset_user(call: ServiceCall) -> None:
        _ensure_target(call.data)
        user_id = _resolve_user_id(hass, call.data)
        manager = _get_manager_for_user_id(hass, user_id)
        await manager.async_reset_user(user_id)

    async def handle_reset_calories(call: ServiceCall) -> None:
        _ensure_target(call.data)
        user_id = _resolve_user_id(hass, call.data)
        manager = _get_manager_for_user_id(hass, user_id)
        await manager.async_reset_calories(user_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PROTEIN,
        handle_add_protein,
        schema=SERVICE_SCHEMA_ADD_PROTEIN,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_FOOD,
        handle_add_food,
        schema=SERVICE_SCHEMA_ADD_FOOD,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_CALORIES,
        handle_add_calories,
        schema=SERVICE_SCHEMA_ADD_CALORIES,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_CALORIE_FOOD,
        handle_add_calorie_food,
        schema=SERVICE_SCHEMA_ADD_CALORIE_FOOD,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_GOAL,
        handle_set_goal,
        schema=SERVICE_SCHEMA_SET_GOAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CALORIE_GOAL,
        handle_set_calorie_goal,
        schema=SERVICE_SCHEMA_SET_CALORIE_GOAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_USER,
        handle_reset_user,
        schema=SERVICE_SCHEMA_RESET_USER,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_CALORIES,
        handle_reset_calories,
        schema=SERVICE_SCHEMA_RESET_CALORIES,
    )
