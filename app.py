# Debug logging added 2025-07-10
from flask import Flask, request, jsonify
import spacy
import requests
import re
import sys

app = Flask(__name__)
nlp = spacy.load("en_core_web_sm")

def load_rules():
    url = "https://raw.githubusercontent.com/galviaoy/finglish-fixer-data/main/finglish_fixer_rules.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        print("✅ Rules loaded successfully", file=sys.stderr)
        return response.json()
    except Exception as e:
        print(f"❌ Failed to load rules: {e}", file=sys.stderr)
        return []

@app.route("/process", methods=["POST"])
def process_text():
    print("📥 /process endpoint hit", file=sys.stderr)
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text = data["text"]
    doc = nlp(text)
    results = []

    # Passive voice detection
    for sent in doc.sents:
        if any(tok.dep_ == "nsubjpass" for tok in sent):
            results.append({
                "text": sent.text,
                "start": sent.start_char,
                "end": sent.end_char,
                "issue": "passive voice"
            })

    # Regex-based detection
    rules = load_rules()
    for rule in rules:
        pattern = rule.get("Regex Pattern")
        description = rule.get("Sidebar Suggestion Text")
        if not pattern:
            continue
        try:
            for match in re.finditer(pattern, text):
                results.append({
                    "text": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "issue": description or "regex rule"
                })
        except re.error as e:
            print(f"⚠️ Regex error in pattern: {pattern} — {e}", file=sys.stderr)
            continue

    print(f"✅ Returning {len(results)} matches", file=sys.stderr)
    return jsonify({"matches": results})
