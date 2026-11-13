import os
import sys
import types
import unittest
from unittest.mock import patch

import review


class GeminiRetryTests(unittest.TestCase):
    def test_thinking_config_error_retries_without_thinking_config(self):
        responses = iter([
            RuntimeError("INVALID_ARGUMENT: unsupported thinking_config"),
            types.SimpleNamespace(text='{"findings": []}'),
        ])
        calls = []

        class FakeModels:
            def generate_content(self, **kwargs):
                calls.append(kwargs)
                response = next(responses)
                if isinstance(response, Exception):
                    raise response
                return response

        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = lambda **kwargs: types.SimpleNamespace(models=FakeModels())
        fake_types = types.ModuleType("google.genai.types")
        fake_types.HttpOptions = lambda **kwargs: kwargs
        fake_types.Part = types.SimpleNamespace(from_bytes=lambda **kwargs: kwargs)
        fake_types.ThinkingConfig = lambda **kwargs: kwargs
        fake_types.GenerateContentConfig = lambda **kwargs: kwargs
        fake_genai.types = fake_types
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
             patch.dict(sys.modules, {
                 "google": fake_google,
                 "google.genai": fake_genai,
                 "google.genai.types": fake_types,
             }), \
             patch.object(review, "build_input", return_value=("Review this text.", None, None)):
            result = review.call_gemini({}, {}, [])

        self.assertEqual(result, [])
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
