"""Number platform for Protein Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CALORIE_GOAL,
    ATTR_GOAL,
    ATTR_TRACKER_TYPE,
    ATTR_USER_ID,
    CONF_NAME,
    DATA_ENTRIES,
    DATA_MANAGER,
    DOMAIN,
    TRACKER_TYPE_CALORIES,
    TRACKER_TYPE_PROTEIN,
)
from .manager import ProteinTrackerManager
from .naming import base_display_name, calorie_goal_display_name, goal_display_name

UNIT_KILOCALORIES = "kcal"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Protein Tracker number entities."""
    manager: ProteinTrackerManager = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id][DATA_MANAGER]
    entities = []
    for user_id in manager.user_ids():
        entities.append(ProteinGoalNumber(manager, user_id))
        entities.append(CalorieGoalNumber(manager, user_id))
    async_add_entities(entities)


class ProteinGoalNumber(CoordinatorEntity[ProteinTrackerManager], NumberEntity):
    """Daily protein goal number for one user."""

    _attr_icon = "mdi:target"
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX
    _attr_has_entity_name = False

    def __init__(self, manager: ProteinTrackerManager, user_id: str) -> None:
        super().__init__(manager)
        self._user_id = user_id
        self._attr_unique_id = f"{DOMAIN}_{user_id}_goal"
        self._attr_object_id = f"{user_id}_protein"

    async def async_added_to_hass(self) -> None:
        """Ensure stable entity_id format number.<configured_id>_protein."""
        await super().async_added_to_hass()
        if self.hass is None:
            return

        desired_entity_id = f"number.{self._user_id}_protein"
        registry = er.async_get(self.hass)
        current_entity_id = registry.async_get_entity_id("number", DOMAIN, self.unique_id)
        if current_entity_id is None or current_entity_id == desired_entity_id:
            return
        if registry.async_get(desired_entity_id) is not None:
            return

        registry.async_update_entity(current_entity_id, new_entity_id=desired_entity_id)

    @property
    def name(self) -> str:
        """Return entity name."""
        state = self.coordinator.user_state(self._user_id)
        return goal_display_name(str(state[CONF_NAME]))

    @property
    def native_value(self) -> float:
        """Return goal in grams."""
        return self.coordinator.user_state(self._user_id)[ATTR_GOAL]

    async def async_set_native_value(self, value: float) -> None:
        """Set new goal value."""
        await self.coordinator.async_set_goal(self._user_id, value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes used by service targeting helpers."""
        return {
            ATTR_USER_ID: self._user_id,
            ATTR_TRACKER_TYPE: TRACKER_TYPE_PROTEIN,
        }

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info so user entities are grouped."""
        state = self.coordinator.user_state(self._user_id)
        return {
            "identifiers": {(DOMAIN, self._user_id)},
            "name": base_display_name(str(state[CONF_NAME])),
            "manufacturer": "Custom",
            "model": "Nutrition Tracker",
        }


class CalorieGoalNumber(CoordinatorEntity[ProteinTrackerManager], NumberEntity):
    """Daily calorie goal number for one user."""

    _attr_icon = "mdi:target"
    _attr_native_unit_of_measurement = UNIT_KILOCALORIES
    _attr_native_min_value = 0.0
    _attr_native_max_value = 10000.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX
    _attr_has_entity_name = False

    def __init__(self, manager: ProteinTrackerManager, user_id: str) -> None:
        super().__init__(manager)
        self._user_id = user_id
        self._attr_unique_id = f"{DOMAIN}_{user_id}_calorie_goal"
        self._attr_object_id = f"{user_id}_calories"

    async def async_added_to_hass(self) -> None:
        """Ensure stable entity_id format number.<configured_id>_calories."""
        await super().async_added_to_hass()
        if self.hass is None:
            return

        desired_entity_id = f"number.{self._user_id}_calories"
        registry = er.async_get(self.hass)
        current_entity_id = registry.async_get_entity_id("number", DOMAIN, self.unique_id)
        if current_entity_id is None or current_entity_id == desired_entity_id:
            return
        if registry.async_get(desired_entity_id) is not None:
            return

        registry.async_update_entity(current_entity_id, new_entity_id=desired_entity_id)

    @property
    def name(self) -> str:
        """Return entity name."""
        state = self.coordinator.user_state(self._user_id)
        return calorie_goal_display_name(str(state[CONF_NAME]))

    @property
    def native_value(self) -> float:
        """Return calorie goal."""
        return self.coordinator.user_state(self._user_id)[ATTR_CALORIE_GOAL]

    async def async_set_native_value(self, value: float) -> None:
        """Set new goal value."""
        await self.coordinator.async_set_calorie_goal(self._user_id, value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes used by service targeting helpers."""
        return {
            ATTR_USER_ID: self._user_id,
            ATTR_TRACKER_TYPE: TRACKER_TYPE_CALORIES,
        }

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info so user entities are grouped."""
        state = self.coordinator.user_state(self._user_id)
        return {
            "identifiers": {(DOMAIN, self._user_id)},
            "name": base_display_name(str(state[CONF_NAME])),
            "manufacturer": "Custom",
            "model": "Nutrition Tracker",
        }
