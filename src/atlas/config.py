"""Load config.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")


class ConfigError(Exception):
    pass


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if not path.is_file():
        raise ConfigError(
            f"{path} not found. Copy config.example.yaml to config.yaml and set maps_folder."
        )
    config = yaml.safe_load(path.read_text()) or {}
    if not isinstance(config, dict):
        raise ConfigError(f"{path} must be a YAML mapping.")
    return config


def maps_folder(config: dict) -> Path:
    value = config.get("maps_folder")
    if not value:
        raise ConfigError("maps_folder is not set in config.yaml.")
    return Path(value).expanduser()


def data_dir(config: dict) -> Path:
    return Path(config.get("data_dir", "data")).expanduser()


def manifest_csv(config: dict) -> Path:
    return Path(config.get("manifest_csv", "config/map_manifest.csv")).expanduser()


def regions_csv(config: dict) -> Path:
    return Path(config.get("regions_csv", "config/regions.csv")).expanduser()
