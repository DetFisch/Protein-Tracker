"""Runtime state manager for Protein Tracker."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CALORIE_GOAL,
    ATTR_CALORIES_PROGRESS_PERCENT,
    ATTR_CALORIES_REMAINING,
    ATTR_CALORIES_TODAY_TOTAL,
    ATTR_DATE,
    ATTR_GOAL,
    ATTR_PROGRESS_PERCENT,
    ATTR_REMAINING,
    ATTR_TODAY_TOTAL,
    CONF_CALORIE_GOAL,
    CONF_GOAL,
    CONF_ID,
    CONF_NAME,
    CONF_USERS,
    DEFAULT_CALORIE_GOAL,
    DEFAULT_GOAL,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class ProteinTrackerManager(DataUpdateCoordinator[dict[str, Any]]):
    """Manage Protein Tracker state and persistence."""

    def __init__(
        self,
        hass: HomeAssistant,
        users_config: list[dict[str, Any]],
        storage_key: str | None = None,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, storage_key or STORAGE_KEY)
        self._users_config = users_config
        self._data: dict[str, Any] = {CONF_USERS: {}}

    async def async_initialize(self) -> None:
        """Load persisted state and merge configured users."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._data = stored

        users = self._data.setdefault(CONF_USERS, {})
        today = self._today_key()

        configured_ids: set[str] = set()
        for user_conf in self._users_config:
            user_id = user_conf[CONF_ID]
            configured_ids.add(user_id)

            existing = users.get(user_id, {})
            users[user_id] = {
                CONF_ID: user_id,
                CONF_NAME: user_conf.get(CONF_NAME, user_id),
                CONF_GOAL: float(existing.get(CONF_GOAL, user_conf.get(CONF_GOAL, DEFAULT_GOAL))),
                CONF_CALORIE_GOAL: float(
                    existing.get(
                        CONF_CALORIE_GOAL,
                        user_conf.get(CONF_CALORIE_GOAL, DEFAULT_CALORIE_GOAL),
                    )
                ),
                ATTR_TODAY_TOTAL: float(existing.get(ATTR_TODAY_TOTAL, 0.0)),
                ATTR_CALORIES_TODAY_TOTAL: float(existing.get(ATTR_CALORIES_TODAY_TOTAL, 0.0)),
                ATTR_DATE: str(existing.get(ATTR_DATE, today)),
                "history": existing.get("history", []),
            }

        # Remove users that are no longer configured.
        for existing_user_id in list(users):
            if existing_user_id not in configured_ids:
                users.pop(existing_user_id, None)

        changed = self._rollover_if_needed(today)

        if changed:
            await self._save()

        self.async_set_updated_data(self._public_data())

    def user_ids(self) -> list[str]:
        """Return configured user ids."""
        return list(self._data[CONF_USERS])

    def user_state(self, user_id: str) -> dict[str, Any]:
        """Return public state for a specific user."""
        users = self._public_data()[CONF_USERS]
        if user_id not in users:
            raise HomeAssistantError(f"Unknown user_id '{user_id}'")
        return users[user_id]

    async def async_daily_rollover(self) -> None:
        """Roll users to a new day if needed."""
        today = self._today_key()
        if not self._rollover_if_needed(today):
            return

        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_add_protein(self, user_id: str, grams: float) -> None:
        """Add protein in grams for one user."""
        if grams <= 0:
            raise HomeAssistantError("grams must be > 0")

        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[ATTR_TODAY_TOTAL] = float(user[ATTR_TODAY_TOTAL]) + float(grams)
        
        # Record history
        history = user.setdefault("history", [])
        history.append({"protein": float(grams), "calories": 0.0})
        # Keep only last 20 entries
        user["history"] = history[-20:]

        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_add_food(
        self,
        user_id: str,
        food_grams: float,
        protein_per_100g: float,
    ) -> float:
        """Calculate protein from food amount and add it."""
        if food_grams <= 0:
            raise HomeAssistantError("food_grams must be > 0")
        if protein_per_100g <= 0:
            raise HomeAssistantError("protein_per_100g must be > 0")

        grams = (food_grams * protein_per_100g) / 100.0
        
        # We need to record this as a combined entry if we want to undo it correctly,
        # but the card might call add_food and then add_calorie_food separately if they are separate metrics.
        # Actually, in ProteinTrackerCard._handleAddFood, it calls them separately.
        # So we should just handle them as separate history entries.
        await self.async_add_protein(user_id, grams)
        return grams

    async def async_set_goal(self, user_id: str, goal_grams: float) -> None:
        """Set protein goal for one user."""
        if goal_grams < 0:
            raise HomeAssistantError("goal_grams must be >= 0")

        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[CONF_GOAL] = float(goal_grams)

        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_add_calories(self, user_id: str, calories: float) -> None:
        """Add calories for one user."""
        if calories <= 0:
            raise HomeAssistantError("calories must be > 0")

        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[ATTR_CALORIES_TODAY_TOTAL] = float(user[ATTR_CALORIES_TODAY_TOTAL]) + float(calories)

        # Record history
        history = user.setdefault("history", [])
        history.append({"protein": 0.0, "calories": float(calories)})
        # Keep only last 20 entries
        user["history"] = history[-20:]

        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_add_calorie_food(
        self,
        user_id: str,
        food_grams: float,
        calories_per_100g: float,
    ) -> float:
        """Calculate calories from food amount and add them."""
        if food_grams <= 0:
            raise HomeAssistantError("food_grams must be > 0")
        if calories_per_100g <= 0:
            raise HomeAssistantError("calories_per_100g must be > 0")

        calories = (food_grams * calories_per_100g) / 100.0
        await self.async_add_calories(user_id, calories)
        return calories

    async def async_set_calorie_goal(self, user_id: str, goal_calories: float) -> None:
        """Set calorie goal for one user."""
        if goal_calories < 0:
            raise HomeAssistantError("goal_calories must be >= 0")

        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[CONF_CALORIE_GOAL] = float(goal_calories)

        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_undo(self, user_id: str) -> None:
        """Undo the last added entry."""
        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        history = user.get("history", [])
        
        if not history:
            raise HomeAssistantError("No history to undo")
            
        last_entry = history.pop()
        user[ATTR_TODAY_TOTAL] = max(0.0, float(user[ATTR_TODAY_TOTAL]) - float(last_entry.get("protein", 0.0)))
        user[ATTR_CALORIES_TODAY_TOTAL] = max(0.0, float(user[ATTR_CALORIES_TODAY_TOTAL]) - float(last_entry.get("calories", 0.0)))
        
        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_reset_user(self, user_id: str) -> None:
        """Reset current-day protein for one user to 0."""
        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[ATTR_TODAY_TOTAL] = 0.0
        user["history"] = []

        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_reset_calories(self, user_id: str) -> None:
        """Reset current-day calories for one user to 0."""
        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[ATTR_CALORIES_TODAY_TOTAL] = 0.0
        user["history"] = []

        await self._save()
        self.async_set_updated_data(self._public_data())

    def _rollover_if_needed(self, today: str) -> bool:
        changed = False
        for user in self._data[CONF_USERS].values():
            if str(user[ATTR_DATE]) == today:
                continue

            user[ATTR_DATE] = today
            user[ATTR_TODAY_TOTAL] = 0.0
            user[ATTR_CALORIES_TODAY_TOTAL] = 0.0
            changed = True

        return changed

    async def _save(self) -> None:
        await self._store.async_save(self._data)

    def _public_data(self) -> dict[str, Any]:
        users: dict[str, Any] = {}
        for user_id, user in self._data[CONF_USERS].items():
            today_total = float(user[ATTR_TODAY_TOTAL])
            goal = float(user[CONF_GOAL])
            remaining = max(goal - today_total, 0.0)
            progress_percent = 0.0 if goal <= 0 else min((today_total / goal) * 100.0, 999.0)
            calories_today_total = float(user[ATTR_CALORIES_TODAY_TOTAL])
            calorie_goal = float(user[CONF_CALORIE_GOAL])
            calories_remaining = max(calorie_goal - calories_today_total, 0.0)
            calories_progress_percent = (
                0.0
                if calorie_goal <= 0
                else min((calories_today_total / calorie_goal) * 100.0, 999.0)
            )

            users[user_id] = {
                CONF_ID: user_id,
                CONF_NAME: str(user[CONF_NAME]),
                ATTR_DATE: str(user[ATTR_DATE]),
                ATTR_TODAY_TOTAL: round(today_total, 2),
                CONF_GOAL: round(goal, 2),
                ATTR_REMAINING: round(remaining, 2),
                ATTR_PROGRESS_PERCENT: round(progress_percent, 2),
                ATTR_CALORIES_TODAY_TOTAL: round(calories_today_total, 2),
                CONF_CALORIE_GOAL: round(calorie_goal, 2),
                ATTR_CALORIES_REMAINING: round(calories_remaining, 2),
                ATTR_CALORIES_PROGRESS_PERCENT: round(calories_progress_percent, 2),
            }

        return {CONF_USERS: users}

    def _get_user(self, user_id: str) -> dict[str, Any]:
        users = self._data[CONF_USERS]
        if user_id not in users:
            raise HomeAssistantError(f"Unknown user_id '{user_id}'")
        return users[user_id]

    @staticmethod
    def _today_key() -> str:
        return dt_util.now().date().isoformat()
