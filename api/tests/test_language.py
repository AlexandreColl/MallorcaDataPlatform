from typing import Annotated

import pytest
from fastapi import FastAPI, Header, Response
from fastapi.testclient import TestClient

from api.language import negotiate
from api.middleware import ResponseCache
from api.tests.test_api import FakeDatabase, client


@pytest.mark.parametrize(
    ("header", "language"),
    [
        ("ca-ES,ca;q=0.9,en;q=0.8", "ca"),
        ("ca-ES-valencia", "ca"),
        ("en-GB,en;q=0.9", "en"),
        ("fr-FR,en;q=0.7,ca;q=0.8", "ca"),  # by quality, not by order
        ("en;q=0.5,ca;q=0.5", "en"),  # a tie goes to the first
        ("CA", "ca"),
        ("fr-FR,de", "es"),
        ("*", "es"),
        ("ca;q=0,en;q=0", "es"),  # q=0 means "not this one"
        ("en;q=abc", "es"),
        ("", "es"),
        (None, "es"),
    ],
)
def test_negotiate_picks_the_preferred_language_the_api_speaks(header, language):
    assert negotiate(header) == language


def test_the_catalogue_texts_follow_accept_language():
    db = FakeDatabase()
    api = client(db)

    for path in ("/v1/sources", "/v1/locations", "/v1/weather/daily"):
        answer = api.get(path, headers={"Accept-Language": "ca-ES,ca;q=0.9"})
        assert answer.headers["content-language"] == "ca"
        assert "accept-language" in answer.headers["vary"].lower()
        assert db.calls[-1][1]["language"] == "ca"

    default = api.get("/v1/sources")
    assert default.headers["content-language"] == "es"
    assert db.calls[-1][1]["language"] == "es"


def test_answers_that_do_not_change_with_the_language_do_not_vary():
    answer = client(FakeDatabase()).get("/v1/water/reserves", headers={"Accept-Language": "ca"})
    assert "content-language" not in answer.headers
    assert "accept-language" not in answer.headers.get("vary", "").lower()  # CORS adds its own Vary: Origin


def test_the_cache_keeps_one_answer_per_language_when_the_answer_varies():
    calls: list[str | None] = []
    app = FastAPI()

    @app.get("/texts")
    def texts(response: Response, accept_language: Annotated[str | None, Header()] = None) -> dict[str, str]:
        calls.append(accept_language)
        response.headers["Vary"] = "Accept-Language"
        return {"language": negotiate(accept_language)}

    app.add_middleware(ResponseCache, seconds=60, paths=["/texts"])
    api = TestClient(app)

    catalan = api.get("/texts", headers={"Accept-Language": "ca-ES,ca;q=0.9"})
    english = api.get("/texts", headers={"Accept-Language": "en-GB"})
    catalan_again = api.get("/texts", headers={"Accept-Language": "ca"})  # another header, the same language

    assert [r.json()["language"] for r in (catalan, english, catalan_again)] == ["ca", "en", "ca"]
    assert [r.headers["x-cache"] for r in (catalan, english, catalan_again)] == ["MISS", "MISS", "HIT"]
    assert catalan.headers["etag"] != english.headers["etag"]
    assert len(calls) == 2
