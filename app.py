# Debug logging added 2025-07-10
from flask import Flask, request, jsonify
import spacy
import requests
import re
import sys

app = Flask(__name__)
nlp = spacy.load("en_core_web_sm")

@app.route("/process", methods=["POST"])
def process_text():
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text = data["text"]
    results = []

    # Test hardcoded regex
    pattern = r"\bwith a low threshold\b"
    matches = re.finditer(pattern, text, re.IGNORECASE)
    for match in matches:
        results.append({
            "text": match.group(),
            "start": match.start(),
            "end": match.end(),
            "issue": "matched hardcoded test rule"
        })

    return jsonify({"matches": results})
