"""Environment-backed non-secret runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class SettingsError(ValueError):
    """Raised when required runtime configuration is absent or inconsistent."""


def load_environment(root: Path) -> dict[str, str]:
    """Load ignored local values, with the process environment taking precedence."""

    values: dict[str, str] = {}
    env_path = root / ".env"
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    values.update(os.environ)
    return values


@dataclass(frozen=True, slots=True)
class EmbeddingSettings:
    """Validated configuration for the production Bedrock embedding provider."""

    aws_region: str
    model_id: str
    dimension: int
    aws_profile: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> EmbeddingSettings:
        region = values.get("AWS_REGION", "").strip()
        model_id = values.get("BEDROCK_EMBEDDING_MODEL_ID", "").strip()
        raw_dimension = values.get("EMBEDDING_DIM", "").strip()
        if not region:
            raise SettingsError("AWS_REGION is required for production embeddings")
        if not model_id:
            raise SettingsError("BEDROCK_EMBEDDING_MODEL_ID is required")
        try:
            dimension = int(raw_dimension)
        except ValueError as error:
            raise SettingsError("EMBEDDING_DIM must be an integer") from error
        if dimension <= 0:
            raise SettingsError("EMBEDDING_DIM must be positive")
        profile = values.get("AWS_PROFILE", "").strip() or None
        return cls(region, model_id, dimension, profile)
