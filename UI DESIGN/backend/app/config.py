import re
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LLM_PROVIDER: str = "gemini"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.5-flash"
    DATABASE_URL: str = "sqlite:///./negotiation.db"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> List[str]:
        raw_origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        filtered = [o for o in raw_origins if o != "*"]
        return filtered or ["http://localhost:5173", "http://127.0.0.1:5173"]

settings = Settings()

def mask_secrets(text: str) -> str:
    if not text:
        return ""
    # Mask passwords in connection strings like postgresql://user:password@host
    masked = re.sub(r'(postgres(?:ql)?://[^:]+:)[^@]+(@)', r'\1***\2', text)
    # Mask Gemini API keys
    masked = re.sub(r'AIzaSy[A-Za-z0-9_-]{33}', '[REDACTED_API_KEY]', masked)
    return masked

