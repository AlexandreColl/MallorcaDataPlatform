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
# Query parameters; a list value is sent as a repeated key (?var=a&var=b).
type Params = dict[str, str | list[str]]


class JsonGetter(Protocol):
    """Anything that can GET a URL (real client or test fake). Connectors use the methods they need."""

    def get_json(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> JsonValue:
        """GET ``url`` and return the decoded JSON body."""
        ...

    def get_text(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> str:
        """GET ``url`` and return the body as text (CSV, XML...)."""
        ...

    def get_bytes(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> bytes:
        """GET ``url`` and return the raw body (zip files...)."""
        ...

    def post_text(self, url: str, json: JsonValue, headers: dict[str, str] | None = None) -> str:
        """POST a JSON body to a read-only query endpoint and return the response as text."""
        ...


class HttpClient:
    """``requests`` session with retries and backoff on connection errors, 429 and 5xx.

    A short connect timeout fails fast on an unreachable host so the retries (and then the Airflow task
    retries) get a chance; the read timeout is longer for slow but working APIs.
    """

    def __init__(
        self, connect_timeout: float = 10.0, read_timeout: float = 60.0, retries: int = 5, backoff: float = 2.0
    ) -> None:
        self.timeout = (connect_timeout, read_timeout)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"mallorca-data-platform/{__version__}"
        retry = Retry(
            total=retries,
            backoff_factor=backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            # POST only reaches read-only query endpoints (a search with a JSON body): retrying it is safe.
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _get(self, url: str, params: Params | None, headers: dict[str, str] | None) -> requests.Response:
        log.info("GET %s params=%s", url, params)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response

    def get_json(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> JsonValue:
        """GET ``url`` and return the decoded JSON body.

        Raises:
            requests.HTTPError: for non-2xx responses once retries are exhausted.
        """
        return self._get(url, params, headers).json()

    def get_text(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> str:
        """GET ``url`` and return the body as text.

        Raises:
            requests.HTTPError: for non-2xx responses once retries are exhausted.
        """
        return self._get(url, params, headers).text

    def get_bytes(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> bytes:
        """GET ``url`` and return the raw body.

        Raises:
            requests.HTTPError: for non-2xx responses once retries are exhausted.
        """
        return self._get(url, params, headers).content

    def post_text(self, url: str, json: JsonValue, headers: dict[str, str] | None = None) -> str:
        """POST ``json`` to ``url`` and return the body as text.

        Raises:
            requests.HTTPError: for non-2xx responses once retries are exhausted.
        """
        log.info("POST %s json=%s", url, json)
        response = self.session.post(url, json=json, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.text
