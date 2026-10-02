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
