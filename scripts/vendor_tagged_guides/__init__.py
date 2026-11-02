"""Vendor an upstream guide at a pinned tag into a consuming repository.

A vendored guide is a verbatim copy of an upstream document at one known tag,
not a merge of the upstream text into a repository-owned document. Three
transformations make that copy usable in a checkout:

- relative links outside protected regions are rewritten for the pinned tag,
  so the copy cannot silently follow the upstream default branch;
- links between two guides that are imported together stay local, so they
  resolve inside the consuming repository;
- a canonical "Imported from" note is inserted after the first heading, and
  bounded MD013 exemptions are added where the consumer's formatter cannot
  break a line.

Protected regions include fenced code, inline code, footnote definitions, and
HTML comments. Their contents remain byte-for-byte unchanged.

The transformations are pure standard-library functions, so a test can call
them without a formatter or a process. :func:`vendor` composes them with an
injected ``format_files`` callable; the sibling ``vendor_tagged_guides_cli``
module supplies the Cyclopts front end and the cuprum process boundary.

The package is split by concern: :mod:`~vendor_tagged_guides.config` validates
an import, :mod:`~vendor_tagged_guides.masking` finds protected text,
:mod:`~vendor_tagged_guides.links` rewrites destinations,
:mod:`~vendor_tagged_guides.note` inserts the provenance record,
:mod:`~vendor_tagged_guides.exemptions` adds Markdown-lint exemptions, and
:mod:`~vendor_tagged_guides.pipeline` composes them. The public API is
re-exported here, so a caller imports only this package.

Examples
--------
Vendor two cuprum guides from a checkout of the upstream ``docs/`` directory::

    uv run --script scripts/vendor_tagged_guides_cli.py \\
        --tag v0.2.0-beta2 \\
        --repository leynos/cuprum \\
        --source ../cuprum/docs \\
        --output docs \\
        --map users-guide.md=cuprum-users-guide.md \\
        --map v0-2-0-migration-guide.md=cuprum-v0-2-0-migration-guide.md

The package imports nothing beyond the standard library, so it remains
importable under Python 3.13 even though the front end targets Python 3.14.
"""

from __future__ import annotations

from .config import (
    DEFAULT_CODE_LINE_LENGTH,
    DEFAULT_LINE_LENGTH,
    DEFAULT_SOURCE_PATH,
    VENDOR_ERRORS,
    VendorConfig,
    VendorError,
    validate,
)
from .exemptions import (
    DISABLE_M013,
    ENABLE_M013,
    insert_exemptions,
    long_lines,
)
from .note import IMPORT_MARKER, NOTE_TEMPLATE
from .pipeline import convert, vendor

__all__ = (
    "DEFAULT_CODE_LINE_LENGTH",
    "DEFAULT_LINE_LENGTH",
    "DEFAULT_SOURCE_PATH",
    "DISABLE_M013",
    "ENABLE_M013",
    "IMPORT_MARKER",
    "NOTE_TEMPLATE",
    "VENDOR_ERRORS",
    "VendorConfig",
    "VendorError",
    "convert",
    "insert_exemptions",
    "long_lines",
    "validate",
    "vendor",
)