import os
import re
import json
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# --- Config ---
RULES_URL = os.getenv(
    "RULES_URL",
    "https://raw.githubusercontent.com/galviaoy/finglish-fixer-data/refs/heads/main/finglish_fixer_rules.json"
)

# --- Load rules once at startup ---
def load_rules() -> list:
    try:
        r = requests.get(RULES_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        app.logger.info(f"Loaded rules from URL: {RULES_URL} (count={len(data)})")
        return data
    except Exception as e:
        app.logger.error(f"Failed to load rules from URL: {e}")
        # Optional: fallback to local file
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
if not isinstance(RULES, list):
    app.logger.error(f"RULES is not a list (got {type(RULES).__name__}); forcing empty list")
    RULES = []
app.logger.info(f"RULES_COUNT={len(RULES)} FIRST_ITEMS={[r.get('item') for r in RULES[:3]]}")

# --- Compile regexes (honour inline flags) ---
FLAG_MAP = {'i': re.IGNORECASE, 'm': re.MULTILINE, 's': re.DOTALL}

def extract_inline_flags_and_body(pat: str):
    """Parse leading inline flags like (?im), (?i), (?ms)."""
    flags = 0
    body = pat or ""
    if body.startswith("(?"):
        end = body.find(")")
        if end != -1:
            raw = body[2:end]
            if raw and all(ch in "ims" for ch in raw):
                for ch in raw:
                    flags |= FLAG_MAP[ch]
                body = body[end+1:]
    return flags, body

def compile_rule(rule):
    pat = rule.get("pattern", "") or ""
    inline_flags, stripped = extract_inline_flags_and_body(pat)
    default_flags = re.IGNORECASE | re.MULTILINE  # helpful defaults
    try:
        return re.compile(stripped, default_flags | inline_flags)
    except re.error as e:
        app.logger.error(f"Regex compile failed for item={rule.get('item')} pattern={pat!r}: {e}")
        return None

COMPILED = []
for r in RULES:
    c = compile_rule(r)
    if c:
        COMPILED.append((r, c))
app.logger.info(f"COMPILED_COUNT={len(COMPILED)} (of RULES_COUNT={len(RULES)})")

# --- Health check ---
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "rules_count": len(RULES),
        "compiled_count": len(COMPILED),
        "first_items": [r.get("item") for r, _ in COMPILED[:5]]
    })

# --- Core matcher ---
def run_rules(text: str, offset: int = 0, limit: int = 10):
    """Return (page, has_more). Each match: {start,end,text,issue,replacement}"""
    out = []
    for rule, creg in COMPILED:
        try:
            for m in creg.finditer(text):
                out.append({
                    "start": m.start(),
                    "end":   m.end(),
                    "text":  m.group(0),
                    "issue": rule.get("sidebar") or rule.get("issue") or rule.get("item") or "",
                    "replacement": rule.get("replacement") or rule.get("replacement_pattern") or ""
                })
        except Exception as e:
            app.logger.error(f"finditer error for rule {rule.get('item')}: {e}")
    out.sort(key=lambda x: (x["start"], x["end"]))
    page = out[offset: offset + limit]
    has_more = (offset + limit) < len(out)
    return page, has_more

# --- Process endpoint used by Apps Script ---
@app.post("/process")
def process():
    data = request.get_json(silent=True) or {}
    text = data.get("text") or data.get("content") or ""
    try:
        offset = int(request.args.get("offset", "0"))
        limit  = int(request.args.get("limit", "10"))
    except ValueError:
        offset, limit = 0, 10

    app.logger.info(f"/process keys={list(data.keys())} text_len={len(text)} offset={offset} limit={limit}")

    if not RULES or not COMPILED:
        return jsonify({"matches": [], "hasMore": False, "chunkHasMore": False, "error": "NO_RULES_LOADED"}), 200

    matches, has_more = run_rules(text, offset=offset, limit=limit)
    return jsonify({
        "matches": matches,
        "hasMore": has_more,
        "chunkHasMore": False
    })

# --- Debug scan endpoint (useful for quick checks) ---
@app.post("/debug/scan")
def debug_scan():
    """Body: { "text": "...", "limit": 50 } -> which rules hit."""
    data = request.get_json(silent=True) or {}
    text = data.get("text") or ""
    limit = int(data.get("limit") or 50)
    hits = []
    for rule, creg in COMPILED:
        m = creg.search(text)
        if m:
            hits.append({
                "item": rule.get("item"),
                "first_match": m.group(0),
                "span": [m.start(), m.end()],
            })
            if len(hits) >= limit:
                break
    return jsonify({
        "compiled_count": len(COMPILED),
        "hit_count": len(hits),
        "hits": hits,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
