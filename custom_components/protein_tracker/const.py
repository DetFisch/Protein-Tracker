"""Constants for the Protein Tracker integration."""

DOMAIN = "protein_tracker"
STORAGE_VERSION = 1
STORAGE_KEY = "protein_tracker.storage"

DATA_MANAGER = "manager"
DATA_UNSUB_RESET = "unsub_reset"
DATA_ENTRIES = "entries"
DATA_SERVICES_REGISTERED = "services_registered"

CONF_USERS = "users"
CONF_ID = "id"
CONF_NAME = "name"
CONF_GOAL = "goal"
CONF_CALORIE_GOAL = "calorie_goal"

DEFAULT_GOAL = 0.0
DEFAULT_CALORIE_GOAL = 0.0

SERVICE_ADD_PROTEIN = "add_protein"
SERVICE_ADD_FOOD = "add_food"
SERVICE_SET_GOAL = "set_goal"
SERVICE_RESET_USER = "reset_user"
SERVICE_ADD_CALORIES = "add_calories"
SERVICE_ADD_CALORIE_FOOD = "add_calorie_food"
SERVICE_SET_CALORIE_GOAL = "set_calorie_goal"
SERVICE_RESET_CALORIES = "reset_calories"

ATTR_USER_ID = "user_id"
ATTR_DATE = "date"
ATTR_TODAY_TOTAL = "today_total"
ATTR_GOAL = "goal"
ATTR_REMAINING = "remaining"
ATTR_PROGRESS_PERCENT = "progress_percent"
ATTR_CALORIES_TODAY_TOTAL = "calories_today_total"
ATTR_CALORIE_GOAL = "calorie_goal"
ATTR_CALORIES_REMAINING = "calories_remaining"
ATTR_CALORIES_PROGRESS_PERCENT = "calories_progress_percent"
ATTR_TRACKER_TYPE = "tracker_type"

TRACKER_TYPE_PROTEIN = "protein"
TRACKER_TYPE_CALORIES = "calories"

FIELD_GRAMS = "grams"
FIELD_FOOD_GRAMS = "food_grams"
FIELD_PROTEIN_PER_100G = "protein_per_100g"
FIELD_GOAL_GRAMS = "goal_grams"
FIELD_CALORIES = "calories"
FIELD_CALORIES_PER_100G = "calories_per_100g"
FIELD_GOAL_CALORIES = "goal_calories"
FIELD_USER_ID = "user_id"
FIELD_ENTITY_ID = "entity_id"
