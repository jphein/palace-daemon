"""The daemon must resolve --palace itself, before importing mempalace.mcp_server.

Regression 2026-09-03: mempalace #441 stopped mcp_server scraping the importing
process's argv; the daemon had relied on that by accident, fell back to
~/.mempalace/palace, and orphaned its whole mine queue across a restart.
"""
import os

import main


def test_argv_space_form():
    assert main._palace_path_from_argv(["--palace", "/srv/p"], {}) == "/srv/p"


def test_argv_equals_form():
    assert main._palace_path_from_argv(["--port", "1", "--palace=/srv/q"], {}) == "/srv/q"


def test_env_fallbacks_and_precedence():
    assert main._palace_path_from_argv([], {"PALACE_PATH": "/e1"}) == "/e1"
    assert main._palace_path_from_argv([], {"MEMPALACE_PALACE_PATH": "/e2", "PALACE_PATH": "/e1"}) == "/e2"
    assert main._palace_path_from_argv(["--palace", "/a"], {"MEMPALACE_PALACE_PATH": "/e2"}) == "/a"


def test_nothing_given_returns_none():
    assert main._palace_path_from_argv(["--port", "8085"], {}) is None


def test_mcp_server_config_saw_the_export():
    # main.py is imported by the test session with whatever argv/env pytest has;
    # the invariant we can check here is consistency: if an export happened,
    # mcp_server's config reflects it.
    exported = os.environ.get("MEMPALACE_PALACE_PATH")
    if exported:
        assert os.path.abspath(main._mp._config.palace_path) == os.path.abspath(exported)
