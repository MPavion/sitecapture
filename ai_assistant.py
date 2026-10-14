import json
import re

try:
    import anthropic
    ANTHROPIC_OK = True
except ImportError:
    ANTHROPIC_OK = False

_SYSTEM = """\
You are a web scraping assistant. Analyse the URL and HTML snippet provided, then return ONLY a \
valid JSON object — no markdown, no explanation — with exactly these keys:

{
  "site_type": "e-learning | documentation | blog | marketing | portfolio | other",
  "content_confidence": 0.0,
  "recommended_depth": 3,
  "url_include_patterns": [],
  "url_exclude_patterns": [],
  "warnings": [],
  "notes": ""
}

Field guidance:
- site_type: best single label for this site
- content_confidence: 0–1, how confident you are this contains downloadable course content
- recommended_depth: 1–6, how deep the crawler should go (higher for deep course hierarchies)
- url_include_patterns: URL path fragments that typically lead to course/lesson pages \
  (e.g. "/lesson", "/module", "/course", "/watch", "/content")
- url_exclude_patterns: path fragments to skip \
  (e.g. "/privacy", "/terms", "/contact", "/about", "/careers", "/login", "/blog", "/store")
- warnings: list of concerns — login wall detected, JavaScript-heavy SPA, paywall, \
  pagination needed, or empty list
- notes: 2–3 sentence plain-English summary and any specific recommendations

Return ONLY the JSON object."""


def analyse(url: str, html: str, api_key: str, model: str) -> dict:
    """
    Fetch a one-shot site analysis from the Anthropic API.
    Returns a dict. On failure the dict contains an "error" key.
    """
    if not ANTHROPIC_OK:
        return {"error": "The 'anthropic' package is not installed. Run setup.bat to install it."}
    if not api_key:
        return {"error": "No Anthropic API key configured. Add it under Settings → AI Analysis."}

    client = anthropic.Anthropic(api_key=api_key)

    # Keep the payload lean — first 6 000 chars covers the nav, hero, and structure
    snippet = html[:6000]

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=800,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"URL: {url}\n\nHTML:\n{snippet}"
            }]
        )
    except anthropic.AuthenticationError:
        return {"error": "Invalid API key — check the key you entered in Settings."}
    except anthropic.RateLimitError:
        return {"error": "Anthropic rate limit reached. Wait a moment and try again."}
    except Exception as e:
        return {"error": f"API call failed: {e}"}

    text = msg.content[0].text.strip()

    # Tolerate models that wrap JSON in a markdown block
    m = re.search(r'\{.*\}', text, re.DOTALL)
    raw = m.group() if m else text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": f"Could not parse AI response:\n{text[:400]}"}
