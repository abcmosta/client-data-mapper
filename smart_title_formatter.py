"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           ALEX – SMART TITLE FORMATTER  v3.0                               ║
║           Featuring: Master Brand Dictionary Scanner & Promo Preserver       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  TITLE FORMULA:                                                              ║
║    [Brand] [Product Name] [Variant/Color/Flavor], [Qty x ]Value Unit         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import re
import unicodedata
from typing import Optional, Tuple, List, Dict

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS & LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────

_LOWERCASE_WORDS = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "so", "yet",
    "at", "by", "in", "of", "on", "to", "up", "as", "de", "du", "van", "von",
    "with", "from", "into", "onto", "over", "after", "before", "between", "among",
    "through", "during", "without", "about",
}

_CANONICAL_TOKENS = {
    "spf": "SPF", "spf50+": "SPF50+", "spf50": "SPF50", "pa+++": "PA+++",
    "uva": "UVA", "uvb": "UVB", "aha": "AHA", "bha": "BHA", "pha": "PHA",
    "edp": "EDP", "edt": "EDT", "edc": "EDC", "usb": "USB", "usb-c": "USB-C",
    "hdmi": "HDMI", "4k": "4K", "8k": "8K", "led": "LED", "lcd": "LCD",
    "wifi": "WiFi", "wi-fi": "Wi-Fi", "gps": "GPS", "mah": "mAh",
    "bpa": "BPA", "fda": "FDA", "cbd": "CBD", "mcg": "mcg", "mg": "mg",
    "mk-7": "MK-7", "mk-4": "MK-4", "ph": "pH", "rgb": "RGB", "vr": "VR",
    "xs": "XS", "xl": "XL", "xxl": "XXL", "xxs": "XXS",
}

_UNIT_NORMALISE = {
    "g": "g", "gr": "g", "gm": "g", "grams": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg",
    "mg": "mg", "lb": "lb", "oz": "oz",
    "ml": "ml", "l": "l", "cl": "cl",
    "floz": "fl oz", "fl oz": "fl oz",
    "cm": "cm", "mm": "mm", "m": "m", "inches": "inches", '"': "inches",
    "piece": "Piece", "pieces": "Pieces", "pc": "Piece", "pcs": "Pieces",
    "pack": "Pack", "packs": "Packs", "packet": "Packet",
    "bag": "Bags", "bags": "Bags", "box": "Box", "boxes": "Boxes",
    "roll": "Rolls", "sheet": "Sheets", "wipe": "Wipes",
    "tablet": "Tablets", "capsule": "Capsules", "sachet": "Sachets",
    "set": "Set", "pair": "Pair", "mah": "mAh",
}

_COMPACT_UNITS = {"g", "kg", "mg", "ml", "l", "cl", "lb", "oz", "fl oz", "cm", "mm", "m", "mah"}
_SPACED_UNITS = {"Piece", "Pieces", "Pack", "Packs", "Packet", "Bags", "Box", "Boxes", "Rolls", "Sheets", "Wipes", "Tablets", "Capsules", "Sachets", "Set", "Pair", "inches"}

_ALL_UNIT_PATTERNS = sorted(_UNIT_NORMALISE.keys(), key=len, reverse=True)
_SIZE_RE = re.compile(
    r"""(?ix)
    (?P<multipack>(?:\d+(?:\.\d+)?\s*[x×*]\s*)+)?
    (?P<value>\d+(?:\.\d+)?)
    \s*
    (?P<unit>""" + "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS) + r'|")' +
    r"""(?:\s*(?P<unit2>""" + "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS) + r"""))?""",
    re.VERBOSE | re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _clean_raw(text: str) -> str:
    if not isinstance(text, str): return ""
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[ \t]+", " ", text).strip()

def _title_case_word(word: str, is_first: bool = False) -> str:
    lower = word.lower()
    if lower in _CANONICAL_TOKENS: return _CANONICAL_TOKENS[lower]
    if lower in _LOWERCASE_WORDS and not is_first: return lower
    stripped = re.sub(r"[^a-zA-Z]", "", word)
    if stripped and (stripped != stripped.lower()) and (stripped != stripped.upper()):
        return word
    return re.sub(r"[a-z]", lambda m: m.group(0).upper(), word, count=1)

def _smart_title_case(text: str) -> str:
    if not text: return text
    tokens = re.split(r"(\s+)", text)
    result_tokens = []
    word_index = 0

    for token in tokens:
        if re.fullmatch(r"\s+", token):
            result_tokens.append(token)
            continue
        is_first = (word_index == 0)
        word_index += 1
        
        lower_token = token.lower()
        if lower_token in _CANONICAL_TOKENS:
            result_tokens.append(_CANONICAL_TOKENS[lower_token])
            continue

        inline_meas = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]{1,5})", lower_token)
        if inline_meas and inline_meas.group(2) in _COMPACT_UNITS:
            result_tokens.append(f"{inline_meas.group(1)}{inline_meas.group(2)}")
            continue

        parts = re.split(r"([-/])", token)
        if len(parts) > 1:
            new_parts = []
            sub_first = is_first
            for part in parts:
                if re.fullmatch(r"[-/]", part):
                    new_parts.append(part)
                else:
                    lo_part = part.lower()
                    if lo_part in _CANONICAL_TOKENS: new_parts.append(_CANONICAL_TOKENS[lo_part])
                    else: new_parts.append(_title_case_word(part, is_first=sub_first))
                    sub_first = False
            result_tokens.append("".join(new_parts))
        else:
            result_tokens.append(_title_case_word(token, is_first=is_first))

    return "".join(result_tokens)

def _extract_size_from_end(text: str) -> Tuple[str, str]:
    text = text.strip()
    if "," in text:
        last_comma = text.rfind(",")
        body = text[:last_comma].strip()
        tail = text[last_comma + 1:].strip()
        if _SIZE_RE.search(tail) or tail.lower() in _UNIT_NORMALISE:
            return body, tail
        return body, tail

    # Match size or just floating unit at the end
    end_size_re = re.compile(
        r"(?ix)(?P<space>\s+)(?P<full>(?:(?:(?:\d+(?:\.\d+)?\s*[x×*]\s*)+)?\d+(?:\.\d+)?\s*(?:" + 
        "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS) + r"|\"))|(?:" + 
        "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS) + r"))$"
    )
    m = end_size_re.search(text)
    if m:
        return text[:m.start()].strip(), m.group("full").strip()
    
    return text, ""

# ─────────────────────────────────────────────────────────────────────────────
# MAIN FORMATTER
# ─────────────────────────────────────────────────────────────────────────────
def format_title(
    raw_title: str,
    brands_list: List[Dict[str, str]] = None
) -> dict:
    issues = []
    
    if not raw_title or not isinstance(raw_title, str):
        return {"formatted_title": "", "extracted_size": "", "brand_id": "", "issues": ["Empty title"], "confidence": "low"}

    text = _clean_raw(raw_title)

    # 1. Master Brand Dictionary Scanner
    detected_brand_id = ""
    detected_brand_en = ""
    lower_title = text.lower()
    
    if brands_list:
        for b in brands_list:
            b_en_lower = str(b.get('brand::en', '')).lower().strip()
            if not b_en_lower: continue
            # Exact match using negative lookbehinds/lookaheads (handles M&S, 1&1, etc.)
            pattern = r'(?<![a-zA-Z0-9])' + re.escape(b_en_lower) + r'(?![a-zA-Z0-9])'
            if re.search(pattern, lower_title):
                detected_brand_id = b.get('brand_id', '')
                detected_brand_en = b.get('brand::en', '')
                break

    if not detected_brand_id:
        issues.append("Unbranded - Audit Required")

    # 2. Size Extraction
    body, raw_size = _extract_size_from_end(text)
    extracted_size = raw_size.strip()
    
    # Clean floating units without numbers (e.g., "kg" -> "1 kg")
    if extracted_size.lower() in _UNIT_NORMALISE:
        canon_unit = _UNIT_NORMALISE[extracted_size.lower()]
        extracted_size = f"1{canon_unit}" if canon_unit in _COMPACT_UNITS else f"1 {canon_unit}"
    else:
        m = _SIZE_RE.fullmatch(extracted_size)
        if m:
            mp = (m.group("multipack") or "").replace(" ", "").replace("*", "x")
            val = m.group("value")
            u = _UNIT_NORMALISE.get((m.group("unit") or "").lower(), m.group("unit"))
            extracted_size = f"{mp}{val}{u}" if u in _COMPACT_UNITS else f"{mp}{val} {u}"

    # 3. Smart Title Casing
    body_cased = _smart_title_case(body)

    final_title = f"{body_cased}, {extracted_size}" if extracted_size else body_cased
    final_title = re.sub(r",\s*,", ",", final_title).strip(" ,")

    # 4. Confidence Score
    confidence = "high"
    if "Unbranded - Audit Required" in issues:
        confidence = "medium"

    return {
        "formatted_title": final_title,
        "extracted_size": extracted_size,
        "brand_id": detected_brand_id,
        "issues": issues,
        "confidence": confidence,
    }