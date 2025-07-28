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

    if not text:
        return jsonify({"error": "Missing 'text' in request body"}), 400

    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        offset, limit = 0, 20

    if not hasattr(app, "cached_rules"):
        app.cached_rules = load_rules()
        logging.info(f"✅ Rules cached: {len(app.cached_rules)} rules")

    rules = app.cached_rules
    paragraphs = text.split("\n")
    matches = []

    for p_idx, para in enumerate(paragraphs):
        for rule in rules:
            pattern = rule.get("Regex Pattern") or rule.get("pattern")
            suggestion = rule.get("sidebar") or rule.get("Sidebar Suggestion Text") or rule.get("suggestion") or "regex rule"
            replacement = rule.get("Replacement Pattern") or rule.get("replacement") or ""

            if not pattern:
                continue

            try:
                for match in re.finditer(pattern, para, re.IGNORECASE):
                    matches.append({
                        "paragraphIndex": p_idx,
                        "start": match.start() + sum(len(p) + 1 for p in paragraphs[:p_idx]),
                        "end": match.end() + sum(len(p) + 1 for p in paragraphs[:p_idx]),
                        "text": match.group(),
                        "issue": suggestion,
                        "replacement": replacement,
                    })
            except re.error as e:
                logging.warning(f"⚠️ Regex error in pattern: {pattern} — {e}")

    paged_matches = matches[offset:offset + limit]
    logging.info(f"✅ Returning {len(paged_matches)} of {len(matches)} matches (offset {offset})")

    return jsonify({
        "matches": paged_matches,
        "total": len(matches),
        "offset": offset,
        "limit": limit,
        "hasMore": offset + limit < len(matches)
    })
