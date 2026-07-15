"""
Fieldnote — Gemini connection test
Tries Gemini first; falls back to Groq + Gemma 2 (Google's open-source model).
Both paths are free. Press Run to verify.
"""
import os
import sys

# ── Secret detection ──────────────────────────────────────────────────────────
GOOGLE_API_KEY = (
    os.getenv("GOOGLE_API_KEY")
    or os.getenv("Google_API_Key")
    or os.getenv("Gemini")
)
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROQ")

if not GOOGLE_API_KEY and not GROQ_API_KEY:
    print("❌  No API key found.\n")
    print("    Option A — Gemini (Google AI Studio, free):")
    print("      1. https://aistudio.google.com/app/apikey  → Create API key")
    print("      2. Tools › Secrets  → key: GOOGLE_API_KEY, value: <your key>")
    print()
    print("    Option B — Groq + Gemma 2 (free, no credit card):")
    print("      1. https://console.groq.com  → sign up → API Keys → Create")
    print("      2. Tools › Secrets  → key: GROQ_API_KEY, value: <your key>")
    print()
    print("    Then press Run again.")
    sys.exit(1)

# ── Path A: Gemini ────────────────────────────────────────────────────────────
if GOOGLE_API_KEY:
    print("🔑  Google API key found — trying Gemini …\n")
    import google.generativeai as genai

    genai.configure(api_key=GOOGLE_API_KEY)

    PREFERRED = [
        "gemini-2.0-flash", "gemini-2.0-flash-lite",
        "gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-1.5-flash-001",
        "gemini-1.5-pro",   "gemini-1.5-pro-latest",
        "gemini-1.0-pro",   "gemini-pro",
    ]

    try:
        available = [
            m.name for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
    except Exception as e:
        print(f"⚠️   Could not reach Gemini API: {e}")
        available = []

    if available:
        preferred_full = [f"models/{p}" for p in PREFERRED]
        candidates = [m for m in preferred_full if m in available] + \
                     [m for m in available  if m not in preferred_full]

        gemini_ok    = False
        quota_zero   = False
        model_name   = None
        reply        = None

        for candidate in candidates:
            try:
                m        = genai.GenerativeModel(model_name=candidate)
                response = m.generate_content("Reply with exactly: Fieldnote Gemini OK")
                reply      = response.text.strip()
                model_name = candidate
                gemini_ok  = True
                break
            except Exception as e:
                err = str(e)
                if "429" in err and "limit: 0" in err:
                    quota_zero = True
                    break
                if "404" in err or "400" in err:
                    continue
                # Unexpected — surface it
                print(f"⚠️   {candidate}: {e}")

        if gemini_ok:
            print("─" * 55)
            print("✅  SUCCESS — Gemini is connected and working.")
            print(f"    Model  : {model_name}")
            print(f"    Reply  : {reply}")
            print("─" * 55)
            sys.exit(0)

        if quota_zero:
            print("⚠️   Gemini key has zero quota (Cloud Console key).")
            if not GROQ_API_KEY:
                print()
                print("    To fix without billing, get a free Groq key:")
                print("      1. https://console.groq.com  → sign up → API Keys → Create")
                print("      2. Tools › Secrets  → key: GROQ_API_KEY, value: <key>")
                print("      3. Press Run again")
                sys.exit(1)
            print("    → Falling back to Groq + Gemma 2 …\n")

# ── Path B: Groq + Gemma 2 (Google open-source model) ────────────────────────
if GROQ_API_KEY:
    print("🔑  Groq API key found — using Gemma 2 (Google open-source) …\n")
    from groq import Groq

    GROQ_MODELS = [
        "llama-3.3-70b-versatile",  # best free Groq model
        "llama-3.1-8b-instant",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
    ]

    client     = Groq(api_key=GROQ_API_KEY)
    model_name = None
    reply      = None

    for model_id in GROQ_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user",
                           "content": "Reply with exactly: Fieldnote Gemini OK"}],
                max_tokens=32,
            )
            reply      = resp.choices[0].message.content.strip()
            model_name = model_id
            break
        except Exception as e:
            print(f"    ↳ {model_id} — skipped ({e})")

    print()
    print("─" * 55)
    if model_name:
        print("✅  SUCCESS — Groq + Gemma 2 connected and working.")
        print(f"    Provider : Groq  (free tier)")
        print(f"    Model    : {model_name}  (Google open-source)")
        print(f"    Reply    : {reply}")
        print()
        print("    💡 To upgrade to native Gemini later:")
        print("       aistudio.google.com/app/apikey → add as GOOGLE_API_KEY secret")
    else:
        print("❌  All Groq models failed. Check your GROQ_API_KEY is valid.")
    print("─" * 55)
