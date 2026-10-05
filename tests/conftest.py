"""Shared test setup."""

import socket

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Rule 3: tests never hit the network. Any real connection attempt fails loudly."""

    def refuse(*args, **kwargs):
        raise RuntimeError("A test tried to use the network. Mock it or use tests/fixtures/ instead.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


@pytest.fixture(autouse=True)
def no_github_run_summary(monkeypatch):
    """In GitHub Actions, keep tests' made-up pipeline summaries off the real run's summary page."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("GROUPME_BOT_ID", raising=False)  # the chat post's secret: tests set a fake one when needed
