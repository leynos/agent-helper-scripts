"""Execute the published Femtologging callback-enrichment example.

The document contract proves only that every fence carries a marker. The
guide also presents this example as working code, so the test runs the
shipped snippet in a fresh interpreter against the real library and checks
the record the documented configuration delivers. An edit that reverts the
example to an unsupported API therefore fails here instead of misleading a
reader.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tested_example_test_support import load_tested_examples

GUIDE_PATH = (
    Path(__file__).resolve().parents[1]
    / "documentation-library"
    / "femtologging-users-guide.md"
)
#: The accepted-enrichment example in the Femtologging guide.
ENRICHMENT_EXAMPLE = "femtologging-callback-enrichment-accepted"

#: Appended after the published text. The example configures and flushes its
#: own `logger`, so the probe attaches a collector to that same object, emits
#: one more record, and prints the delivered key-values as JSON. Nothing here
#: changes how the shipped text runs. Its message differs from the example's,
#: so an assertion on the example's own delivery cannot be satisfied by the
#: probe's record.
PROBE_MESSAGE = "probe after the published example"
RECORD_PROBE = f"""
import json

_collector_records = []


class _Collector:
    def handle(self, logger, level, message):
        pass

    def handle_record(self, record):
        _collector_records.append(dict(record))

    def flush(self):
        return True


logger.add_handler(_Collector())
logger.log("INFO", {PROBE_MESSAGE!r})
logger.flush_handlers()
print(json.dumps(_collector_records[-1]["metadata"]["key_values"]))
"""


def published_example_body(identifier: str) -> str:
    """Return the body of the named example, exactly as the guide ships it."""
    for example in load_tested_examples(GUIDE_PATH):
        if example.identifier == identifier:
            return example.body
    message = f"no published example named {identifier!r} in {GUIDE_PATH}"
    raise AssertionError(message)


def run_published_example(
    body: str, cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run the shipped example, then report the record its filter delivered.

    A fresh interpreter starts with an empty logger registry, as a reader's
    would, and ``cwd`` keeps any files the example writes out of the
    repository.
    """
    return subprocess.run(
        [sys.executable, "-c", body + RECORD_PROBE],
        capture_output=True,
        check=False,
        cwd=cwd,
        text=True,
        timeout=60,
    )


def test_published_callback_enrichment_example_stamps_delivered_records(
    tmp_path: Path,
) -> None:
    """The guide's example configures a filter that enriches its records."""
    body = published_example_body(ENRICHMENT_EXAMPLE)
    result = run_published_example(body, tmp_path)

    assert result.returncode == 0, f"the published example failed:\n{result.stderr}"
    # The probe emits a different message, so finding this text proves the
    # example's own `logger.log(...)` reached a handler and was delivered.
    assert "request accepted" in result.stderr, (
        f"the published example must deliver its own record, got {result.stderr!r}"
    )
    assert result.stdout.strip(), "the probe must report the delivered record"
    key_values = json.loads(result.stdout.strip().splitlines()[-1])
    assert key_values == {
        "request_id": "req-123",
        "user_id": "42",
        "cache_hit": "False",
    }, f"the documented filter must enrich the record, got {key_values!r}"