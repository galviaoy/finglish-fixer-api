from flask import Flask, request, jsonify
import re
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route("/")
def hello():
    return "API is alive!"

@app.route("/process", methods=["POST"])
def process_text():
    data = request.get_json()
    text = data.get("text", "")
    logger.info(f"📥 TEXT: {text}")

    results = []
    pattern = r"\bwith a low threshold\b"

    try:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        logger.info(f"🔍 FOUND {len(matches)} matches")
        for match in matches:
            logger.info(f"✅ MATCH: {match.group()} at {match.start()}–{match.end()}")
            results.append({
                "text": match.group(),
                "start": match.start(),
                "end": match.end(),
                "issue": "matched hardcoded test rule"
            })
    except Exception as e:
        logger.error(f"❌ Regex error: {e}")

    return jsonify({"matches": results})
