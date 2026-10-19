"""Safe Gemini helper: quota/network errors do not crash Flask routes."""
import os
from dotenv import load_dotenv
from google import genai
load_dotenv()
_key=os.getenv("GEMINI_API_KEY")
client=genai.Client(api_key=_key) if _key else None

def ask_ai(prompt):
    if client is None: return "AI is temporarily unavailable because GEMINI_API_KEY is not configured."
    try:
        response=client.models.generate_content(model="gemini-2.5-flash",contents=prompt)
        return response.text or "AI returned an empty response. Please try again."
    except Exception as exc:
        print("Gemini request failed:",repr(exc)); msg=str(exc).lower()
        if any(token in msg for token in ("429","quota","resource_exhausted","rate limit")):
            return "Gemini API quota/rate limit reached. Please try again after the quota resets."
        return "AI service is temporarily unavailable. Please try again later."
