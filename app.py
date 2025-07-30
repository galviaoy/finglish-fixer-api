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
# === Rule 17: Misplaced "also" (spaCy-based) ===
def detect_misplaced_also_spacy(doc):
    issues = []

    for sent in doc.sents:
        main_verb = None

        # Find the ROOT verb that is not a form of 'be'
        for token in sent:
            if token.dep_ == "ROOT" and token.pos_ == "VERB" and token.lemma_ != "be":
                main_verb = token
                break

        if not main_verb:
            continue

        for token in sent:
            if token.text.lower() == "also" and token.i > main_verb.i:
                # Create a suggested sentence: move "also" before the main verb
                tokens = [t for t in sent if t != token]
                insert_index = [i for i, t in enumerate(sent) if t == main_verb][0]
                tokens.insert(insert_index, token)

                suggestion = "".join(t.text_with_ws for t in tokens).strip()

                issues.append({
                    "text": sent.text,
                    "start": token.idx,
                    "end": token.idx + len(token),
                    "issue": "‘also’ comes after the main verb. Move ‘also’ before the verb unless it's a form of ‘be’.",
                    "suggestion": suggestion,
                    "rule_id": 17
                })

    return issues

def detect_they_as_company_spacy(doc):
    issues = []

    company_words = {"company", "business", "organisation", "organization", "agency", "firm"}

    sents = list(doc.sents)
    for i, sent in enumerate(sents):
        for token in sent:
            if token.text.lower() == "they" and token.dep_ == "nsubj":
                # Look back to previous sentence if there is one
                if i > 0:
                    prev_sent = sents[i - 1]
                    if any(tok.lemma_.lower() in company_words for tok in prev_sent):
                        issues.append({
                            "text": sent.text,
                            "start": token.idx,
                            "end": token.idx + len(token),
                            "issue": "We say 'it' rather than 'they' to refer to a company in English.",
                            "suggestion": sent.text.replace(token.text, "It", 1),
                            "rule_id": 35
                        })
                        break

    return issues

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

        all_issues = []
        all_issues.extend(detect_misplaced_also_spacy(doc))
        all_issues.extend(detect_they_as_company_spacy(doc))

        sentences = list(doc.sents)
        logging.info("✂️ Sentences extracted: %d", len(sentences))


        try:
            offset = int(request.args.get("offset", 0))
            limit = int(request.args.get("limit", 20))
        except ValueError:
            offset, limit = 0, 20

        # Force fresh load of rules from GitHub every time (for now)
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
        paragraph_offsets = []
        char_count = 0
        for para in paragraphs:
            paragraph_offsets.append(char_count)
            char_count += len(para) + 1  # +1 for newline

        matches = []


        for p_idx, para in enumerate(paragraphs):
            for rule in rules:
                if rule.get("disabled", False):
                    continue
                pattern = rule.get("Regex Pattern") or rule.get("pattern")
                suggestion = rule.get("sidebar") or rule.get("Sidebar Suggestion Text") or rule.get("suggestion") or "regex rule"
                replacement = rule.get("Replacement Pattern") or rule.get("replacement") or ""

                if not pattern:
                    continue

                try:
                        for match in re.finditer(pattern, para, re.IGNORECASE):
                            relative_start = match.start()
                            relative_end = match.end()
                            para_offset = paragraph_offsets[p_idx]
                            absolute_start = para_offset + relative_start
                            absolute_end = para_offset + relative_end



                            sentence_start = 0
                            sentence_end = len(text)
                            for sent in sentences:
                                if sent.start_char <= absolute_start < sent.end_char:
                                    sentence_start = sent.start_char
                                    sentence_end = sent.end_char
                                    break

                            match_data = {
                                "paragraphIndex": p_idx,
                                "start": absolute_start,
                                "end": absolute_end,
                                "startOffsetInParagraph": relative_start,
                                "endOffsetInParagraph": relative_end,
                                "sentenceStart": sentence_start,
                                "sentenceEnd": sentence_end,
                                "text": match.group(),
                                "issue": suggestion,
                                "sidebar": rule.get("sidebar", "")
                            }

                            if replacement:
                                match_data["replacement"] = replacement
                                
                            matches.append(match_data)


                except re.error as e:
                    logging.warning(f"⚠️ Regex error in pattern: {pattern} — {e}")
                # Include spaCy-based results (e.g. rule 17) in matches
        for issue in all_issues:
            # Try to determine paragraph index from sentenceStart
            p_idx = 0
            for i, para_offset in enumerate(paragraph_offsets):
                if issue["start"] >= para_offset:
                    p_idx = i
                else:
                    break

            matches.append({
                "paragraphIndex": p_idx,
                "start": issue["start"],
                "end": issue["end"],
                "startOffsetInParagraph": issue["start"] - paragraph_offsets[p_idx],
                "endOffsetInParagraph": issue["end"] - paragraph_offsets[p_idx],
                "sentenceStart": issue["start"],  # assuming start of sentence is start
                "sentenceEnd": issue["end"],      # and end of sentence is end
                "text": issue["text"],
                "issue": issue["issue"],
                "sidebar": issue["issue"],
                "replacement": issue.get("suggestion", "")
            })

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