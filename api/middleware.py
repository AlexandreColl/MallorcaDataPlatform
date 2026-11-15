"""Response cache and rate limit, as plain ASGI middleware held in the memory of each API process.

Both are deliberately local (ADR 0023): the API runs two uvicorn workers on one machine, so a shared store such as
Redis would be one more service for a cache whose data changes once a day and a limit meant to stop a runaway
client, not to bill one. Each worker keeps its own entries and buckets.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, MutableMapping

    type Scope = MutableMapping[str, Any]
    type Message = MutableMapping[str, Any]
    type Receive = Callable[[], Any]
    type Send = Callable[[Message], Any]
    type App = Callable[[Scope, Receive, Send], Any]


def _header(scope: Scope, name: bytes) -> bytes | None:
    """The first value of a request header (names are lower case in ASGI)."""
    return next((value for key, value in scope.get("headers", ()) if key == name), None)


async def _send_json(
    send: Send, status: HTTPStatus, body: dict[str, Any], headers: Iterable[tuple[bytes, bytes]]
) -> None:
    payload = json.dumps(body).encode()
    start = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode()), *headers]
    await send({"type": "http.response.start", "status": int(status), "headers": start})
    await send({"type": "http.response.body", "body": payload})


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimit:
    """Token bucket per client: ``per_minute`` requests in a burst, refilled at ``per_minute`` a minute.

    The client is the address uvicorn gives the request, which is the one in ``X-Forwarded-For`` when the request
    comes through a trusted proxy (the web's nginx, see ``FORWARDED_ALLOW_IPS``). Over the limit the answer is
    429 with ``Retry-After``; every answer carries the ``RateLimit-Limit`` and ``RateLimit-Remaining`` headers.
    """

    def __init__(
        self,
        app: App,
        *,
        per_minute: int,
        exempt: Iterable[str] = (),
        clock: Callable[[], float] = time.monotonic,
        max_clients: int = 10_000,
    ) -> None:
        self.app = app
        self.per_minute = per_minute
        self.exempt = frozenset(exempt)
        self.clock = clock
        self.max_clients = max_clients
        self.buckets: dict[str, _Bucket] = {}

    def take(self, client: str) -> tuple[bool, int, float]:
        """Spend one token of ``client``: whether it had one, the tokens left and the seconds to the next one."""
        now = self.clock()
        rate = self.per_minute / 60
        bucket = self.buckets.get(client)
        if bucket is None:
            if len(self.buckets) >= self.max_clients:
                self._forget_full(now, rate)
            bucket = self.buckets[client] = _Bucket(float(self.per_minute), now)
        bucket.tokens = min(float(self.per_minute), bucket.tokens + (now - bucket.updated) * rate)
        bucket.updated = now
        if bucket.tokens < 1:
            return False, 0, (1 - bucket.tokens) / rate
        bucket.tokens -= 1
        return True, int(bucket.tokens), 0.0

    def _forget_full(self, now: float, rate: float) -> None:
        """Drop the clients whose bucket has refilled: they are where a new client would start anyway."""
        for client, bucket in list(self.buckets.items()):
            if bucket.tokens + (now - bucket.updated) * rate >= self.per_minute:
                del self.buckets[client]
        if len(self.buckets) >= self.max_clients:  # all of them busy: start again rather than grow without end
            self.buckets.clear()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass the request on, or answer 429 when its client has no token left."""
        if scope["type"] != "http" or self.per_minute <= 0 or scope["path"] in self.exempt:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        allowed, remaining, wait = self.take(client[0] if client else "unknown")
        limit_headers = [(b"ratelimit-limit", str(self.per_minute).encode())]
        if not allowed:
            retry = str(math.ceil(wait)).encode()
            error = {"code": "rate_limited", "message": f"more than {self.per_minute} requests a minute; retry later"}
            headers = [*limit_headers, (b"ratelimit-remaining", b"0"), (b"retry-after", retry)]
            await _send_json(send, HTTPStatus.TOO_MANY_REQUESTS, {"error": error}, headers)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    *limit_headers,
                    (b"ratelimit-remaining", str(remaining).encode()),
                ]
            await send(message)

        await self.app(scope, receive, with_headers)


@dataclass(frozen=True)
class _Entry:
    stored: float
    headers: list[tuple[bytes, bytes]]
    body: bytes
    etag: bytes


class ResponseCache:
    """Keeps the successful GET answers of ``paths`` for ``seconds`` and validates them with an ``ETag``.

    The key is the path and the sorted query string, so ``?from=2025-01-01&to=...`` and its reordering share an
    entry. A fresh entry is answered without touching the warehouse (``X-Cache: HIT``), or with 304 when the client
    already holds that ``ETag``. ``Cache-Control: max-age`` tells browsers and proxies the time the entry has left.
    """

    def __init__(
        self,
        app: App,
        *,
        seconds: int,
        paths: Iterable[str],
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.seconds = seconds
        self.paths = frozenset(paths)
        self.max_entries = max_entries
        self.clock = clock
        self.entries: OrderedDict[str, _Entry] = OrderedDict()

    @staticmethod
    def key(scope: Scope) -> str:
        """Path plus the query parameters in a fixed order."""
        query = scope.get("query_string", b"").decode("latin-1")
        return scope["path"] + "?" + "&".join(sorted(p for p in query.split("&") if p))

    def fresh(self, key: str) -> _Entry | None:
        """The entry of ``key`` if it is younger than ``seconds`` (and mark it as recently used)."""
        entry = self.entries.get(key)
        if entry is None or self.clock() - entry.stored >= self.seconds:
            return None
        self.entries.move_to_end(key)
        return entry

    def store(self, key: str, headers: list[tuple[bytes, bytes]], body: bytes) -> _Entry:
        """Keep an answer, dropping the least recently used one beyond ``max_entries``."""
        etag = b'"' + hashlib.sha256(body).hexdigest()[:32].encode() + b'"'
        entry = self.entries[key] = _Entry(self.clock(), headers, body, etag)
        self.entries.move_to_end(key)
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)
        return entry

    def _validators(self, entry: _Entry, *, hit: bool) -> list[tuple[bytes, bytes]]:
        left = max(0, math.ceil(self.seconds - (self.clock() - entry.stored)))
        return [
            (b"etag", entry.etag),
            (b"cache-control", f"public, max-age={left}".encode()),
            (b"x-cache", b"HIT" if hit else b"MISS"),
        ]

    async def _answer(self, scope: Scope, send: Send, entry: _Entry, *, hit: bool) -> None:
        validators = self._validators(entry, hit=hit)
        if _header(scope, b"if-none-match") == entry.etag:
            await send({"type": "http.response.start", "status": int(HTTPStatus.NOT_MODIFIED), "headers": validators})
            await send({"type": "http.response.body", "body": b""})
            return
        await send(
            {"type": "http.response.start", "status": int(HTTPStatus.OK), "headers": [*entry.headers, *validators]}
        )
        await send({"type": "http.response.body", "body": entry.body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answer from the cache, or ask the app and keep its answer when it is a 200."""
        if scope["type"] != "http" or scope["method"] != "GET" or self.seconds <= 0 or scope["path"] not in self.paths:
            await self.app(scope, receive, send)
            return
        key = self.key(scope)
        entry = self.fresh(key)
        if entry is not None:
            await self._answer(scope, send, entry, hit=True)
            return

        start: Message = {}
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                start.update(message)
                if message["status"] != HTTPStatus.OK:  # errors pass through, untouched and uncached
                    await send(message)
            elif start.get("status") != HTTPStatus.OK:
                await send(message)
            else:
                chunks.append(message.get("body", b""))

        await self.app(scope, receive, capture)
        if start.get("status") == HTTPStatus.OK:
            headers = [(k, v) for k, v in start.get("headers", []) if k not in {b"etag", b"cache-control"}]
            await self._answer(scope, send, self.store(key, headers, b"".join(chunks)), hit=False)
