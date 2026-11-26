# MCP test evidence

Run from a clean checkout:

```sh
python3 docs/render_mcp_catalog.py --check
python3 docs/audit_mcp_tests.py --write
```

The report `docs/mcp-test-evidence.json` is a dated-by-source-fingerprint snapshot, not a guarantee that each tool is fully tested. The runner executes the existing offline unittest suite (test_*.py, not live_* scripts) and records only tool names, test IDs, layers and return/exception categories. It does not record media, arguments, results or credentials. Calls outside the current in-process test, subprocess calls and mocked-away functions are excluded. Existing unit tests may use fake backends and synthetic media.

The public catalogue establishes discovery and profile membership; the evidence report separates literal references, calls observed in passing tests, and actual Production dispatch entry/return. A return is not proof of an asserted correct outcome. A tool with no recorded dispatch may have lower-level or subprocess tests. Use this inventory to prioritize targeted tests rather than to claim full functional or security coverage.

See [catalogue](mcp-tools.json), [privacy](../PRIVACY.md) and [security](../SECURITY.md).
