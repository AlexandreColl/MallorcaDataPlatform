"""HTTP client with retries. Connectors receive it injected so tests can replace it."""

from __future__ import annotations

import logging
from typing import Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core import __version__

log = logging.getLogger(__name__)

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None


class JsonGetter(Protocol):
    """Anything that can GET a URL and return decoded JSON (real client or test fake)."""

    def get_json(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> JsonValue:
        """GET ``url`` and return the decoded JSON body."""
        ...


class HttpClient:
    """``requests`` session with retries and backoff on 429/5xx."""

    def __init__(self, timeout: float = 30.0, retries: int = 5, backoff: float = 1.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"mallorca-data-platform/{__version__}"
        retry = Retry(
            total=retries,
            backoff_factor=backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_json(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> JsonValue:
        """GET ``url`` and return the decoded JSON body.

        Raises:
            requests.HTTPError: for non-2xx responses once retries are exhausted.
        """
        log.info("GET %s params=%s", url, params)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
