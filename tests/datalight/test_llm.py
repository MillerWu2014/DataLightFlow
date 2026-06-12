import unittest
from unittest.mock import patch

from datalight.llm import (
    LLMRequestTimeoutError,
    OpenAICompatibleLLMClient,
    StaticLLMClient,
    _post_json,
    safe_generate,
)
from urllib import error


class PostJsonTimeoutTest(unittest.TestCase):
    def test_timeout_raises_llm_request_timeout_error(self):
        with patch("datalight.llm.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(LLMRequestTimeoutError) as ctx:
                _post_json("http://127.0.0.1:1234/v1/chat/completions", {"model": "x"}, 180)
        self.assertIn("180s", str(ctx.exception))

    def test_urlerror_timeout_raises(self):
        with patch(
            "datalight.llm.request.urlopen",
            side_effect=error.URLError(TimeoutError("timed out")),
        ):
            with self.assertRaises(LLMRequestTimeoutError):
                _post_json("http://127.0.0.1:1234/v1/chat/completions", {"model": "x"}, 120)

    def test_urlerror_non_timeout_still_raises(self):
        with patch(
            "datalight.llm.request.urlopen",
            side_effect=error.URLError("connection refused"),
        ):
            with self.assertRaises(ConnectionError):
                _post_json("http://127.0.0.1:1234/v1/chat/completions", {"model": "x"}, 120)

    def test_connection_reset_raises_connection_error(self):
        with patch(
            "datalight.llm.request.urlopen",
            side_effect=ConnectionResetError(54, "Connection reset by peer"),
        ):
            with self.assertRaises(ConnectionError) as ctx:
                _post_json("http://127.0.0.1:1234/v1/chat/completions", {"model": "x"}, 120)
        self.assertIn("Connection reset by peer", str(ctx.exception))


class SafeGenerateTest(unittest.TestCase):
    def test_continues_after_timeout(self):
        calls = {"count": 0}

        def flaky_transport(url, payload, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise LLMRequestTimeoutError("LLM request timed out after 1s: test")
            return {"choices": [{"message": {"content": "ok"}}]}

        client = OpenAICompatibleLLMClient(transport=flaky_transport, timeout_sec=1)
        self.assertEqual(safe_generate(client, ["a", "b"]), ["", "ok"])

    def test_continues_after_connection_error(self):
        calls = {"count": 0}

        def flaky_transport(url, payload, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectionError("LLM request failed: test: Connection reset by peer")
            return {"choices": [{"message": {"content": "ok"}}]}

        client = OpenAICompatibleLLMClient(transport=flaky_transport)
        self.assertEqual(safe_generate(client, ["a", "b"]), ["", "ok"])

    def test_static_client_unaffected(self):
        client = StaticLLMClient(["one", "two"])
        self.assertEqual(safe_generate(client, ["p1", "p2"]), ["one", "two"])


if __name__ == "__main__":
    unittest.main()
