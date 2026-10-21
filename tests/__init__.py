"""Test package."""

from __future__ import annotations

import atexit
import os
import tempfile

if not os.environ.get("SU_MCP_LOG_DIR"):
    _log_dir = tempfile.mkdtemp(prefix="su-mcp-test-log-")
    os.environ["SU_MCP_LOG_DIR"] = _log_dir
    atexit.register(lambda: __import__("shutil").rmtree(_log_dir,
                                                        ignore_errors=True))
