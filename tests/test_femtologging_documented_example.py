"""Execute the published Femtologging callback-enrichment example.

The document contract proves only that every fence carries a marker. The
guide also presents this example as working code, so the test runs the
shipped snippet against the real library and checks the record the documented
configuration delivers. An edit that reverts the example to an unsupported
API therefore fails here instead of misleading a reader.
"""

from __future__ import annotations

from pathlib import Path

from femtologging import get_logger
from tested_example_test_support import load_tested_examples

GUIDE_PATH = (
    Path(__file__).resolve().parents[1]
    / "documentation-library"
    / "femtologging-users-guide.md"
)
#: The accepted-enrichment example in the Femtologging guide.
ENRICHMENT_EXAMPLE = "femtologging-callback-enrichment-accepted"


class RecordCollector:
    """Collect structured records delivered through ``handle_record``."""

    def __init__(self) -> None:
        """Initialize the empty collection of received records."""
        self.records: list[dict[str, object]] = []

    def handle(self, logger: str, level: str, message: str) -> None:
        """Provide the legacy handler interface required by ``add_handler``."""
        _ = (self.records, logger, level, message)

    def handle_record(self, record: dict[str, object]) -> None:
        """Store a record snapshot emitted by the logger worker."""
        self.records.append(dict(record))

    def flush(self) -> bool:
        """Acknowledge the flush protocol used by the configured logger."""
        _ = self.records
        return True


def published_example_body(identifier: str) -> str:
    """Return the body of the named example, exactly as the guide ships it."""
    for example in load_tested_examples(GUIDE_PATH):
        if example.identifier == identifier:
            return example.body
    message = f"no published example named {identifier!r} in {GUIDE_PATH}"
    raise AssertionError(message)


def test_published_callback_enrichment_example_stamps_delivered_records() -> None:
    """The guide's example configures a filter that enriches its records."""
    body = published_example_body(ENRICHMENT_EXAMPLE)
    namespace: dict[str, object] = {}
    # The example is executed exactly as published; loading it through the
    # shared loader keeps the guide, not a copy, as the fixture.
    exec(compile(body, str(GUIDE_PATH), "exec"), namespace)  # noqa: S102

    collector = RecordCollector()
    logger = get_logger("service")
    logger.add_handler(collector)

    assert logger.log("INFO", "request accepted") is not None, (
        "the documented filter configuration must accept the record"
    )
    assert logger.flush_handlers(), "service handler delivery should flush"

    assert len(collector.records) == 1, (
        f"the documented configuration must deliver one record, got "
        f"{collector.records!r}"
    )
    metadata = collector.records[0].get("metadata")
    assert isinstance(metadata, dict), f"unexpected metadata payload: {metadata!r}"
    assert metadata.get("key_values") == {
        "request_id": "req-123",
        "user_id": "42",
        "cache_hit": "False",
    }, f"the documented filter must enrich the record, got {metadata!r}"