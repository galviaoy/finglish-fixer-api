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
        for token in sent:
            if token.dep_ == "ROOT" and token.pos_ == "VERB" and token.lemma_ != "be":
                main_verb = token
                break
        if not main_verb:
            continue
        for token in sent:
            if token.text.lower() == "also" and token.i > main_verb.i:
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
                print(f"📌 Found subject: '{token.text}' at sentence {i}")
                if i > 0:
                    prev_sent = sents[i - 1]
                    print(f"🔍 Sentence before 'They': {prev_sent.text}")
                    for tok in prev_sent:
                        if tok.lemma_.lower() in company_words and tok.pos_ == "NOUN":
                            if tok.tag_ in {"NN", "NNP"}:  # singular common or proper noun
                                print(f"✅ Match: '{tok.text}' is singular company noun")
                                issues.append({
                                    "text": sent.text,
                                    "start": token.idx,
                                    "end": token.idx + len(token),
                                    "issue": "We say 'it' rather than 'they' to refer to a company in English.",
                                    "suggestion": sent.text.replace(token.text, "It", 1),
                                    "rule_id": 35
                                })
                                break
                            else:
                                print(f"❌ '{tok.text}' is not singular: tag = {tok.tag_}")
                        else:
                            print(f"❌ '{tok.text}' is not a tracked company noun")

    return issues

    issues = []
    company_words = {"company", "business", "organisation", "organization", "agency", "firm"}
    sents = list(doc.sents)
    for i, sent in enumerate(sents):
        for token in sent:
            if token.text.lower() == "they" and token.dep_ == "nsubj":
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

def debug_sentences(text):
    doc = nlp(text)
    print("\n🔍 Sentences as seen by spaCy:")
    for i, sent in enumerate(doc.sents):
        print(f"{i}: {sent.text}")

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
    logging.info("🚀 process_text() endpoint hit")
    try:
        data = request.get_json()
        text = data.get("text", "")
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 20))
        chunk_index = int(request.args.get("chunkIndex", 0))
        CHUNK_SIZE = 30000
        start_char = chunk_index * CHUNK_SIZE
        end_char = start_char + CHUNK_SIZE
        text_chunk = text[start_char:end_char]

        if not text_chunk:
            return jsonify({"matches": [], "total": 0, "offset": offset, "limit": limit, "hasMore": False, "chunkHasMore": False})

        debug_sentences(text_chunk)
        doc = nlp(text_chunk)
        logging.info("🧠 spaCy NLP completed")

        all_issues = detect_misplaced_also_spacy(doc) + detect_they_as_company_spacy(doc)
        sentences = list(doc.sents)
        app.cached_rules = load_rules()
        rules = app.cached_rules[:50]

        paragraphs = text.split("\n")
        paragraph_offsets = []
        char_count = 0
        for para in paragraphs:
            paragraph_offsets.append(char_count)
            char_count += len(para) + 1

        matches = []
        stop_processing = False

        for p_idx, para in enumerate(paragraphs):
            if stop_processing:
                break
            for rule in rules:
                if stop_processing:
                    break
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
                        if len(matches) >= offset + limit:
                            stop_processing = True
                            break
                except re.error as e:
                    logging.warning(f"⚠️ Regex error in pattern: {pattern} — {e}")

        for issue in all_issues:
            if len(matches) >= offset + limit:
                break
            p_idx = 0
            for i, para_offset in enumerate(paragraph_offsets):
                if issue["start"] >= para_offset:
                    p_idx = i
                else:
                    break

            matches.append({
                "paragraphIndex": p_idx,
                "start": start_char + issue["start"],
                "end": start_char + issue["end"],
                "startOffsetInParagraph": issue["start"] - paragraph_offsets[p_idx],
                "endOffsetInParagraph": issue["end"] - paragraph_offsets[p_idx],
                "sentenceStart": issue["start"],
                "sentenceEnd": issue["end"],
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
            "hasMore": offset + limit < len(matches),
            "chunkHasMore": end_char < len(text)
        })

    except Exception as e:
        import traceback
        logging.error(f"❌ Exception: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

if __name__ == "__main__":
    print("⚙️ Starting Flask app...")
    app.run(host="0.0.0.0", port=5050, debug=True)
