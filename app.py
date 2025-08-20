import json
import re
import requests
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Constants
CHUNK_SIZE = 60000

# Cache rules to avoid fetching on every request
RULES_URL = "https://raw.githubusercontent.com/galviaoy/finglish-fixer-data/refs/heads/main/finglish_fixer_rules.json"
RULES = None

def get_rules():
    global RULES
    if RULES is None:
        try:
            response = requests.get(RULES_URL)
            response.raise_for_status()
            RULES = response.json()
            print("✅ Rules loaded from GitHub.")
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching rules: {e}")
            RULES = []
    return RULES

def get_rule_by_id(rule_id):
    rules = get_rules()
    for rule in rules:
        if rule.get('id') == rule_id:
            return rule
    return None

def process_text(text_chunk, global_chunk_offset, offset_in_chunk, limit_in_chunk):
    matches = []
    rules = get_rules()

    if not rules:
        return {'matches': [], 'hasMore': False, 'chunkHasMore': False}

    for rule in rules:
        regex = rule.get('regex')
        if not regex:
            continue
        
        # Use re.finditer to find all non-overlapping matches
        for match in re.finditer(regex, text_chunk):
            matches.append({
                "id": rule['id'],
                "text": match.group(),
                "issue": rule['suggestion'],
                "replacement": rule.get('replacement', ''),
                # ✅ CRITICAL FIX: Add global chunk offset to get the correct position
                "startOffset": match.start() + global_chunk_offset,
                "endOffset": match.end() + global_chunk_offset,
                "paragraphIndex": -1, # To be determined on the client side
                "startOffsetInParagraph": -1, # To be determined on the client side
                "endOffsetInParagraph": -1 # To be determined on the client side
            })

    # Sort matches by their starting offset
    matches.sort(key=lambda x: x['startOffset'])
    
    # Simple pagination logic
    start_index = offset_in_chunk
    end_index = start_index + limit_in_chunk
    
    # Check if there are more matches in this chunk
    chunk_has_more = len(matches) > end_index
    
    return {
        "matches": matches[start_index:end_index],
        "hasMore": False, # This is now handled by the frontend
        "chunkHasMore": chunk_has_more
    }

@app.route('/process', methods=['POST'])
def process_document():
    try:
        data = request.get_json(force=True)
        text_chunk = data.get('text', '')

        # 🎯 Read chunk and offset from URL parameters
        offset_in_chunk = int(request.args.get('offset', 0))
        limit_in_chunk = int(request.args.get('limit', 10))
        chunk_index = int(request.args.get('chunkIndex', 0))

        # 💡 Calculate the global offset for the current chunk
        global_chunk_offset = chunk_index * CHUNK_SIZE

        result = process_text(text_chunk, global_chunk_offset, offset_in_chunk, limit_in_chunk)

        return jsonify(result)
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
