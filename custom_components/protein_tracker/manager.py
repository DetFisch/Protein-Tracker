"""Runtime state manager for Protein Tracker."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

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
    ATTR_CREATED_AT,
    ATTR_DATE,
    ATTR_ENTRY_ID,
    ATTR_ENTRY_NAME,
    ATTR_GOAL,
    ATTR_HISTORY,
    ATTR_PROGRESS_PERCENT,
    ATTR_REMAINING,
    ATTR_TEMPLATES,
    ATTR_TEMPLATE_TYPE,
    ATTR_TODAY_TOTAL,
    ATTR_PROTEIN_PER_100G,
    ATTR_CALORIES_PER_100G,
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
        changed = False
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
                ATTR_HISTORY: existing.get(ATTR_HISTORY, []),
                ATTR_TEMPLATES: existing.get(ATTR_TEMPLATES, []),
            }
            changed = self._normalize_history(users[user_id], today) or changed
            changed = self._normalize_templates(users[user_id]) or changed
            changed = self._sync_missing_templates_from_history(users[user_id]) or changed

        # Remove users that are no longer configured.
        for existing_user_id in list(users):
            if existing_user_id not in configured_ids:
                users.pop(existing_user_id, None)

        changed = self._rollover_if_needed(today) or changed

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

    async def async_add_entry(
        self,
        user_id: str,
        protein: float = 0.0,
        calories: float = 0.0,
        entry_name: str | None = None,
        food_grams: float | None = None,
        protein_per_100g: float | None = None,
        calories_per_100g: float | None = None,
    ) -> None:
        """Add both protein and calories in a single atomic history entry."""
        if float(protein) <= 0 and float(calories) <= 0:
            raise HomeAssistantError("At least one value must be > 0")

        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[ATTR_TODAY_TOTAL] = float(user[ATTR_TODAY_TOTAL]) + float(protein)
        user[ATTR_CALORIES_TODAY_TOTAL] = (
            float(user[ATTR_CALORIES_TODAY_TOTAL]) + float(calories)
        )

        # Record as ONE history entry
        history = user.setdefault(ATTR_HISTORY, [])
        entry = {
            ATTR_ENTRY_ID: uuid4().hex,
            "protein": float(protein),
            "calories": float(calories),
            ATTR_CREATED_AT: dt_util.now().isoformat(),
        }
        normalized_name = self._normalize_entry_name(entry_name)
        if normalized_name:
            entry[ATTR_ENTRY_NAME] = normalized_name
            if (
                food_grams is not None
                and float(food_grams) > 0
                and (
                    (protein_per_100g is not None and float(protein_per_100g) > 0)
                    or (calories_per_100g is not None and float(calories_per_100g) > 0)
                )
            ):
                self._upsert_template(
                    user,
                    normalized_name,
                    float(protein),
                    float(calories),
                    template_type="per_100g",
                    protein_per_100g=float(protein_per_100g or 0.0),
                    calories_per_100g=float(calories_per_100g or 0.0),
                )
            else:
                self._upsert_template(
                    user,
                    normalized_name,
                    float(protein),
                    float(calories),
                    template_type="fixed",
                )
        history.append(entry)
        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_add_protein(
        self, user_id: str, grams: float, entry_name: str | None = None
    ) -> None:
        """Add protein in grams for one user."""
        await self.async_add_entry(user_id, protein=grams, entry_name=entry_name)

    async def async_add_food(
        self,
        user_id: str,
        food_grams: float,
        protein_per_100g: float,
        entry_name: str | None = None,
    ) -> float:
        """Calculate protein from food amount and add it."""
        if food_grams <= 0:
            raise HomeAssistantError("food_grams must be > 0")
        if protein_per_100g <= 0:
            raise HomeAssistantError("protein_per_100g must be > 0")

        grams = (food_grams * protein_per_100g) / 100.0
        await self.async_add_entry(
            user_id,
            protein=grams,
            entry_name=entry_name,
            food_grams=food_grams,
            protein_per_100g=protein_per_100g,
        )
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

    async def async_add_calories(
        self, user_id: str, calories: float, entry_name: str | None = None
    ) -> None:
        """Add calories for one user."""
        await self.async_add_entry(user_id, calories=calories, entry_name=entry_name)

    async def async_add_calorie_food(
        self,
        user_id: str,
        food_grams: float,
        calories_per_100g: float,
        entry_name: str | None = None,
    ) -> float:
        """Calculate calories from food amount and add them."""
        if food_grams <= 0:
            raise HomeAssistantError("food_grams must be > 0")
        if calories_per_100g <= 0:
            raise HomeAssistantError("calories_per_100g must be > 0")

        calories = (food_grams * calories_per_100g) / 100.0
        await self.async_add_entry(
            user_id,
            calories=calories,
            entry_name=entry_name,
            food_grams=food_grams,
            calories_per_100g=calories_per_100g,
        )
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
        history = user.get(ATTR_HISTORY, [])
        
        if not history:
            raise HomeAssistantError("No history to undo")
            
        last_entry = history.pop()
        user[ATTR_TODAY_TOTAL] = max(0.0, float(user[ATTR_TODAY_TOTAL]) - float(last_entry.get("protein", 0.0)))
        user[ATTR_CALORIES_TODAY_TOTAL] = max(0.0, float(user[ATTR_CALORIES_TODAY_TOTAL]) - float(last_entry.get("calories", 0.0)))
        
        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_delete_entry(self, user_id: str, entry_id: str) -> None:
        """Delete a specific history entry and subtract its values."""
        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        history = user.get(ATTR_HISTORY, [])

        today = self._today_key()
        for index, entry in enumerate(history):
            if not self._entry_is_today(entry, today):
                continue
            if str(entry.get(ATTR_ENTRY_ID, "")) != str(entry_id):
                continue

            removed = history.pop(index)
            user[ATTR_TODAY_TOTAL] = max(
                0.0,
                float(user[ATTR_TODAY_TOTAL]) - float(removed.get("protein", 0.0)),
            )
            user[ATTR_CALORIES_TODAY_TOTAL] = max(
                0.0,
                float(user[ATTR_CALORIES_TODAY_TOTAL])
                - float(removed.get("calories", 0.0)),
            )

            await self._save()
            self.async_set_updated_data(self._public_data())
            return

        raise HomeAssistantError("Entry not found")

    async def async_delete_template(self, user_id: str, entry_name: str) -> None:
        """Delete a reusable entry template by name."""
        user = self._get_user(user_id)
        normalized_name = self._normalize_entry_name(entry_name)
        template_key = self._template_key(normalized_name)
        if not template_key:
            raise HomeAssistantError("Template name is required")

        templates = user.get(ATTR_TEMPLATES, [])
        kept_templates = [
            template
            for template in templates
            if not isinstance(template, dict)
            or self._template_key(template.get(ATTR_ENTRY_NAME, "")) != template_key
        ]
        if len(kept_templates) == len(templates):
            raise HomeAssistantError("Template not found")

        user[ATTR_TEMPLATES] = kept_templates
        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_reset_user(self, user_id: str) -> None:
        """Reset current-day protein for one user to 0."""
        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[ATTR_TODAY_TOTAL] = 0.0
        user[ATTR_HISTORY] = []

        await self._save()
        self.async_set_updated_data(self._public_data())

    async def async_reset_calories(self, user_id: str) -> None:
        """Reset current-day calories for one user to 0."""
        self._rollover_if_needed(self._today_key())
        user = self._get_user(user_id)
        user[ATTR_CALORIES_TODAY_TOTAL] = 0.0
        user[ATTR_HISTORY] = []

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
            user[ATTR_HISTORY] = []
            changed = True

        return changed

    def _normalize_history(self, user: dict[str, Any], today: str) -> bool:
        """Keep only today's dated history entries and ensure they have IDs."""
        history = user.get(ATTR_HISTORY, [])
        if not isinstance(history, list):
            user[ATTR_HISTORY] = []
            return True

        changed = False
        normalized = []
        for entry in history:
            if not isinstance(entry, dict):
                changed = True
                continue
            if not self._entry_is_today(entry, today):
                changed = True
                continue

            normalized_entry = {
                ATTR_ENTRY_ID: str(entry.get(ATTR_ENTRY_ID) or uuid4().hex),
                "protein": float(entry.get("protein", 0.0)),
                "calories": float(entry.get("calories", 0.0)),
                ATTR_CREATED_AT: str(entry.get(ATTR_CREATED_AT, "")),
            }
            normalized_name = self._normalize_entry_name(entry.get(ATTR_ENTRY_NAME))
            if normalized_name:
                normalized_entry[ATTR_ENTRY_NAME] = normalized_name
            changed = changed or normalized_entry != entry
            normalized.append(normalized_entry)

        if len(normalized) != len(history):
            changed = True

        user[ATTR_HISTORY] = normalized
        return changed

    def _normalize_templates(self, user: dict[str, Any]) -> bool:
        """Normalize persisted entry templates and deduplicate by name."""
        templates = user.get(ATTR_TEMPLATES, [])
        if not isinstance(templates, list):
            user[ATTR_TEMPLATES] = []
            return True

        changed = False
        by_name: dict[str, dict[str, Any]] = {}
        for template in templates:
            if not isinstance(template, dict):
                changed = True
                continue

            normalized_name = self._normalize_entry_name(template.get(ATTR_ENTRY_NAME))
            template_type = self._normalize_template_type(template.get(ATTR_TEMPLATE_TYPE))
            protein = float(template.get("protein", 0.0))
            calories = float(template.get("calories", 0.0))
            protein_per_100g = float(template.get(ATTR_PROTEIN_PER_100G, 0.0))
            calories_per_100g = float(template.get(ATTR_CALORIES_PER_100G, 0.0))

            if template_type == "per_100g":
                is_empty = protein_per_100g <= 0 and calories_per_100g <= 0
            else:
                is_empty = protein <= 0 and calories <= 0

            if not normalized_name or is_empty:
                changed = True
                continue

            normalized_template = {
                ATTR_ENTRY_NAME: normalized_name,
                "protein": protein,
                "calories": calories,
                ATTR_TEMPLATE_TYPE: template_type,
                ATTR_CREATED_AT: str(template.get(ATTR_CREATED_AT, "")),
            }
            if template_type == "per_100g":
                normalized_template[ATTR_PROTEIN_PER_100G] = protein_per_100g
                normalized_template[ATTR_CALORIES_PER_100G] = calories_per_100g

            by_name[self._template_key(normalized_name)] = normalized_template
            changed = changed or normalized_template != template

        normalized = sorted(by_name.values(), key=lambda item: str(item[ATTR_ENTRY_NAME]).casefold())
        if normalized != templates:
            changed = True

        user[ATTR_TEMPLATES] = normalized
        return changed

    def _upsert_template(
        self,
        user: dict[str, Any],
        entry_name: str,
        protein: float,
        calories: float,
        template_type: str = "fixed",
        protein_per_100g: float = 0.0,
        calories_per_100g: float = 0.0,
    ) -> None:
        """Store the latest values for a named entry as a reusable template."""
        normalized_type = self._normalize_template_type(template_type)
        if normalized_type == "per_100g":
            if protein_per_100g <= 0 and calories_per_100g <= 0:
                return
        elif protein <= 0 and calories <= 0:
            return

        template = {
            ATTR_ENTRY_NAME: entry_name,
            "protein": float(protein),
            "calories": float(calories),
            ATTR_TEMPLATE_TYPE: normalized_type,
            ATTR_CREATED_AT: dt_util.now().isoformat(),
        }
        if normalized_type == "per_100g":
            template[ATTR_PROTEIN_PER_100G] = float(protein_per_100g)
            template[ATTR_CALORIES_PER_100G] = float(calories_per_100g)

        key = self._template_key(entry_name)
        templates = [
            existing
            for existing in user.setdefault(ATTR_TEMPLATES, [])
            if self._template_key(existing.get(ATTR_ENTRY_NAME, "")) != key
        ]
        templates.append(template)
        user[ATTR_TEMPLATES] = sorted(
            templates,
            key=lambda item: str(item.get(ATTR_ENTRY_NAME, "")).casefold(),
        )

    def _sync_missing_templates_from_history(self, user: dict[str, Any]) -> bool:
        """Create templates for named history entries that predate template support."""
        existing_keys = {
            self._template_key(template.get(ATTR_ENTRY_NAME, ""))
            for template in user.get(ATTR_TEMPLATES, [])
            if isinstance(template, dict)
        }

        changed = False
        templates = list(user.get(ATTR_TEMPLATES, []))
        for entry in reversed(user.get(ATTR_HISTORY, [])):
            if not isinstance(entry, dict):
                continue

            normalized_name = self._normalize_entry_name(entry.get(ATTR_ENTRY_NAME))
            key = self._template_key(normalized_name)
            protein = float(entry.get("protein", 0.0))
            calories = float(entry.get("calories", 0.0))
            if not normalized_name or key in existing_keys or (protein <= 0 and calories <= 0):
                continue

            templates.append(
                {
                    ATTR_ENTRY_NAME: normalized_name,
                    "protein": protein,
                    "calories": calories,
                    ATTR_TEMPLATE_TYPE: "fixed",
                    ATTR_CREATED_AT: str(entry.get(ATTR_CREATED_AT, "")),
                }
            )
            existing_keys.add(key)
            changed = True

        if changed:
            user[ATTR_TEMPLATES] = sorted(
                templates,
                key=lambda item: str(item.get(ATTR_ENTRY_NAME, "")).casefold(),
            )

        return changed

    @staticmethod
    def _entry_is_today(entry: dict[str, Any], today: str) -> bool:
        """Return whether a stored entry has a creation date matching today."""
        created_at = str(entry.get(ATTR_CREATED_AT, ""))
        return len(created_at) >= 10 and created_at[:10] == today

    @staticmethod
    def _normalize_entry_name(entry_name: Any) -> str:
        """Return a compact optional entry name safe for storage/display."""
        if entry_name is None:
            return ""
        return " ".join(str(entry_name).split())[:80]

    @staticmethod
    def _template_key(entry_name: Any) -> str:
        """Return a case-insensitive key for matching templates by name."""
        return " ".join(str(entry_name).split()).casefold()

    @staticmethod
    def _normalize_template_type(template_type: Any) -> str:
        """Return a known template type."""
        return "per_100g" if str(template_type) == "per_100g" else "fixed"

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
                ATTR_HISTORY: [
                    {
                        ATTR_ENTRY_ID: str(entry.get(ATTR_ENTRY_ID, "")),
                        "protein": round(float(entry.get("protein", 0.0)), 2),
                        "calories": round(float(entry.get("calories", 0.0)), 2),
                        ATTR_ENTRY_NAME: str(entry.get(ATTR_ENTRY_NAME, "")),
                        ATTR_CREATED_AT: str(entry.get(ATTR_CREATED_AT, "")),
                    }
                    for entry in user.get(ATTR_HISTORY, [])
                    if isinstance(entry, dict)
                    and self._entry_is_today(entry, str(user[ATTR_DATE]))
                ],
                ATTR_TEMPLATES: [
                    {
                        ATTR_ENTRY_NAME: str(template.get(ATTR_ENTRY_NAME, "")),
                        "protein": round(float(template.get("protein", 0.0)), 2),
                        "calories": round(float(template.get("calories", 0.0)), 2),
                        ATTR_TEMPLATE_TYPE: self._normalize_template_type(
                            template.get(ATTR_TEMPLATE_TYPE)
                        ),
                        ATTR_PROTEIN_PER_100G: round(
                            float(template.get(ATTR_PROTEIN_PER_100G, 0.0)), 2
                        ),
                        ATTR_CALORIES_PER_100G: round(
                            float(template.get(ATTR_CALORIES_PER_100G, 0.0)), 2
                        ),
                        ATTR_CREATED_AT: str(template.get(ATTR_CREATED_AT, "")),
                    }
                    for template in user.get(ATTR_TEMPLATES, [])
                    if isinstance(template, dict)
                    and str(template.get(ATTR_ENTRY_NAME, ""))
                    and (
                        float(template.get("protein", 0.0)) > 0
                        or float(template.get("calories", 0.0)) > 0
                        or float(template.get(ATTR_PROTEIN_PER_100G, 0.0)) > 0
                        or float(template.get(ATTR_CALORIES_PER_100G, 0.0)) > 0
                    )
                ],
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
