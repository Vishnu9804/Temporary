from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    JSON_DB_PATH: str = "app/core/clients.json"
    API_V1_STR: str = "/api/v1"

settings = Settings()