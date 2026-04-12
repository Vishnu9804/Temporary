from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    API_KEY: str 
    
    # NEW: Supabase / PostgreSQL Connection String
    # Format: postgresql://user:password@host:port/dbname
    DATABASE_URL: str 

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()