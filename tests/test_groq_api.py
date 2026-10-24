import json

import pytest

from dictation.groq_api import GroqClient, GroqError, ModelUnavailable, pick_cleanup_model


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_missing_key_is_reported():
    with pytest.raises(GroqError, match="API key"):
        GroqClient("")


def test_transcribe_sends_audio_and_options():
    session = FakeSession(FakeResponse(200, {"text": " hello world "}))
    client = GroqClient("key", session=session)

    text = client.transcribe(b"RIFF", "whisper-large-v3-turbo", language="en", vocabulary=["Groq"])

    assert text == "hello world"
    url, kwargs = session.calls[0]
    assert url.endswith("/audio/transcriptions")
    assert kwargs["headers"]["Authorization"] == "Bearer key"
    assert kwargs["data"]["language"] == "en"
    assert kwargs["data"]["prompt"] == "Groq"
    assert kwargs["files"]["file"][1] == b"RIFF"


def test_transcribe_omits_empty_language():
    session = FakeSession(FakeResponse(200, {"text": "hi"}))
    GroqClient("key", session=session).transcribe(b"", "m")
    assert "language" not in session.calls[0][1]["data"]


def test_api_error_message_is_surfaced():
    session = FakeSession(FakeResponse(401, {"error": {"message": "Invalid API Key"}}))
    with pytest.raises(GroqError, match="401: Invalid API Key"):
        GroqClient("bad", session=session).transcribe(b"", "m")


def test_clean_up_wraps_transcript_and_strips_echoed_tags():
    reply = {"choices": [{"message": {"content": "<transcript>\nHello, world.\n</transcript>"}}]}
    session = FakeSession(FakeResponse(200, reply))

    cleaned = GroqClient("key", session=session).clean_up("um hello world", "llama", ["Groq"])

    assert cleaned == "Hello, world."
    body = session.calls[0][1]["json"]
    assert body["messages"][1]["content"] == "<transcript>\num hello world\n</transcript>"
    assert "Groq" in body["messages"][0]["content"]


def test_clean_up_falls_back_to_transcript_when_reply_is_empty():
    reply = {"choices": [{"message": {"content": "  "}}]}
    session = FakeSession(FakeResponse(200, reply))
    assert GroqClient("key", session=session).clean_up("raw text", "llama") == "raw text"


def test_check_key_rejects_bad_key():
    class Session(FakeSession):
        def get(self, url, **kwargs):
            return self.post(url, **kwargs)

    session = Session(FakeResponse(401, {"error": {"message": "Invalid API Key"}}))
    with pytest.raises(GroqError, match="Invalid API Key"):
        GroqClient("bad", session=session).check_key()
    assert session.calls[0][0].endswith("/models")


def test_retired_model_raises_model_unavailable():
    message = "The model `llama-3.3-70b-versatile` does not exist or you do not have access to it."
    session = FakeSession(FakeResponse(404, {"error": {"message": message}}))
    with pytest.raises(ModelUnavailable):
        GroqClient("key", session=session).clean_up("hi", "llama-3.3-70b-versatile")


def test_reasoning_model_gets_low_effort_and_thinking_is_stripped():
    reply = {"choices": [{"message": {"content": "<think>easy</think>\nHi there."}}]}
    session = FakeSession(FakeResponse(200, reply))

    cleaned = GroqClient("key", session=session).clean_up("hi there", "openai/gpt-oss-120b")

    assert cleaned == "Hi there."
    assert session.calls[0][1]["json"]["reasoning_effort"] == "low"


def test_pick_cleanup_model_prefers_known_good_models():
    assert pick_cleanup_model(["whisper-large-v3", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]) == "openai/gpt-oss-120b"
    assert pick_cleanup_model(["whisper-large-v3", "some/new-model"]) == "some/new-model"
    assert pick_cleanup_model(["whisper-large-v3-turbo", "meta-llama/llama-guard-4-12b"]) is None
