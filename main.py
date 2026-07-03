import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # or restrict if required
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------
# Defaults
# ------------------------

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}


# ------------------------
# Helpers
# ------------------------

def to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )


def coerce(key, value):
    if key in ("port", "workers"):
        return int(value)

    if key == "debug":
        return to_bool(value)

    return str(value)


def load_yaml():
    env = os.getenv("APP_ENV", "development")
    filename = f"config.{env}.yaml"

    if not Path(filename).exists():
        return {}

    with open(filename, "r") as f:
        data = yaml.safe_load(f) or {}

    return data


def load_dotenv():
    if not Path(".env").exists():
        return {}

    env = dotenv_values(".env")

    result = {}

    for k, v in env.items():
        if k == "NUM_WORKERS":
            result["workers"] = v
        elif k.startswith("APP_"):
            result[k[4:].lower()] = v

    return result


def load_os_env():
    result = {}

    for k, v in os.environ.items():
        if not k.startswith("APP_"):
            continue

        result[k[4:].lower()] = v

    return result


@app.get("/effective-config")
def effective_config(set: list[str] = Query(default=[])):
    config = DEFAULTS.copy()

    # YAML
    for k, v in load_yaml().items():
        config[k] = v

    # .env
    for k, v in load_dotenv().items():
        config[k] = v

    # OS env
    for k, v in load_os_env().items():
        config[k] = v

    # CLI overrides (?set=key=value)
    for item in set:
        if "=" not in item:
            continue

        key, value = item.split("=", 1)
        config[key] = value

    # Type coercion
    result = {}

    for key in DEFAULTS:
        result[key] = coerce(key, config[key])

    # Secret masking
    result["api_key"] = "****"

    return result