# Debug logging for isolated regex test
from flask import Flask, request, jsonify
import re
import sys

app = Flask(__name__)

@app.route("/process", methods=["POST"])
def process_text():
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text = data["text"]
    print(f"📥 TEXT: {text}", file=sys.stderr)

    results = []
    pattern = r"\bwith a low threshold\b"

    try:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        print(f"🔍 FOUND {len(matches)} matches", file=sys.stderr)
        for match in matches:
            print(f"✅ MATCH: {match.group()} at {match.start()}–{match.end()}", file=sys.stderr)
            results.append({
                "text": match.group(),
                "start": match.start(),
                "end": match.end(),
                "issue": "matched hardcoded test rule"
            })
    except Exception as e:
        print(f"❌ Regex error: {e}", file=sys.stderr)

    return jsonify({"matches": results})
