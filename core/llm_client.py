"""
core/llm_client.py — One function, three independent LLM providers behind it.

Why this exists: Gemini alone has now broken your run twice from provider-
side issues (early model deprecation). Instead of depending on one company's
uptime, this tries three genuinely free, no-credit-card providers in order:

  1. Gemini (Google AI Studio)   — GEMINI_API_KEY
  2. Groq (LPU hardware, fast)   — GROQ_API_KEY   — https://console.groq.com
  3. OpenRouter (many free models) — OPENROUTER_API_KEY — https://openrouter.ai

If one provider is down, deprecated, or rate-limited, the next one picks up
automatically — matcher.py and cv_tailor.py just call generate_text() and
don't need to know which provider actually answered.

Every provider here has a genuinely permanent free tier with no credit card
required (verified June 2026) — this isn't trial credits that expire.
"""

import os
import requests

# Auto-updating Gemini alias first, explicit fallbacks after —
# see the note in matcher.py history: Google has been retiring dated
# model names early and inconsistently ahead of their announced schedule.
GEMINI_MODEL_CANDIDATES = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-3.1-flash-lite"]
GROQ_MODEL = "llama-3.3-70b-versatile"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def _try_gemini(prompt, api_key=None):
    from google import genai
    client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))
    last_error = None
    for model_name in GEMINI_MODEL_CANDIDATES:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text
        except Exception as e:
            last_error = e
            continue
    raise last_error


def _try_groq(prompt, api_key=None):
    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _try_openrouter(prompt, api_key=None):
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


PROVIDERS = [
    ("Gemini", _try_gemini),
    ("Groq", _try_groq),
    ("OpenRouter", _try_openrouter),
]


def generate_text(prompt, gemini_key=None, groq_key=None, openrouter_key=None):
    """
    Tries each configured provider in order, returns the first successful
    response. Raises the last error only if every provider fails.
    """
    keys = {"Gemini": gemini_key, "Groq": groq_key, "OpenRouter": openrouter_key}
    last_error = None

    for name, fn in PROVIDERS:
        try:
            result = fn(prompt, keys.get(name))
            return result
        except Exception as e:
            print(f"[llm_client] {name} failed ({e}), trying next provider...")
            last_error = e
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(generate_text("Say 'hello world' and nothing else."))
