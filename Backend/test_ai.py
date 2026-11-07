from dotenv import load_dotenv
load_dotenv()
import os, sys, time
from google import genai
from google.genai import types

model = sys.argv[1] if len(sys.argv) > 1 else os.environ["GEMINI_MODEL"]
c = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                 http_options=types.HttpOptions(timeout=120000))
t = time.time()
try:
    r = c.models.generate_content(model=model, contents="Reply with the word OK")
    print("Reply:", r.text, "| model:", model, "| took", round(time.time() - t, 1), "seconds")
except Exception as e:
    print("FAILED after", round(time.time() - t, 1), "seconds:", str(e)[:300])