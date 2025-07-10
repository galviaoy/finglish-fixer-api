from flask import Flask, request, jsonify
import spacy

app = Flask(__name__)
nlp = spacy.load("en_core_web_sm")

@app.route("/process", methods=["POST"])
def process_text():
    data = request.get_json()
    text = data.get("text", "")
    doc = nlp(text)

    results = []
    for sent in doc.sents:
        if any(tok.dep_ == "nsubjpass" for tok in sent):
            results.append({
                "text": sent.text,
                "start": sent.start_char,
                "end": sent.end_char,
                "issue": "passive voice"
            })

    return jsonify({"matches": results})
