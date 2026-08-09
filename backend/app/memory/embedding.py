"""Production Bedrock and explicitly TEST-ONLY embedding providers."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from time import sleep
from typing import Any, Protocol, cast

from backend.app.memory.models import EmbeddingResult, ProviderMetadata
from backend.app.settings import EmbeddingSettings


class EmbeddingError(RuntimeError):
    """Base class for secret-safe embedding failures."""


class EmbeddingAuthenticationError(EmbeddingError):
    """The production provider is not authenticated or authorized."""


class EmbeddingInvocationError(EmbeddingError):
    """The provider failed to complete an invocation."""


class MalformedEmbeddingResponseError(EmbeddingError):
    """The provider returned a response without a valid numeric embedding."""


class EmbeddingDimensionError(EmbeddingError):
    """The returned vector does not match the configured schema dimension."""


class EmbeddingProvider(Protocol):
    @property
    def metadata(self) -> ProviderMetadata: ...

    def embed(self, text: str) -> EmbeddingResult: ...


class _ResponseBody(Protocol):
    def read(self) -> bytes: ...


class _BedrockClient(Protocol):
    def invoke_model(
        self,
        *,
        modelId: str,
        body: bytes,
        accept: str,
        contentType: str,
    ) -> Mapping[str, Any]: ...


def _validated_vector(raw: object, expected_dimension: int) -> tuple[float, ...]:
    if not isinstance(raw, list) or not raw:
        raise MalformedEmbeddingResponseError("embedding response lacks a numeric vector")
    values: list[float] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MalformedEmbeddingResponseError("embedding vector contains a non-number")
        number = float(value)
        if not math.isfinite(number):
            raise MalformedEmbeddingResponseError("embedding vector contains a non-finite number")
        values.append(number)
    if len(values) != expected_dimension:
        raise EmbeddingDimensionError(
            f"embedding dimension mismatch: expected {expected_dimension}, received {len(values)}"
        )
    return tuple(values)


def _error_code(error: Exception) -> str:
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        raw_error = response.get("Error")
        if isinstance(raw_error, dict):
            code = raw_error.get("Code")
            if isinstance(code, str):
                return code
    return type(error).__name__


class BedrockTitanEmbeddingProvider:
    """Amazon Titan Text Embeddings V2 through Bedrock InvokeModel."""

    _AUTH_CODES = frozenset(
        {
            "AccessDeniedException",
            "ExpiredTokenException",
            "InvalidClientTokenId",
            "NoCredentialsError",
            "PartialCredentialsError",
            "UnrecognizedClientException",
        }
    )
    _RETRY_CODES = frozenset(
        {
            "ConnectTimeoutError",
            "EndpointConnectionError",
            "InternalServerException",
            "ModelNotReadyException",
            "ModelTimeoutException",
            "ReadTimeoutError",
            "ServiceUnavailableException",
            "ThrottlingException",
        }
    )

    def __init__(
        self,
        settings: EmbeddingSettings,
        *,
        client: _BedrockClient | None = None,
        max_attempts: int = 7,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self._settings = settings
        self._client = client if client is not None else self._build_client(settings)
        self._max_attempts = max_attempts
        self._sleeper = sleeper

    @staticmethod
    def _build_client(settings: EmbeddingSettings) -> _BedrockClient:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        try:
            session = boto3.Session(
                profile_name=settings.aws_profile,
                region_name=settings.aws_region,
            )
            return cast(
                _BedrockClient,
                session.client(
                    "bedrock-runtime",
                    region_name=settings.aws_region,
                    config=Config(
                        connect_timeout=5,
                        read_timeout=30,
                        retries={"max_attempts": 1, "mode": "standard"},
                    ),
                ),
            )
        except Exception as error:
            code = _error_code(error)
            if code == "MissingDependencyException":
                raise EmbeddingAuthenticationError(
                    "AWS login credential provider requires the botocore CRT dependency"
                ) from error
            raise EmbeddingAuthenticationError(
                "Bedrock client could not load AWS credentials"
            ) from error

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider="amazon-bedrock",
            model_id=self._settings.model_id,
            dimension=self._settings.dimension,
            region=self._settings.aws_region,
            test_only=False,
        )

    def embed(self, text: str) -> EmbeddingResult:
        normalized = text.strip()
        if not normalized:
            raise ValueError("embedding input must not be empty")
        request = json.dumps(
            {
                "inputText": normalized,
                "dimensions": self._settings.dimension,
                "normalize": True,
                "embeddingTypes": ["float"],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        for attempt in range(self._max_attempts):
            try:
                response = self._client.invoke_model(
                    modelId=self._settings.model_id,
                    body=request,
                    accept="application/json",
                    contentType="application/json",
                )
                return self._parse_response(response)
            except EmbeddingError:
                raise
            except Exception as error:
                code = _error_code(error)
                if code in self._AUTH_CODES:
                    raise EmbeddingAuthenticationError(
                        "Bedrock embedding authentication or authorization failed"
                    ) from error
                if code not in self._RETRY_CODES or attempt + 1 == self._max_attempts:
                    raise EmbeddingInvocationError(
                        f"Bedrock embedding invocation failed ({code})"
                    ) from error
                self._sleeper(min(1.0 * (2**attempt), 8.0))
        raise AssertionError("embedding retry loop exited unexpectedly")

    def _parse_response(self, response: Mapping[str, Any]) -> EmbeddingResult:
        body = response.get("body")
        if body is None or not hasattr(body, "read"):
            raise MalformedEmbeddingResponseError("Bedrock response body is missing")
        try:
            payload = json.loads(cast(_ResponseBody, body).read())
        except (TypeError, ValueError) as error:
            raise MalformedEmbeddingResponseError(
                "Bedrock response body is not valid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise MalformedEmbeddingResponseError("Bedrock response is not an object")
        vector = _validated_vector(payload.get("embedding"), self._settings.dimension)
        raw_token_count = payload.get("inputTextTokenCount")
        token_count = raw_token_count if isinstance(raw_token_count, int) else None
        return EmbeddingResult(vector, self.metadata, token_count)


class DeterministicTestEmbeddingProvider:
    """Deterministic token hashing for unit tests; never production evidence."""

    def __init__(self, dimension: int = 32) -> None:
        if dimension < 4:
            raise ValueError("test embedding dimension must be at least four")
        self._dimension = dimension

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider="deterministic-token-hash",
            model_id="test-only-v1",
            dimension=self._dimension,
            region=None,
            test_only=True,
        )

    def embed(self, text: str) -> EmbeddingResult:
        tokens = [token for token in text.lower().replace("_", " ").split() if token]
        if not tokens:
            raise ValueError("embedding input must not be empty")
        vector = [0.0] * self._dimension
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0.0:
            vector[0] = 1.0
            magnitude = 1.0
        normalized = tuple(value / magnitude for value in vector)
        return EmbeddingResult(normalized, self.metadata, len(tokens))
