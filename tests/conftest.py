"""Shared pytest configuration for command-mocking tests.

The module registers the cmd-mox pytest plugin so tests can request the
``cmd_mox`` fixture directly. Test modules should use that fixture when command
expectations can follow the plugin's automatic record, replay and verify
lifecycle.
"""

from typos_rollout_test_support import rollout_fixture

pytest_plugins = ("cmd_mox.pytest_plugin",)
__all__ = ("rollout_fixture",)
