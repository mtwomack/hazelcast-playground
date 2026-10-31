"""
Application settings.

Values come from environment variables, loaded from the `.env` file in the
project root if one exists (see `.env.example`). Real environment variables
take priority over `.env`. Set ENV_FILE to load a different file.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(os.getenv("ENV_FILE") or PROJECT_ROOT / ".env")

HZ_MEMBERS = [m.strip() for m in os.getenv("HZ_MEMBERS", "127.0.0.1:5701").split(",") if m.strip()]
HZ_CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
HZ_CONTAINER = os.getenv("HZ_CONTAINER", "hazelcast")   # Docker container name for /stats
