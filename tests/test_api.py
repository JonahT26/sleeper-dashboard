"""Tests for the Sleeper API client. requests.get and the clock are faked, so nothing touches the network."""

import json
import os
import time

import pytest
import requests

from sleeper_dash import api


def make_response(status_code, body=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(body).encode()
    return response


class FakeSleeper:
    """Stands in for requests.get: returns queued responses (or raises queued errors) in order."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, url, timeout):
        self.calls.append({"url": url, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClock:
    """Replaces time.monotonic and time.sleep so tests run instantly and record every pause."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(api.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(api.time, "sleep", fake.sleep)
    monkeypatch.setattr(api, "_last_call", float("-inf"))
    return fake


def fake_sleeper(monkeypatch, *outcomes):
    fake = FakeSleeper(*outcomes)
    monkeypatch.setattr(api.requests, "get", fake)
    return fake


def test_real_network_calls_are_blocked():
    # Guards rule 3 via tests/conftest.py. Uses a local address so not even a DNS lookup happens.
    with pytest.raises(RuntimeError, match="network"):
        requests.get("http://127.0.0.1:9", timeout=1)


# --- get() ---


def test_get_returns_json_from_the_right_url(monkeypatch, clock):
    sleeper = fake_sleeper(monkeypatch, make_response(200, {"name": "Test League"}))
    assert api.get("/league/123") == {"name": "Test League"}
    assert sleeper.calls == [{"url": "https://api.sleeper.app/v1/league/123", "timeout": 10}]


@pytest.mark.parametrize(
    "failure",
    [
        make_response(500),
        make_response(503),
        make_response(429),
        requests.ConnectionError("connection reset"),
        requests.Timeout("read timed out"),
    ],
    ids=["500", "503", "429", "connection-error", "timeout"],
)
def test_get_retries_temporary_failures_then_succeeds(monkeypatch, clock, failure):
    sleeper = fake_sleeper(monkeypatch, failure, failure, make_response(200, {"ok": True}))
    assert api.get("/state/nfl") == {"ok": True}
    assert len(sleeper.calls) == 3
    assert clock.sleeps == [1, 2]  # backoff doubles


def test_get_gives_up_after_three_retries(monkeypatch, clock):
    sleeper = fake_sleeper(monkeypatch, *[make_response(503)] * 4)
    with pytest.raises(api.SleeperAPIError, match="/state/nfl"):
        api.get("/state/nfl")
    assert len(sleeper.calls) == 4  # first try + 3 retries
    assert clock.sleeps == [1, 2, 4]


def test_get_404_names_the_path_and_does_not_retry(monkeypatch, clock):
    sleeper = fake_sleeper(monkeypatch, make_response(404))
    with pytest.raises(api.SleeperNotFoundError, match="/league/999/matchups/3"):
        api.get("/league/999/matchups/3")
    assert len(sleeper.calls) == 1


def test_get_other_client_errors_do_not_retry(monkeypatch, clock):
    sleeper = fake_sleeper(monkeypatch, make_response(400))
    with pytest.raises(api.SleeperAPIError, match="HTTP 400"):
        api.get("/league/abc")
    assert len(sleeper.calls) == 1


def test_back_to_back_calls_are_spaced_out(monkeypatch, clock):
    fake_sleeper(monkeypatch, make_response(200, {}), make_response(200, {}))
    api.get("/state/nfl")
    api.get("/state/nfl")
    assert clock.sleeps == [pytest.approx(api.MIN_SECONDS_BETWEEN_CALLS)]


# --- get_players() ---

PLAYERS = {"1234": {"full_name": "Test Player", "position": "WR"}, "KC": {"position": "DEF"}}


def test_get_players_downloads_and_caches_when_no_cache(monkeypatch, clock, tmp_path):
    cache = tmp_path / "cache" / "players_nfl.json"
    sleeper = fake_sleeper(monkeypatch, make_response(200, PLAYERS))
    assert api.get_players(cache_path=cache) == PLAYERS
    assert sleeper.calls[0]["url"].endswith("/players/nfl")
    assert json.loads(cache.read_text(encoding="utf-8")) == PLAYERS


def test_get_players_uses_fresh_cache_without_network(monkeypatch, clock, tmp_path):
    cache = tmp_path / "players_nfl.json"
    cache.write_text(json.dumps(PLAYERS), encoding="utf-8")
    sleeper = fake_sleeper(monkeypatch)  # nothing queued: any request would fail the test
    assert api.get_players(cache_path=cache) == PLAYERS
    assert sleeper.calls == []


def test_get_players_redownloads_stale_cache(monkeypatch, clock, tmp_path):
    cache = tmp_path / "players_nfl.json"
    cache.write_text(json.dumps({"old": {}}), encoding="utf-8")
    hours_25_ago = time.time() - 25 * 3600
    os.utime(cache, (hours_25_ago, hours_25_ago))
    sleeper = fake_sleeper(monkeypatch, make_response(200, PLAYERS))
    assert api.get_players(cache_path=cache) == PLAYERS
    assert len(sleeper.calls) == 1
    assert json.loads(cache.read_text(encoding="utf-8")) == PLAYERS
