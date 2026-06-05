from dataclasses import dataclass
import os


DEFAULT_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|"
    r"127(?:\.\d{1,3}){3}|"
    r"10(?:\.\d{1,3}){3}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"\[[0-9a-fA-F:]+\]"
    r")(?::\d+)?$"
)


def _parse_csv_env(name: str, default: str) -> list[str]:
    raw_value = os.getenv(name, default)
    return [part.strip() for part in raw_value.split(",") if part.strip()]


def _parse_optional_env(name: str, default: str | None) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip() or None


@dataclass(frozen=True)
class Settings:
    backend_port: int
    cache_ttl_seconds: int
    cors_origins: list[str]
    cors_origin_regex: str | None
    symbol_master_ttl_seconds: int
    quote_cache_ttl_seconds: int
    stock_provider_timeout_seconds: float


def load_settings() -> Settings:
    return Settings(
        backend_port=int(os.getenv("BACKEND_PORT", "8000")),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "30")),
        cors_origins=_parse_csv_env(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ),
        cors_origin_regex=_parse_optional_env("CORS_ORIGIN_REGEX", DEFAULT_CORS_ORIGIN_REGEX),
        symbol_master_ttl_seconds=int(os.getenv("SYMBOL_MASTER_TTL_SECONDS", "86400")),
        quote_cache_ttl_seconds=int(os.getenv("QUOTE_CACHE_TTL_SECONDS", "60")),
        stock_provider_timeout_seconds=float(os.getenv("STOCK_PROVIDER_TIMEOUT_SECONDS", "5.0")),
    )


settings = load_settings()
