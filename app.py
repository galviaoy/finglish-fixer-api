from flask import Flask, request, jsonify
import spacy
import requests
import re
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
nlp = spacy.load("en_core_web_sm")

# Load rules from GitHub
def load_rules():
    url = "https://raw.githubusercontent.com/galviaoy/finglish-fixer-data/main/finglish_fixer_rules.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        rules = response.json()
        logging.info(f"✅ Loaded {len(rules)} rules from GitHub")
        return rules
    except Exception as e:
        logging.error(f"❌ Failed to load rules: {e}")
        return []

@app.route("/process", methods=["POST"])
def process_text():
    data = request.get_json()
    text = data.get("text", "")

    # Validate input
    if not text:
        return jsonify({"error": "Missing 'text' in request body"}), 400

    # Read pagination params from query string
    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        offset, limit = 0, 20

    logging.info(f"📥 TEXT: {text[:100]}... (length: {len(text)})")
    paragraphs = text.split("\n")
    rules = load_rules()
    logging.info(f"📦 Loaded {len(rules)} rules")

    results = []
    for p_idx, para in enumerate(paragraphs):
        for rule in rules:
            pattern = rule.get("Regex Pattern") or rule.get("pattern")
            description = rule.get("Sidebar Suggestion Text")
            if not pattern:
                continue

            try:
                for match in re.finditer(pattern, para, re.IGNORECASE):
                    results.append({
                        "paragraphIndex": p_idx,
                        "start": match.start(),
                        "end": match.end(),
                        "text": match.group(),
                        "issue": description or "regex rule"
                    })
            except re.error as e:
                logging.warning(f"⚠️ Regex error in pattern: {pattern} — {e}")

    paged_matches = results[offset:offset+limit]
    logging.info(f"✅ Returning {len(paged_matches)} matches from offset {offset}")

    return jsonify({
        "matches": paged_matches,
        "total": len(results),
        "offset": offset,
        "limit": limit
    })
