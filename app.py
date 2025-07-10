from flask import Flask, request, jsonify
import spacy
import requests
import re

app = Flask(__name__)
nlp = spacy.load("en_core_web_sm")

def load_rules():
    url = "https://raw.githubusercontent.com/galviaoy/finglish-fixer-data/main/finglish_fixer_rules.json"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

@app.route("/process", methods=["POST"])
def process_text():
    data = request.get_json()
    text = data.get("text", "")
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

    # Regex-based rule detection
    rules = load_rules()
    for rule in rules:
        pattern = rule.get("Regex Pattern")
        description = rule.get("Sidebar Suggestion Text")
        try:
            for match in re.finditer(pattern, text):
                results.append({
                    "text": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "issue": description or "regex rule"
                })
        except re.error:
            continue  # skip invalid patterns silently

    return jsonify({"matches": results})
