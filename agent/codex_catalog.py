"""Shared Codex OAuth model-catalog request policy.

The backend gates models on client_version. Ask as a new client first; if
that yields no entries, try the old ungated sentinel for compatibility.
"""

from typing import Any, Callable


CODEX_MODELS_CATALOG_ENDPOINT = "https://chatgpt.com/backend-api/codex/models"
CODEX_MODELS_CATALOG_URLS = tuple(
    f"{CODEX_MODELS_CATALOG_ENDPOINT}?client_version={version}"
    for version in ("99.0.0", "0.0.0")
)


def fetch_codex_catalog_entries(get: Callable[[str], Any]) -> list:
    """Return the first non-empty successful model list, otherwise [].

    Network and JSON errors at either URL must not prevent the fallback.
    """
    for url in CODEX_MODELS_CATALOG_URLS:
        try:
            response = get(url)
            if response.status_code != 200:
                continue
            payload = response.json()
            entries = payload.get("models") if isinstance(payload, dict) else None
            if isinstance(entries, list) and entries:
                return entries
        except Exception:
            continue
    return []
