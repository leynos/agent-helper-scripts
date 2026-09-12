"""Shared pytest configuration for command-mocking tests.

The module registers the cmd-mox pytest plugin so tests can request the
``cmd_mox`` fixture directly. Test modules should use that fixture when command
expectations can follow the plugin's automatic record, replay and verify
lifecycle.

It also re-exports the fixtures that more than one test module requests from a
sibling ``*_test_support`` module, so a test module names the fixture without
importing the support module's other contents.
"""

from biome_typescript_pipeline_support import pipeline_fixture
from gate_runner_test_support import gate_fixture
from typos_rollout_test_support import rollout_fixture

pytest_plugins = ("cmd_mox.pytest_plugin",)
__all__ = ("gate_fixture", "pipeline_fixture", "rollout_fixture")
