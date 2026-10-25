"""Search settings: defaults from ``Config/search.yaml`` plus admin overrides in the config container.

Admins change ``top_n``, ``min_match_percent``, ``example_queries`` and ``welcome_text`` on the Settings page.
The overrides are saved as ``settings.json`` in the config container, so no redeploy is needed.
"""

from __future__ import annotations

import copy
import logging
import threading
import time
from functools import lru_cache
from pathlib import Path

import yaml

from .config import Settings

log = logging.getLogger(__name__)

OVERRIDES_BLOB = "settings.json"
EDITABLE = ("top_n", "min_match_percent", "example_queries", "welcome_text")
CACHE_SECONDS = 30

FALLBACK_DEFAULTS = {
    "results": {"top_n": 3, "min_match_percent": 20, "candidates": 50},
    "welcome_text": "",
    "example_queries": [],
    "chunking": {"target_tokens": 500, "max_tokens": 600, "overlap_ratio": 0.15, "max_chars": 4000},
    "excel": {"skip_hidden_sheets": True, "max_rows_per_sheet": 20000},
    "embedding": {"batch_size": 16},
    "related_terms": [],
}


class SettingsError(ValueError):
    pass


@lru_cache(maxsize=4)
def load_defaults(config_dir: Path | None) -> dict:
    data = copy.deepcopy(FALLBACK_DEFAULTS)
    path = Path(config_dir) / "search.yaml" if config_dir else None
    if path and path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key].update(value)
            else:
                data[key] = value
    else:
        log.warning("Config/search.yaml not found; using built-in defaults")
    return data


def validate(values: dict) -> dict:
    """Return clean editable values or raise SettingsError with a message for the user."""
    clean = {}
    if "top_n" in values:
        try:
            top_n = int(values["top_n"])
        except (TypeError, ValueError):
            raise SettingsError("Number of results must be a whole number.") from None
        if not 1 <= top_n <= 10:
            raise SettingsError("Number of results must be between 1 and 10.")
        clean["top_n"] = top_n
    if "min_match_percent" in values:
        try:
            minimum = int(values["min_match_percent"])
        except (TypeError, ValueError):
            raise SettingsError("Minimum match % must be a whole number.") from None
        if not 0 <= minimum <= 100:
            raise SettingsError("Minimum match % must be between 0 and 100.")
        clean["min_match_percent"] = minimum
    if "example_queries" in values:
        queries = values["example_queries"]
        if isinstance(queries, str):
            queries = queries.splitlines()
        queries = [str(q).strip()[:120] for q in queries if str(q).strip()]
        if len(queries) > 12:
            raise SettingsError("Use at most 12 example queries.")
        clean["example_queries"] = queries
    if "welcome_text" in values:
        text = str(values["welcome_text"]).strip()
        if len(text) > 500:
            raise SettingsError("Welcome text must be 500 characters or fewer.")
        clean["welcome_text"] = text
    return clean


class SettingsStore:
    def __init__(self, blob_store, settings: Settings):
        self.blobs = blob_store
        self.settings = settings
        self._cache: tuple[float, dict] | None = None
        self._lock = threading.Lock()

    @property
    def defaults(self) -> dict:
        return load_defaults(self.settings.config_dir)

    def overrides(self) -> dict:
        with self._lock:
            if self._cache and time.monotonic() - self._cache[0] < CACHE_SECONDS:
                return dict(self._cache[1])
        try:
            data = self.blobs.get_json_or_none(self.settings.container_config, OVERRIDES_BLOB) or {}
            data = validate({k: v for k, v in data.items() if k in EDITABLE})
        except Exception:  # noqa: BLE001 - a broken overrides file must not break search
            log.warning("Could not read settings overrides; using defaults", exc_info=True)
            data = {}
        with self._lock:
            self._cache = (time.monotonic(), data)
        return dict(data)

    def effective(self) -> dict:
        """Editable values in effect (defaults overlaid with admin overrides)."""
        d = self.defaults
        values = {
            "top_n": int(d["results"]["top_n"]),
            "min_match_percent": int(d["results"]["min_match_percent"]),
            "example_queries": list(d.get("example_queries") or []),
            "welcome_text": d.get("welcome_text") or "",
        }
        values.update(self.overrides())
        return values

    def save(self, values: dict) -> dict:
        clean = validate({k: v for k, v in values.items() if k in EDITABLE})
        merged = {**self.overrides(), **clean}
        self.blobs.put_json(self.settings.container_config, OVERRIDES_BLOB, merged)
        with self._lock:
            self._cache = (time.monotonic(), merged)
        return self.effective()

    def reset(self) -> None:
        self.blobs.delete(self.settings.container_config, OVERRIDES_BLOB)
        with self._lock:
            self._cache = None

    # Fixed (redeploy) values
    @property
    def candidates(self) -> int:
        return int(self.defaults["results"].get("candidates", 50))

    @property
    def chunking(self) -> dict:
        return dict(self.defaults["chunking"])

    @property
    def excel(self) -> dict:
        return dict(self.defaults["excel"])

    @property
    def batch_size(self) -> int:
        return max(1, int(self.defaults["embedding"].get("batch_size", 16)))

    @property
    def synonyms(self) -> list[list[str]]:
        return [list(g) for g in self.defaults.get("related_terms") or []]
