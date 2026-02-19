from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    JSON_DB_PATH: str = "app/core/clients.json"
    API_V1_STR: str = "/api/v1"
    
    # Add this line to tell Pydantic to read this from your .env file
    GOOGLE_API_KEY: str 

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()