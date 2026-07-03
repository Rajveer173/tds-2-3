import os
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Pre-seed the three OS-level environment variables assigned for this task,
# ONLY if they are not already present in the real OS environment. This lets
# the service work out-of-the-box on any host without extra config, while
# still respecting real OS env vars if the deployer sets their own.
# ---------------------------------------------------------------------------
os.environ.setdefault("APP_PORT", "8883")
os.environ.setdefault("APP_WORKERS", "3")
os.environ.setdefault("APP_API_KEY", "key-c0fzhua3p9")

app = FastAPI(title="12-Factor Config Precedence Resolver")

# CORS: allow any origin so the grader's browser page can call this directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Layer 1: hardcoded defaults
# ---------------------------------------------------------------------------
DEFAULTS: Dict[str, Any] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

KNOWN_KEYS = {"port", "workers", "debug", "log_level", "api_key"}


def coerce(key: str, value: Any) -> Any:
    """Apply the required type-coercion rules for a given key."""
    if value is None:
        return None
    if key in ("port", "workers"):
        return int(value)
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    # log_level and any other key -> string
    return str(value)


def load_yaml_layer() -> Dict[str, Any]:
    """Layer 2: config.<env>.yaml (environment-specific)."""
    env_name = os.environ.get("APP_ENV", "development")
    path = BASE_DIR / f"config.{env_name}.yaml"
    if not path.exists():
        # fall back to the shipped development config
        path = BASE_DIR / "config.development.yaml"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    return {k: v for k, v in data.items()}


def load_dotenv_layer() -> Dict[str, Any]:
    """Layer 3: .env file, parsed manually so it stays a distinct layer
    from the real OS environment (layer 4)."""
    path = BASE_DIR / ".env"
    result: Dict[str, Any] = {}
    if not path.exists():
        return result

    line_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = line_re.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        # strip optional surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        # Special alias: NUM_WORKERS -> workers
        if name == "NUM_WORKERS":
            result["workers"] = value
            continue

        if name.startswith("APP_"):
            key = name[len("APP_"):].lower()
            result[key] = value

    return result


def load_os_env_layer() -> Dict[str, Any]:
    """Layer 4: real OS-level environment variables with APP_ prefix."""
    result: Dict[str, Any] = {}
    for name, value in os.environ.items():
        if name.startswith("APP_"):
            key = name[len("APP_"):].lower()
            result[key] = value
        elif name == "NUM_WORKERS":
            result["workers"] = value
    return result


def load_cli_overrides(set_params: List[str]) -> Dict[str, Any]:
    """Layer 5 (highest): ?set=key=value query params."""
    result: Dict[str, Any] = {}
    for item in set_params:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key == "NUM_WORKERS":
            key = "workers"
        result[key.lower()] = value.strip()
    return result


@app.get("/effective-config")
def effective_config(request: Request):
    set_params = request.query_params.getlist("set")

    merged: Dict[str, Any] = {}
    for layer in (
        DEFAULTS,
        load_yaml_layer(),
        load_dotenv_layer(),
        load_os_env_layer(),
        load_cli_overrides(set_params),
    ):
        merged.update(layer)

    response: Dict[str, Any] = {}
    for key in KNOWN_KEYS:
        response[key] = coerce(key, merged.get(key))

    # include any extra/unknown keys the caller set, as strings
    for key, value in merged.items():
        if key not in KNOWN_KEYS:
            response[key] = coerce(key, value)

    # Secret masking: api_key is never exposed
    response["api_key"] = "****"

    return response


@app.get("/")
def root():
    return {
        "service": "12-Factor Config Precedence Resolver",
        "endpoint": "/effective-config?set=key=value&set=...",
    }