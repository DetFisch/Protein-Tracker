"""Sensor platform for Protein Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CALORIE_GOAL,
    ATTR_CALORIES_PROGRESS_PERCENT,
    ATTR_CALORIES_REMAINING,
    ATTR_CALORIES_TODAY_TOTAL,
    ATTR_DATE,
    ATTR_GOAL,
    ATTR_PROGRESS_PERCENT,
    ATTR_REMAINING,
    ATTR_TRACKER_TYPE,
    ATTR_TODAY_TOTAL,
    ATTR_USER_ID,
    CONF_NAME,
    DATA_ENTRIES,
    DATA_MANAGER,
    DOMAIN,
    TRACKER_TYPE_CALORIES,
    TRACKER_TYPE_PROTEIN,
)
from .manager import ProteinTrackerManager
from .naming import base_display_name, calorie_tracker_display_name, tracker_display_name

UNIT_KILOCALORIES = "kcal"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Protein Tracker sensor entities."""
    manager: ProteinTrackerManager = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id][DATA_MANAGER]
    entities = []
    for user_id in manager.user_ids():
        entities.append(ProteinTodaySensor(manager, user_id))
        entities.append(CalorieTodaySensor(manager, user_id))
    async_add_entities(entities)


class ProteinTodaySensor(CoordinatorEntity[ProteinTrackerManager], SensorEntity):
    """Current-day protein sensor for one user."""

    _attr_icon = "mdi:food-steak"
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_has_entity_name = False

    def __init__(self, manager: ProteinTrackerManager, user_id: str) -> None:
        super().__init__(manager)
        self._user_id = user_id
        self._attr_unique_id = f"{DOMAIN}_{user_id}_today"
        self._attr_object_id = f"{user_id}_protein"

    async def async_added_to_hass(self) -> None:
        """Ensure stable entity_id format sensor.<configured_id>_protein."""
        await super().async_added_to_hass()
        if self.hass is None:
            return

        desired_entity_id = f"sensor.{self._user_id}_protein"
        registry = er.async_get(self.hass)
        current_entity_id = registry.async_get_entity_id("sensor", DOMAIN, self.unique_id)
        if current_entity_id is None or current_entity_id == desired_entity_id:
            return
        if registry.async_get(desired_entity_id) is not None:
            return

        registry.async_update_entity(current_entity_id, new_entity_id=desired_entity_id)

    @property
    def name(self) -> str:
        """Return entity name."""
        state = self.coordinator.user_state(self._user_id)
        return tracker_display_name(str(state[CONF_NAME]))

    @property
    def native_value(self) -> float:
        """Return today's consumed protein grams."""
        state = self.coordinator.user_state(self._user_id)
        return state[ATTR_TODAY_TOTAL]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        state = self.coordinator.user_state(self._user_id)
        return {
            ATTR_USER_ID: self._user_id,
            ATTR_TRACKER_TYPE: TRACKER_TYPE_PROTEIN,
            ATTR_GOAL: state[ATTR_GOAL],
            ATTR_REMAINING: state[ATTR_REMAINING],
            ATTR_PROGRESS_PERCENT: state[ATTR_PROGRESS_PERCENT],
            ATTR_DATE: state[ATTR_DATE],
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


class CalorieTodaySensor(CoordinatorEntity[ProteinTrackerManager], SensorEntity):
    """Current-day calorie sensor for one user."""

    _attr_icon = "mdi:fire"
    _attr_native_unit_of_measurement = UNIT_KILOCALORIES
    _attr_has_entity_name = False

    def __init__(self, manager: ProteinTrackerManager, user_id: str) -> None:
        super().__init__(manager)
        self._user_id = user_id
        self._attr_unique_id = f"{DOMAIN}_{user_id}_calories_today"
        self._attr_object_id = f"{user_id}_calories"

    async def async_added_to_hass(self) -> None:
        """Ensure stable entity_id format sensor.<configured_id>_calories."""
        await super().async_added_to_hass()
        if self.hass is None:
            return

        desired_entity_id = f"sensor.{self._user_id}_calories"
        registry = er.async_get(self.hass)
        current_entity_id = registry.async_get_entity_id("sensor", DOMAIN, self.unique_id)
        if current_entity_id is None or current_entity_id == desired_entity_id:
            return
        if registry.async_get(desired_entity_id) is not None:
            return

        registry.async_update_entity(current_entity_id, new_entity_id=desired_entity_id)

    @property
    def name(self) -> str:
        """Return entity name."""
        state = self.coordinator.user_state(self._user_id)
        return calorie_tracker_display_name(str(state[CONF_NAME]))

    @property
    def native_value(self) -> float:
        """Return today's consumed calories."""
        state = self.coordinator.user_state(self._user_id)
        return state[ATTR_CALORIES_TODAY_TOTAL]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        state = self.coordinator.user_state(self._user_id)
        return {
            ATTR_USER_ID: self._user_id,
            ATTR_TRACKER_TYPE: TRACKER_TYPE_CALORIES,
            ATTR_GOAL: state[ATTR_CALORIE_GOAL],
            ATTR_REMAINING: state[ATTR_CALORIES_REMAINING],
            ATTR_PROGRESS_PERCENT: state[ATTR_CALORIES_PROGRESS_PERCENT],
            ATTR_DATE: state[ATTR_DATE],
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
