import os
import unittest

from dotenv import load_dotenv

load_dotenv()


@unittest.skipUnless(
    os.getenv("RUN_GEMINI_SMOKE") == "1" and os.getenv("GEMINI_API_KEY"),
    "set RUN_GEMINI_SMOKE=1 and configure GEMINI_API_KEY to run the live smoke test",
)
class GeminiSmokeTests(unittest.TestCase):
    def test_configured_gemini_model_responds(self):
        from google import genai
        from google.genai import types

        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=120_000),
        )
        response = client.models.generate_content(model=model, contents="Reply with the word OK")
        self.assertTrue((response.text or "").strip())


if __name__ == "__main__":
    unittest.main()
