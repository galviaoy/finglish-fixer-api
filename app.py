from flask import Flask, request, jsonify
import re
import logging
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RULES_URL = "https://raw.githubusercontent.com/galviaoy/finglish-fixer-data/main/finglish_fixer_rules.json"

@app.route("/")
def hello():
    return "API is alive!"

def load_rules():
    try:
        response = requests.get(RULES_URL)
        response.raise_for_status()
        rules = response.json()
        logger.info(f"✅ Loaded {len(rules)} rules from GitHub")
        return rules
    except Exception as e:
        logger.error(f"❌ Failed to load rules: {e}")
        return []

@app.route("/process", methods=["POST"])
def process_text():
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text = data["text"]
    logger.info(f"📥 TEXT: {text}")

    results = []
    rules = load_rules()

    for rule in rules:
        pattern = rule.get("Regex Pattern")
        description = rule.get("Sidebar Suggestion Text")
        if not pattern:
            continue
        try:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                logger.info(f"✅ MATCH: {match.group()} from pattern: {pattern}")
                results.append({
                    "text": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "issue": description or "Finglish pattern"
                })
        except re.error as e:
            logger.warning(f"⚠️ Invalid regex skipped: {pattern} — {e}")
            continue

    logger.info(f"✅ Returning {len(results)} matches")
    return jsonify({"matches": results})
