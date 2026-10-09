
import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}


def normalize_key(key: str) -> str:
    key = key.strip().lower()

    # Support the required NUM_WORKERS alias.
    if key == "num_workers":
        return "workers"

    return key


def coerce_value(key: str, value):
    key = normalize_key(key)

    if key in ("port", "workers"):
        return int(value)

    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {
            "true", "1", "yes", "on"
        }

    # log_level and all other settings are strings.
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def load_effective_config(overrides: list[str]) -> dict:
    # Layer 1: hardcoded defaults.
    config = DEFAULTS.copy()

    # Layer 2: environment-specific YAML.
    environment = os.environ.get("CONFIG_ENV", "development")
    yaml_path = BASE_DIR / f"config.{environment}.yaml"

    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as file:
            yaml_config = yaml.safe_load(file) or {}

        for key, value in yaml_config.items():
            config[normalize_key(key)] = value

    # Layer 3: .env file. NUM_WORKERS maps to workers.
    env_file = dotenv_values(BASE_DIR / ".env")

    for key, value in env_file.items():
        if value is not None:
            normalized_key = key[4:] if key.startswith("APP_") else key
            normalized = normalize_key(normalized_key)
            config[normalized] = value

    # Layer 4: actual OS environment variables with APP_ prefix.
    for key, value in os.environ.items():
        if key.startswith("APP_"):
            normalized = normalize_key(key[4:])
            config[normalized] = value

    # Layer 5: URL query parameters, applied in order.
    for item in overrides:
        if "=" not in item:
            continue

        key, value = item.split("=", 1)
        key = normalize_key(key)

        if key:
            config[key] = value

    # Convert all final values to the required types.
    config = {
        key: coerce_value(key, value)
        for key, value in config.items()
    }

    # Never reveal the real API key.
    config["api_key"] = "****"

    return config


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "Configuration service is running"}


@app.get("/effective-config")
def effective_config(set: list[str] = Query(default=[])):
    try:
        return load_effective_config(set)
    except (ValueError, TypeError):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="Invalid configuration value"
        )