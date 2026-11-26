# MCP test evidence

Run from a clean checkout:

```sh
python3 docs/render_mcp_catalog.py --check
python3 docs/audit_mcp_tests.py --write
```

The report `docs/mcp-test-evidence.json` is a dated-by-source-fingerprint snapshot, not a guarantee that each tool is fully tested. The runner executes the existing offline unittest suite (test_*.py, not live_* scripts) and records only tool names, test IDs, layers and return/exception categories. It does not record media, arguments, results or credentials. Calls outside the current in-process test, subprocess calls and mocked-away functions are excluded. Existing unit tests may use fake backends and synthetic media.

The public catalogue establishes discovery and profile membership; the evidence report separates literal references, calls observed in passing tests, and actual Production dispatch entry/return. A return is not proof of an asserted correct outcome. A tool with no recorded dispatch may have lower-level or subprocess tests. Use this inventory to prioritize targeted tests rather than to claim full functional or security coverage.

## Continuous evidence and desktop boundary

The [GitHub Actions workflow](https://github.com/jackjosias/ccer-mcp/actions/workflows/native-source-check.yml) installs FFmpeg and eSpeak NG on disposable runners, executes the instrumented suite and publishes the current `mcp-test-evidence` artifact (30-day retention). The committed JSON snapshot may differ from the latest CI artifact because optional dependencies differ. Inspect the artifact tied to the desired run and commit.

The test `test_mcp_desktop_roundtrip_with_simulated_slint_peer` exercises JSON-RPC, DirectGateway, Production, the native routing layer, and a real Unix socket connected to a simulated peer. Frames are synthetic test bytes; the test checks image hashes, BEFORE/AFTER ordering, single-use authorization, denial of replay, and the absence of physical X11 input. It does **not** validate a real Concat window, image decoding, native visual appearance, or editorial success. The CI gate for all tool dispatch returns is not live GUI acceptance. Live acceptance requires a separately attested Concat session and human-visible BEFORE/AFTER evidence.

See [catalogue](mcp-tools.json), [privacy](../PRIVACY.md) and [security](../SECURITY.md).
