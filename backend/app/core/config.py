import os
from typing import List, Optional

class Settings:
    @property
    def ENVIRONMENT(self) -> str:
        return os.getenv("ENVIRONMENT", os.getenv("RENDER_ENV", "development")).strip().lower()

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT in {"production", "prod"} or bool(os.getenv("RENDER"))

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        origins = os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,http://localhost:5174",
        )
        return [origin.strip().rstrip("/") for origin in origins.split(",") if origin.strip()]

    @property
    def API_KEY(self) -> str:
        return os.getenv("API_KEY", "dev-key-123")

    @property
    def DEFAULT_PLAN(self) -> str:
        return os.getenv("DEFAULT_PLAN", "free")

    @property
    def JWT_SECRET(self) -> str:
        secret = os.getenv("JWT_SECRET", "").strip()
        if secret:
            return secret
        if self.IS_PRODUCTION:
            raise RuntimeError("JWT_SECRET is required in production")
        return "dev-only-change-me"

    @property
    def JWT_EXPIRES_MIN(self) -> int:
        raw_value = os.getenv("JWT_EXPIRES_MIN", "60")
        try:
            expires = int(raw_value)
        except ValueError as exc:
            raise RuntimeError("JWT_EXPIRES_MIN must be an integer") from exc
        if expires <= 0:
            raise RuntimeError("JWT_EXPIRES_MIN must be greater than zero")
        return expires

    @property
    def COOKIE_DOMAIN(self) -> Optional[str]:
        domain = os.getenv("COOKIE_DOMAIN", "").strip()
        return domain or None

    @property
    def COOKIE_SECURE(self) -> bool:
        raw_value = os.getenv("COOKIE_SECURE")
        if raw_value is None:
            return self.IS_PRODUCTION
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    @property
    def COOKIE_SAMESITE(self) -> str:
        value = os.getenv("COOKIE_SAMESITE", "none" if self.IS_PRODUCTION else "lax").strip().lower()
        if value not in {"lax", "strict", "none"}:
            raise RuntimeError("COOKIE_SAMESITE must be one of: lax, strict, none")
        if value == "none" and not self.COOKIE_SECURE:
            raise RuntimeError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        return value

    @property
    def AUTH_COOKIE_NAME(self) -> str:
        return os.getenv("AUTH_COOKIE_NAME", "InsightAir_access")

settings = Settings()
