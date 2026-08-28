"""Surgical single-field edits to sites.yaml.

`SiteConfigManager.save_sites_config()` rewrites the whole file from a parsed
dict, which reformats it and drops every comment. That is the right call when
saving a site the user edited in the dashboard, but far too broad for changing
one value - a provisioning script that corrects `db_host` should not silently
reflow an operator's hand-maintained config.

This edits the single line belonging to one site's key and leaves the rest of
the file byte-for-byte identical.
"""

from __future__ import annotations

import re
from pathlib import Path

SITES_YAML = Path(__file__).resolve().parents[2] / "config" / "sites.yaml"


class SiteFieldEditError(RuntimeError):
    """Raised when the target site or key cannot be located in sites.yaml."""


def _format(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    # Quote anything YAML would otherwise reinterpret as a non-string.
    if text == "" or re.search(r"[:#\[\]{}&*!|>'\"%@`]", text) or text.strip() != text:
        bs = chr(92)
        return '"' + text.replace(bs, bs + bs).replace('"', bs + '"') + '"'
    return text


def set_site_field(site: str, key: str, value, path: Path | None = None) -> str:
    """Set `key` for `site` in sites.yaml. Returns the previous raw value."""
    target = path or SITES_YAML
    lines = target.read_text(encoding="utf-8").split("\n")

    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == f"{site}:")
    except StopIteration:
        raise SiteFieldEditError(f"site {site!r} not found in {target}") from None

    for i in range(start + 1, len(lines)):
        # A non-indented or single-indented non-blank line starts the next site.
        if lines[i].strip() and not lines[i].startswith("    "):
            break
        stripped = lines[i].strip()
        if stripped.startswith(f"{key}:"):
            indent = " " * (len(lines[i]) - len(lines[i].lstrip()))
            previous = stripped[len(key) + 1:].strip()
            lines[i] = f"{indent}{key}: {_format(value)}"
            target.write_text("\n".join(lines), encoding="utf-8")
            return previous

    raise SiteFieldEditError(f"key {key!r} not found under site {site!r} in {target}")
