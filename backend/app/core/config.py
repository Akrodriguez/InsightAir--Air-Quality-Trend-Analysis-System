import os
from typing import List

class Settings:
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        # Allow both default Vite ports; can be overridden via ALLOWED_ORIGINS env var.
        return os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,http://localhost:5174",
        ).split(",")

    @property
    def API_KEY(self) -> str:
        return os.getenv("API_KEY", "dev-key-123")

    @property
    def DEFAULT_PLAN(self) -> str:
        return os.getenv("DEFAULT_PLAN", "free")

    @property
    def JWT_SECRET(self) -> str:
        return os.getenv("JWT_SECRET", "your-secret-key-change-in-production")

    @property
    def JWT_EXPIRES_MIN(self) -> int:
        return int(os.getenv("JWT_EXPIRES_MIN", "60"))

    @property
    def COOKIE_DOMAIN(self) -> str:
        return os.getenv("COOKIE_DOMAIN", "localhost")

settings = Settings()
