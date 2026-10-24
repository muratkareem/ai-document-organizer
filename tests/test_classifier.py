import json
from unittest.mock import MagicMock
from urllib.error import URLError, HTTPError
import pytest
from pydantic import ValidationError
from organizer.classifier import OllamaClassifier, ClassificationError
from organizer.models import Classification, Category


def client_with(body):
    client = OllamaClassifier(retries=0, max_chars=5)
    client.opener = MagicMock()
    client.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(body).encode()
    return client


def test_structured_request():
    client = client_with({"message": {"content": '{"category":"Education","reason":"Lecture"}'}})
    assert client.classify("notes.txt", "abcdefgh").category == Category.EDUCATION
    request = client.opener.open.call_args.args[0]
    payload = json.loads(request.data)
    assert payload["format"]["additionalProperties"] is False
    assert json.loads(payload["messages"][1]["content"])["text"] == "abcde"
    assert "untrusted" in payload["messages"][0]["content"]


@pytest.mark.parametrize("value", [
    {"category": "../../bad", "reason": "bad"},
    {"category": "Education", "reason": "  "},
    {"category": "Legal", "reason": "x", "path": "/tmp"},
    {"category": "Finance"},
])
def test_invalid_classification(value):
    with pytest.raises(ValidationError):
        Classification.model_validate(value)


@pytest.mark.parametrize("body", [{}, [], {"message": {"content": "not JSON"}},
    {"message": {"content": '{"category":"Wrong","reason":"test"}'}}])
def test_malformed_response(body):
    with pytest.raises(ClassificationError, match="invalid classification"):
        client_with(body).classify("x", "y")


def test_connection_failure():
    client = client_with({})
    client.retries = 1
    client.opener.open.side_effect = URLError("offline")
    with pytest.raises(ClassificationError, match="ollama serve"):
        client.classify("x", "y")
    assert client.opener.open.call_count == 2


def test_missing_model():
    client = client_with({})
    client.opener.open.side_effect = HTTPError("url", 404, "missing", {}, None)
    with pytest.raises(ClassificationError, match="ollama pull"):
        client.classify("x", "y")


def test_timeout():
    client = client_with({})
    client.opener.open.side_effect = TimeoutError()
    with pytest.raises(ClassificationError, match="timeout"):
        client.classify("x", "y")
