import json
import re
import requests
from flask import Flask, request, jsonify
import os

app = Flask(__name__)
# app.py (top-level)
import json, os, re, logging
from flask import Flask, request, jsonify

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

RULES_URL = os.getenv("RULES_URL", "https://raw.githubusercontent.com/galviaoy/finglish-fixer-data/refs/heads/main/finglish_fixer_rules.json")

def load_rules():
    # Load from URL or local path; choose whichever you actually use
    try:
        import requests
        r = requests.get(RULES_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        app.logger.info(f"Loaded rules from URL: {RULES_URL} (count={len(data)})")
        return data
    except Exception as e:
        app.logger.error(f"Failed to load rules from URL: {e}")
        # Fallback to local file if present
        local_path = os.getenv("RULES_FILE", "finglish_fixer_rules.json")
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                app.logger.info(f"Loaded rules from file: {local_path} (count={len(data)})")
                return data
        except Exception as e2:
            app.logger.error(f"Failed to load local rules: {e2}")
            return []

RULES = load_rules()
app.logger.info(f"RULES_COUNT={len(RULES)} FIRST_ITEMS={[r.get('item') for r in RULES[:3]]}")

@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "rules_count": len(RULES),
        "first_items": [r.get("item") for r in RULES[:5]],
    })


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

def compile_rule(rule):
    # Expect JS-style patterns like (?i) and \b...\b — Python re supports (?i)
    pat = rule.get("pattern", "")
    flags = 0
    # You may already store case-insensitivity inline as (?i). If not, also allow a field:
    if rule.get("ignore_case") is True:
        flags |= re.IGNORECASE
    try:
        return re.compile(pat, flags)
    except re.error as e:
        app.logger.error(f"Regex compile failed for item={rule.get('item')} pattern={pat!r}: {e}")
        return None

COMPILED = []
for r in RULES:
    c = compile_rule(r)
    if c:
        COMPILED.append((r, c))
app.logger.info(f"COMPILED_COUNT={len(COMPILED)}")

def run_rules(text, offset=0, limit=10):
    """Return list of dicts: {start,end,text,issue,replacement} limited/paged."""
    out = []
    for rule, creg in COMPILED:
        try:
            for m in creg.finditer(text):
                span_text = m.group(0)
                out.append({
                    "start": m.start(),
                    "end":   m.end(),
                    "text":  span_text,
                    "issue": rule.get("sidebar") or rule.get("issue") or rule.get("item") or "",
                    "replacement": rule.get("replacement") or rule.get("replacement_pattern") or ""
                })
        except Exception as e:
            app.logger.error(f"finditer error for rule {rule.get('item')}: {e}")
    # Sort by start; page by [offset:offset+limit]
    out.sort(key=lambda x: (x["start"], x["end"]))
    page = out[offset: offset + limit]
    has_more = (offset + limit) < len(out)
    return page, has_more

@app.post("/process")
def process():
    data = request.get_json(silent=True) or {}
    text = data.get("text") or data.get("content") or ""
    app.logger.info(f"/process keys={list(data.keys())} text_len={len(text)} offset={request.args.get('offset')} limit={request.args.get('limit')}")

    # Hard fail fast if rules not loaded
    if not RULES:
        return jsonify({"matches": [], "hasMore": False, "chunkHasMore": False, "error": "NO_RULES_LOADED"}), 200

    # SMOKE TEST: prove matching works even if rules are off
    if "We at " in text or "We at" in text:
        app.logger.info("Smoke test: 'We at' found, injecting synthetic match.")
        return jsonify({
            "matches": [{
                "start": text.find("We at"),
                "end":   text.find("We at") + len("We at"),
                "text":  "We at",
                "issue": "In English, 'we' usually needs context like 'here at X, we…'.",
                "replacement": "here at X, we"
            }],
            "hasMore": False,
            "chunkHasMore": False
        })

    try:
        offset = int(request.args.get("offset", "0"))
        limit  = int(request.args.get("limit", "10"))
    except ValueError:
        offset, limit = 0, 10

    matches, has_more = run_rules(text, offset=offset, limit=limit)
    return jsonify({
        "matches": matches,
        "hasMore": has_more,
        "chunkHasMore": False  # client infers chunking by doc length
    })

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
