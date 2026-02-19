import json
import os
from app.core.config import settings

# A simple helper to load data
def load_json_db():
    if not os.path.exists(settings.JSON_DB_PATH):
        return {}
    
    with open(settings.JSON_DB_PATH, "r") as f:
        data = json.load(f)
    return data

# We don't need a "session" like SQL, but let's keep the name similar
# so your routers don't need to change much later.
def get_db():
    # In JSON world, "getting the DB" just means loading the dictionary
    return load_json_db()