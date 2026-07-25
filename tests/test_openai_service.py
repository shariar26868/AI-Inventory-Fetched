import asyncio
import unittest
from unittest.mock import patch

from app.services import openai_service


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        if not self._responses:
            raise AssertionError("No more fake responses")
        return self._responses.pop(0)


class ExtractItemsWithAiTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_after_rate_limit_and_returns_ai_results(self):
        async def fake_sleep(_seconds):
            return None

        success_payload = {
            "choices": [{"message": {"content": '{"items": [{"item_name": "Desk", "item_code": "D-1", "description": "Wood desk", "qty": "2", "manufacturer": "Acme", "commodity": "Furniture"}]}' }}]
        }

        fake_client = FakeAsyncClient([
            FakeResponse(429, headers={"Retry-After": "1"}),
            FakeResponse(200, success_payload),
        ])

        with patch("app.services.openai_service.httpx.AsyncClient", return_value=fake_client), \
             patch("app.services.openai_service.asyncio.sleep", side_effect=fake_sleep):
            result = await openai_service.extract_items_with_ai([{"raw_text": "A desk"}])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_name"], "Desk")


if __name__ == "__main__":
    unittest.main()
