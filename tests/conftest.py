"""Pytest configuration — apply numpy compatibility shim before any test imports."""
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Apply numpy 2.0 compatibility shim before anything imports chromadb
import app.compat  # noqa: F401, E402
