import io
import json
from collections.abc import Mapping
from typing import Any

import pytest

from backend.app.memory.embedding import (
    BedrockTitanEmbeddingProvider,
    DeterministicTestEmbeddingProvider,
    EmbeddingAuthenticationError,
    EmbeddingDimensionError,
    EmbeddingInvocationError,
    MalformedEmbeddingResponseError,
)
from backend.app.settings import EmbeddingSettings, SettingsError


class _Client:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def invoke_model(
        self,
        *,
        modelId: str,
        body: bytes,
        accept: str,
        contentType: str,
    ) -> Mapping[str, Any]:
        self.requests.append(
            {
                "modelId": modelId,
                "body": body,
                "accept": accept,
                "contentType": contentType,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, dict)
        return response


class _ProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


def _settings(dimension: int = 4) -> EmbeddingSettings:
    return EmbeddingSettings("eu-west-2", "amazon.titan-embed-text-v2:0", dimension)


def _response(vector: object) -> dict[str, object]:
    return {
        "body": io.BytesIO(
            json.dumps({"embedding": vector, "inputTextTokenCount": 7}).encode("utf-8")
        )
    }


def test_embedding_settings_require_explicit_production_configuration() -> None:
    with pytest.raises(SettingsError, match="AWS_REGION"):
        EmbeddingSettings.from_mapping({})
    with pytest.raises(SettingsError, match="EMBEDDING_DIM"):
        EmbeddingSettings.from_mapping(
            {
                "AWS_REGION": "eu-west-2",
                "BEDROCK_EMBEDDING_MODEL_ID": "model",
                "EMBEDDING_DIM": "not-an-int",
            }
        )


def test_bedrock_provider_sends_explicit_model_dimension_and_normalization() -> None:
    client = _Client([_response([0.1, 0.2, 0.3, 0.4])])
    provider = BedrockTitanEmbeddingProvider(_settings(), client=client)

    result = provider.embed("measured anomaly")

    assert result.vector == (0.1, 0.2, 0.3, 0.4)
    assert result.metadata.test_only is False
    request = json.loads(bytes(client.requests[0]["body"]))
    assert request == {
        "inputText": "measured anomaly",
        "dimensions": 4,
        "normalize": True,
        "embeddingTypes": ["float"],
    }


@pytest.mark.parametrize("payload", [None, [], [0.1, "bad", 0.3, 0.4]])
def test_bedrock_provider_rejects_malformed_embedding(payload: object) -> None:
    provider = BedrockTitanEmbeddingProvider(_settings(), client=_Client([_response(payload)]))

    with pytest.raises(MalformedEmbeddingResponseError):
        provider.embed("measured anomaly")


def test_bedrock_provider_rejects_wrong_dimension() -> None:
    provider = BedrockTitanEmbeddingProvider(_settings(), client=_Client([_response([0.1, 0.2])]))

    with pytest.raises(EmbeddingDimensionError, match="expected 4"):
        provider.embed("measured anomaly")


def test_bedrock_provider_retries_bounded_transient_failure() -> None:
    client = _Client([_ProviderError("ThrottlingException"), _response([0.1] * 4)])
    sleeps: list[float] = []
    provider = BedrockTitanEmbeddingProvider(
        _settings(),
        client=client,
        sleeper=sleeps.append,
    )

    assert provider.embed("measured anomaly").vector == (0.1,) * 4
    assert sleeps == [1.0]
    assert len(client.requests) == 2


def test_bedrock_provider_stops_after_configured_attempts() -> None:
    client = _Client([_ProviderError("ThrottlingException") for _ in range(3)])
    sleeps: list[float] = []
    provider = BedrockTitanEmbeddingProvider(
        _settings(),
        client=client,
        max_attempts=3,
        sleeper=sleeps.append,
    )

    with pytest.raises(EmbeddingInvocationError, match="ThrottlingException"):
        provider.embed("measured anomaly")

    assert len(client.requests) == 3
    assert sleeps == [1.0, 2.0]


def test_bedrock_provider_classifies_authentication_without_echoing_details() -> None:
    provider = BedrockTitanEmbeddingProvider(
        _settings(),
        client=_Client([_ProviderError("AccessDeniedException")]),
    )

    with pytest.raises(EmbeddingAuthenticationError, match="authentication or authorization"):
        provider.embed("measured anomaly")


def test_test_only_provider_is_deterministic_and_explicitly_labeled() -> None:
    provider = DeterministicTestEmbeddingProvider(8)

    first = provider.embed("temperature noise quality")
    second = provider.embed("temperature noise quality")

    assert first.vector == second.vector
    assert len(first.vector) == 8
    assert first.metadata.test_only is True
