import os
from typing import Any

import yaml

from .env_loader import load_env_file
from .paths import resource_path, writable_path


DEFAULT_FEATURE_FLAGS = {
    "ENABLE_X_READ": False,
    "ENABLE_X_WRITE": False,
    "ENABLE_EMAIL_READ": False,
    "ENABLE_EMAIL_SEND": False,
    "REQUIRE_HUMAN_APPROVAL": True,
    "ALLOW_KEYWORD_SEARCH_AUTO_REPLY": False,
    "ALLOW_UNSOLICITED_DM": False,
    "METADATA_ONLY_LEARNING": True,
}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def load_feature_flags() -> dict:
    load_env_file()
    flags = dict(DEFAULT_FEATURE_FLAGS)
    try:
        with open(resource_path("config", "feature_flags.yaml"), encoding="utf-8") as file:
            configured = yaml.safe_load(file) or {}
            flags.update(configured)
    except OSError:
        pass

    for key in list(flags):
        if key in os.environ:
            flags[key] = _coerce_bool(os.environ[key])
    return flags


def save_feature_flags(flags: dict) -> dict:
    saved = {
        key: _coerce_bool(flags.get(key, DEFAULT_FEATURE_FLAGS[key]))
        for key in DEFAULT_FEATURE_FLAGS
    }
    path = writable_path("config", "feature_flags.yaml")
    with open(path, "w", encoding="utf-8") as file:
        yaml.safe_dump(saved, file, sort_keys=False)

    for key, value in saved.items():
        os.environ[key] = "true" if value else "false"
    return saved


def feature_enabled(name: str) -> bool:
    return _coerce_bool(load_feature_flags().get(name, False))
