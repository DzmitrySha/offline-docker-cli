"""Default values and shared types for offline-docker."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WheelPattern:
    pattern: str
    label: str


DEFAULT_DEB_PACKAGES = [
    "locales",
    "python3.12",
    "python3.12-venv",
    "python3.12-dev",
    "python3-pip",
    "git",
    "curl",
    "wget",
    "ca-certificates",
    "gnupg",
    "libgl1",
    "libglib2.0-0",
    "libsm6",
    "libxext6",
    "libxrender1",
    "ffmpeg",
]

DEFAULT_DOCKER_IMAGES = [
    "ubuntu:24.04",
    "node:22-bookworm-slim",
    "nginx:1.28-alpine",
    "redis:7-alpine",
    "aquasec/trivy:latest",
]

DEFAULT_CRITICAL_WHEELS = [
    WheelPattern("PyJWT-*.whl", "PyJWT"),
    WheelPattern("psycopg-*.whl", "psycopg"),
    WheelPattern("psycopg_binary-*.whl", "psycopg_binary"),
    WheelPattern("redis-*.whl", "redis"),
    WheelPattern("sqlalchemy-*.whl", "sqlalchemy"),
    WheelPattern("alembic-*.whl", "alembic"),
]
