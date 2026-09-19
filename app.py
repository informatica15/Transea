"""
TranSea — Phase 2: Python backend
----------------------------------
Responsibility of this phase: take text + source/target language codes
from the frontend, run it through a translation engine, and hand the
translated text back. No database yet — that's Phase 5.

Flow:
  browser mic -> Web Speech API (STT, in the browser)
              -> fetch POST /translate  { text, source, target }
              -> this file calls the translation engine
              -> returns { translated_text }
              -> fetch POST /speak  { text, lang }
              -> this file generates real audio with gTTS
              -> browser plays the returned mp3

Note on /speak: the browser's built-in speechSynthesis only works for
languages that have a voice installed on the user's OS, which on most
Windows machines does not include Tamil, Hindi, etc. — it silently
skips non-Latin script but still reads plain digits aloud in English.
Generating audio server-side with gTTS sidesteps that entirely.
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from deep_translator import GoogleTranslator, MyMemoryTranslator
from gtts import gTTS
import io
import os

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates"))
app = Flask(__name__, template_folder=template_dir)
CORS(app)  # allows the frontend to call this API from a different origin during development

# Map the BCP-47 codes the frontend uses (e.g. "en-US") to the short
# codes the translation library expects (e.g. "en").
def short_code(bcp47_code: str) -> str:
    return bcp47_code.split("-")[0].lower()


@app.route("/")
def home():
    """Serves the TranSea voice UI."""
    return render_template("index.html")


@app.route("/translate", methods=["POST"])
def translate():
    """
    Expects JSON: { "text": "...", "source": "en-US", "target": "ta-IN" }
    Returns JSON: { "translated_text": "..." }  on success
                  { "error": "..." }             on failure
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    raw_source = data.get("source", "en-US")
    raw_target = data.get("target", "ta-IN")
    source = short_code(raw_source)
    target = short_code(raw_target)

    if not text:
        return jsonify({"error": "No text provided"}), 400

    if source == target:
        # Nothing to translate — hand it straight back.
        return jsonify({"translated_text": text})

    try:
        try:
            translated = GoogleTranslator(source=source, target=target).translate(text)
        except Exception:
            # Fallback to MyMemoryTranslator when Google rate-limits (HTTP 429)
            translated = MyMemoryTranslator(source=raw_source, target=raw_target).translate(text)
        return jsonify({"translated_text": translated})
    except Exception as exc:
        # Common causes: unsupported language pair, no internet access,
        # or the translation engine being temporarily unreachable.
        return jsonify({"error": f"Translation failed: {exc}"}), 502


@app.route("/speak", methods=["POST"])
def speak():
    """
    Expects JSON: { "text": "...", "lang": "ta-IN" }
    Returns: an audio/mpeg (mp3) stream on success, JSON error on failure.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = short_code(data.get("lang", "en"))

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        tts = gTTS(text=text, lang=lang)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return send_file(audio_buffer, mimetype="audio/mpeg")
    except Exception as exc:
        # Common causes: unsupported language code, or no internet access
        # (gTTS calls out to Google Translate's TTS endpoint each time).
        return jsonify({"error": f"Speech generation failed: {exc}"}), 502


if __name__ == "__main__":
    # debug=True auto-reloads on code changes — turn off before deploying (Phase 9)
    app.run(debug=True, port=5000)
