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

@app.route("/", methods=["GET"])
def health_check():
    try:
        test_doc = nlp("This is a test.")
        return "spaCy model loaded and working", 200
    except Exception as e:
        import traceback
        return f"❌ spaCy crash:\n{traceback.format_exc()}", 500

@app.route("/process", methods=["POST"])
def process_text():
    try:
        data = request.get_json()
        text = data.get("text", "")
        logging.info("✔️ /process reached and received text input")

        if not text:
            return jsonify({"error": "Missing 'text' in request body"}), 400

        logging.info("📥 Text received, length: %d", len(text))

        if len(text) > 100000:
            logging.warning("❌ Document too long (%d characters), skipping processing", len(text))
            return jsonify({"error": "Document too long for processing"}), 400

        doc = nlp(text)
        logging.info("🧠 spaCy NLP completed")


        sentences = list(doc.sents)
        logging.info("✂️ Sentences extracted: %d", len(sentences))


        try:
            offset = int(request.args.get("offset", 0))
            limit = int(request.args.get("limit", 20))
        except ValueError:
            offset, limit = 0, 20

        if not hasattr(app, "cached_rules"):
            app.cached_rules = load_rules()
            logging.info(f"✅ Rules cached: {len(app.cached_rules)} rules")


        rules = app.cached_rules
        logging.info(f"📡 Rule loading returned: {type(rules)} with length {len(rules)}")
        logging.info(f"📜 Total rules loaded: {len(rules)}")
        if rules:
            logging.info(f"🧪 Sample rule pattern: {rules[0].get('Regex Pattern') or rules[0].get('pattern')}")
        else:
            logging.warning("⚠️ No rules loaded!")


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
                            absolute_start = match.start() + sum(len(p) + 1 for p in paragraphs[:p_idx])
                            absolute_end = match.end() + sum(len(p) + 1 for p in paragraphs[:p_idx])

                            sentence_start = 0
                            sentence_end = len(text)
                            for sent in sentences:
                                if sent.start_char <= absolute_start < sent.end_char:
                                    sentence_start = sent.start_char
                                    sentence_end = sent.end_char
                                    break

                            kwargs = {
                                "paragraphIndex": p_idx,
                                "start": absolute_start,
                                "end": absolute_end,
                                "sentenceStart": sentence_start,
                                "sentenceEnd": sentence_end,
                                "text": match.group(),
                                "issue": suggestion,
                                "sidebar": rule.get("sidebar", "")
                            }

                            if replacement:
                                kwargs["replacement"] = replacement

                            matches.append(kwargs)

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

    except Exception as e:
        import traceback
        trace = traceback.format_exc()
        logging.error(f"❌ Exception: {e}\n{trace}")
        return jsonify({"error": str(e), "trace": trace}), 500

if __name__ == "__main__":
    print("⚙️ Starting Flask app...")
    app.run(host="0.0.0.0", port=5050, debug=True)


