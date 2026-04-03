"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           ALEX – SMART TITLE FORMATTER  v3.0                               ║
║           Trained on 19,000+ real Talabat catalogue titles                 ║
║           Built by: Mostafa Abdelaziz  |  Upgraded by: Claude              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  TITLE FORMULA:                                                              ║
║    [Brand] [Product Name] [Variant/Flavor/Color], [Qty x]Value Unit         ║
║                                                                              ║
║  NEW in v3.0:                                                                ║
║    • Master brand scanning  – detects brand_id from title using             ║
║      master_brands.csv (longest-match-first, case-insensitive)              ║
║    • Returns brand_id in result dict for direct catalogue use               ║
║    • "1 Piece" / "1 Pack" etc. treated as valid catalogue quantities        ║
║    • Handles contentsValue="1" properly (not skipped like 0)                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import re
import unicodedata
from typing import List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 ─ CONSTANTS & LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────

_LOWERCASE_WORDS = {
    "a", "an", "the",
    "and", "but", "or", "nor", "for", "so", "yet",
    "at", "by", "in", "of", "on", "to", "up",
    "as", "de", "du", "van", "von",
    "with", "from", "into", "onto", "over",
    "after", "before", "between", "among",
    "through", "during", "without", "about",
}

_CANONICAL_TOKENS = {
    # Sunscreen / Skincare
    "spf": "SPF",
    "spf50+": "SPF50+", "spf50": "SPF50",
    "spf45+": "SPF45+", "spf45": "SPF45",
    "spf40+": "SPF40+", "spf40": "SPF40",
    "spf35+": "SPF35+", "spf35": "SPF35",
    "spf30+": "SPF30+", "spf30": "SPF30",
    "spf25": "SPF25", "spf20": "SPF20", "spf15": "SPF15",
    "pa+++": "PA+++", "pa++": "PA++", "pa+": "PA+",
    "uva": "UVA", "uvb": "UVB", "uv": "UV",
    "aha": "AHA", "bha": "BHA", "pha": "PHA",
    "pdrn": "PDRN", "niacinamide": "Niacinamide",
    # Fragrance
    "edp": "EDP", "edt": "EDT", "edc": "EDC",
    # Electronics
    "usb": "USB", "usb-c": "USB-C", "usb-a": "USB-A",
    "hdmi": "HDMI", "4k": "4K", "8k": "8K",
    "led": "LED", "lcd": "LCD", "oled": "OLED",
    "hdr": "HDR", "uhd": "UHD", "fhd": "FHD",
    "wifi": "WiFi", "wi-fi": "Wi-Fi",
    "nfc": "NFC", "gps": "GPS",
    "mah": "mAh",
    # Health / Pharma
    "bpa": "BPA", "fda": "FDA",
    "cbd": "CBD", "thc": "THC",
    "mcg": "mcg", "mg": "mg", "iu": "IU",
    "mk-7": "MK-7", "mk-4": "MK-4", "mk7": "MK-7", "mk4": "MK-4",
    # Food labelling
    "gmo": "GMO",
    # Tech / Size
    "3d": "3D", "360°": "360°",
    # Chemistry
    "ph": "pH",
    # Connectivity / Waterproof
    "ip65": "IP65", "ip67": "IP67", "ip68": "IP68", "ip54": "IP54",
    "3atm": "3ATM", "5atm": "5ATM", "atm": "ATM",
    # Gaming / AV
    "ittf": "ITTF", "rgb": "RGB", "vr": "VR",
    # Clothing sizes
    "xs": "XS", "xl": "XL", "xxl": "XXL", "xxxl": "XXXL", "xxs": "XXS",
}

# Brand IDs whose display is ALL CAPS
_ALLCAPS_BRAND_IDS = {
    "wellage", "rovectin", "skintific", "eqqual_berry", "eqqualberry",
    "banila_co", "kaine", "tirtir", "jumiso", "k_secret",
    "illiyoon", "sungboon", "jbl", "aibo", "trm", "diy",
    "activlab", "ada", "rog", "vt", "agf",
}

# Brand IDs that intentionally START LOWERCASE
_LOWERCASE_BRAND_IDS = {"make_p_rem", "i_m_from", "ma_nyo"}

# ─── UNIT NORMALISATION TABLE ──────────────────────────────────────────────
_UNIT_NORMALISE = {
    # weight – compact
    "g": "g", "gr": "g", "gm": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg",
    "mg": "mg",
    "lb": "lb", "lbs": "lb",
    "oz": "oz",
    # volume – compact
    "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    "milliliters": "ml", "millilitres": "ml",
    "cl": "cl", "dl": "dl",
    "l": "l", "liter": "l", "litre": "l", "liters": "l", "litres": "l",
    "fl oz": "fl oz", "floz": "fl oz", "fl.oz": "fl oz", "fl.oz.": "fl oz",
    # length – compact
    "cm": "cm", "mm": "mm",
    "m": "m", "meter": "m", "metre": "m", "meters": "m", "metres": "m",
    "km": "km",
    "inch": "inches", "in": "inches", "inches": "inches", '"': "inches",
    # count – spaced, Title Case
    # ── SINGULAR & PLURAL both supported ─────────────────────────────────
    "piece": "Piece",   "pieces": "Pieces",
    "pcs": "pcs",       "pc": "pcs",
    "pack": "Pack",     "packs": "Packs",
    "packet": "Packet", "packets": "Packets",
    "bag": "Bags",      "bags": "Bags",
    "box": "Box",       "boxes": "Boxes",
    "roll": "Rolls",    "rolls": "Rolls",
    "sheet": "Sheets",  "sheets": "Sheets",
    "wipe": "Wipes",    "wipes": "Wipes",
    "tablet": "Tablets","tablets": "Tablets",
    "capsule": "Capsules","capsules": "Capsules",
    "sachet": "Sachets","sachets": "Sachets",
    "unit": "Piece",    "units": "Pieces",   # "unit" → Piece for display
    "count": "Pieces",
    "set": "Set",       "sets": "Sets",
    "pair": "Pair",     "pairs": "Pairs",
    "pencils": "Pencils","pencil": "Pencils",
    "puffs": "Puffs",   "puff": "Puffs",
    "cards": "Cards",   "card": "Cards",
    "meters": "Meters",
    "tea bag": "Tea Bags", "tea bags": "Tea Bags",
    "mah": "mAh",
}

_COMPACT_UNITS = {
    "g", "kg", "mg", "ml", "l", "cl", "dl",
    "lb", "oz", "fl oz",
    "cm", "mm", "m", "km",
    "mah",
}

_SPACED_UNITS = {
    "Piece", "Pieces", "pcs",
    "Pack", "Packs", "Packet", "Packets",
    "Bags", "Box", "Boxes",
    "Rolls", "Sheets", "Wipes",
    "Tablets", "Capsules", "Sachets",
    "Set", "Sets", "Pairs", "Pair",
    "Pencils", "Puffs", "Cards", "Meters",
    "Tea Bags", "inches",
}

_COLOUR_WORDS = {
    "black", "white", "silver", "gold", "blue", "red", "green",
    "pink", "purple", "yellow", "orange", "grey", "gray", "brown",
    "beige", "navy", "teal", "coral", "lavender", "rose", "mint",
    "turquoise", "charcoal", "champagne",
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 ─ BRAND SCANNING (uses master_brands.csv list)
# ─────────────────────────────────────────────────────────────────────────────

def _scan_brand_from_title(title: str, brands_list: List[dict]) -> Tuple[str, str]:
    """
    Scan the title to find the best matching brand from the master brands list.

    brands_list must be a list of dicts: [{'brand_id': str, 'brand::en': str}, ...]
    The list MUST already be sorted by brand name length DESCENDING so that
    longer/more-specific brand names match before shorter ones.
    (e.g., "The Ordinary" before "The", "L'Oreal Paris" before "L'Oreal")

    Returns (brand_id, brand_display_name) or ("", "") if no match.
    """
    if not brands_list or not title:
        return "", ""

    title_lower = title.lower().strip()

    for brand in brands_list:
        bn = str(brand.get("brand::en", "")).strip()
        if not bn or bn.lower() in ("nan", "none", ""):
            continue

        bn_lower = bn.lower()
        # Check if title starts with brand name followed by a word boundary
        # (space, comma, digit, or end-of-string)
        if title_lower.startswith(bn_lower):
            rest = title_lower[len(bn_lower):]
            if rest == "" or rest[0] in (" ", ",", "-", "/", "(", "0123456789"):
                return str(brand.get("brand_id", "")), bn

    return "", ""


def prepare_brands_list(brands_df) -> List[dict]:
    """
    Prepare the brands list from a DataFrame loaded from master_brands.csv.
    Sorts longest brand name first so _scan_brand_from_title matches correctly.

    Usage:
        import pandas as pd
        brands_df = pd.read_csv("master_brands.csv")
        brands_list = prepare_brands_list(brands_df)
    """
    brands_df = brands_df.dropna(subset=["brand::en"])
    brands_df = brands_df[brands_df["brand::en"].astype(str).str.strip() != ""]
    brands_df = brands_df[["brand_id", "brand::en"]].drop_duplicates(subset=["brand::en"])
    brands_df["_len"] = brands_df["brand::en"].str.len()
    brands_df = brands_df.sort_values("_len", ascending=False)
    return brands_df[["brand_id", "brand::en"]].to_dict("records")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 ─ LOW-LEVEL TEXT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _clean_raw(text: str) -> str:
    """Remove non-printing / non-standard characters and normalise whitespace."""
    if not isinstance(text, str):
        return ""
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\u200c", "")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _title_case_word(word: str, is_first: bool = False, brand_all_caps: bool = False) -> str:
    """Apply smart title-casing to a single word token."""
    lower = word.lower()

    # 1. Exact canonical lookup
    if lower in _CANONICAL_TOKENS:
        return _CANONICAL_TOKENS[lower]

    # Partial SPF match (e.g. "SPF50+" not in table)
    spf_m = re.fullmatch(r"(spf)(\d+\+?)", lower)
    if spf_m:
        return f"SPF{spf_m.group(2)}"

    # 2. ALL-CAPS brand first word
    if brand_all_caps and is_first:
        return word.upper()

    # 3. Lowercase exceptions (only non-first words)
    if lower in _LOWERCASE_WORDS and not is_first:
        return lower

    # 4. Preserve intentional mixed-case (pH, eBay, iPhone …)
    stripped = re.sub(r"[^a-zA-Z]", "", word)
    if stripped and (stripped != stripped.lower()) and (stripped != stripped.upper()):
        return word

    # 5. Default: capitalise first alpha character
    return re.sub(r"[a-z]", lambda m: m.group(0).upper(), word, count=1)


def _smart_title_case(text: str,
                      brand_all_caps: bool = False,
                      preserve_first_lower: bool = False) -> str:
    """Apply Talabat-style title casing to the descriptive portion of a title."""
    if not text:
        return text

    tokens = re.split(r"(\s+)", text)
    result_tokens = []
    word_index = 0

    for token in tokens:
        if re.fullmatch(r"\s+", token):
            result_tokens.append(token)
            continue

        is_first = (word_index == 0)
        word_index += 1
        effective_first = is_first and not preserve_first_lower

        # ── Whole token canonical check (e.g. mk-7 before splitting) ─────
        if token.lower() in _CANONICAL_TOKENS:
            result_tokens.append(_CANONICAL_TOKENS[token.lower()])
            continue

        # ── Inline measurement: 500mg / 50ml / 10cm mid-title ─────────────
        inline_m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]{1,5})", token.lower())
        if inline_m and inline_m.group(2) in _COMPACT_UNITS:
            result_tokens.append(f"{inline_m.group(1)}{inline_m.group(2)}")
            continue

        # ── Hyphen / slash compound (3-in-1, BHA/AHA, Anti-Acne) ─────────
        parts = re.split(r"([-/])", token)
        if len(parts) > 1:
            new_parts = []
            sub_first = effective_first
            for part in parts:
                if re.fullmatch(r"[-/]", part):
                    new_parts.append(part)
                else:
                    lo = part.lower()
                    if lo in _CANONICAL_TOKENS:
                        new_parts.append(_CANONICAL_TOKENS[lo])
                    else:
                        new_parts.append(
                            _title_case_word(part, is_first=sub_first,
                                             brand_all_caps=brand_all_caps)
                        )
                    sub_first = False
            result_tokens.append("".join(new_parts))
        else:
            result_tokens.append(
                _title_case_word(token, is_first=effective_first,
                                 brand_all_caps=brand_all_caps)
            )

    return "".join(result_tokens)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 ─ SIZE / QUANTITY DETECTION & FORMATTING
# ─────────────────────────────────────────────────────────────────────────────

_ALL_UNIT_PATTERNS = sorted(_UNIT_NORMALISE.keys(), key=len, reverse=True)

_SIZE_RE = re.compile(
    r"""(?ix)
    (?P<multipack>(?:\d+(?:\.\d+)?\s*[x×*]\s*)+)?
    (?P<value>\d+(?:\.\d+)?)
    \s*
    (?P<unit>"""
    + "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS)
    + r'|")'
    + r"""
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _format_size_suffix(raw_size: str) -> str:
    """Return the canonical formatted size string from a raw tail."""
    raw = raw_size.strip()

    # ── fl oz ────────────────────────────────────────────────────────────
    fl_match = re.fullmatch(
        r"(?i)(?P<mp>(?:\d+(?:\.\d+)?[x×*])+)?(?P<v>\d+(?:\.\d+)?)\s*fl\.?\s*oz\.?", raw
    )
    if fl_match:
        mp = re.sub(r"[×*]", "x", fl_match.group("mp") or "").replace(" ", "")
        return f"{mp}{fl_match.group('v')} fl oz"

    # ── Dimension (NxMxPunit, e.g. 31x12x41cm) ───────────────────────────
    dim_match = re.fullmatch(
        r"(?i)(?P<dims>(?:\d+(?:\.\d+)?[x×*]){1,3}\d+(?:\.\d+)?)\s*(?P<unit>[a-z\"]+)", raw
    )
    if dim_match:
        dims = re.sub(r"[×*]", "x", dim_match.group("dims")).replace(" ", "")
        uc = _UNIT_NORMALISE.get(dim_match.group("unit").lower().replace('"', "inches"),
                                  dim_match.group("unit").lower())
        sep = "" if uc in _COMPACT_UNITS else " "
        return f"{dims}{sep}{uc}"

    # ── General ───────────────────────────────────────────────────────────
    m = _SIZE_RE.fullmatch(raw)
    if m:
        mp = re.sub(r"[×* ]+", "x", m.group("multipack") or "").strip("x")
        if mp:
            mp += "x"
        value = m.group("value")
        unit_raw = (m.group("unit") or "").lower().strip()
        uc = _UNIT_NORMALISE.get(unit_raw, unit_raw)
        sep = "" if uc in _COMPACT_UNITS else " "
        return f"{mp}{value}{sep}{uc}"

    return raw


def _extract_size_from_end(text: str) -> Tuple[str, str]:
    """
    Split a title into (body, size_suffix).

    Priority:
      1. Last comma split → validate tail
      2. Regex scan for numeric+unit at end (no comma)
      3. Trailing colour word (for electronics/fashion)
    """
    text = text.strip()

    # ── 1. Last comma split ───────────────────────────────────────────────
    if "," in text:
        last_comma = text.rfind(",")
        body = text[:last_comma].strip()
        tail = text[last_comma + 1:].strip()

        # Colour after comma
        if tail.lower() in _COLOUR_WORDS:
            return body, tail.title()

        # Size pattern match (includes "1 Piece", "3x1L", "16.9 fl oz" …)
        if _SIZE_RE.search(tail) or re.fullmatch(
            r"(?i)(?:\d+(?:\.\d+)?\s*[x×*]\s*)*\d+(?:\.\d+)?\s*[a-z\"]{1,10}(?:\s+[a-z]{1,10})?",
            tail,
        ):
            return body, tail

        # Anything else (size variant, colour, model number) — keep as tail
        return body, tail

    # ── 2. Regex scan at end (no comma) ──────────────────────────────────
    end_re = re.compile(
        r"""(?ix)
        (?P<space>\s+)
        (?P<full>
            (?:(?:\d+(?:\.\d+)?\s*[x×*]\s*)+)?
            \d+(?:\.\d+)?
            \s*
            (?:"""
        + "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS)
        + r"""|")
        )$""",
        re.VERBOSE | re.IGNORECASE,
    )
    em = end_re.search(text)
    if em:
        return text[: em.start()].strip(), em.group("full").strip()

    # ── 3. Trailing colour word (no comma, no unit) ────────────────────
    colour_re = re.compile(
        r"(?i)\s+(" + "|".join(re.escape(c) for c in _COLOUR_WORDS) + r")$"
    )
    cm = colour_re.search(text)
    if cm:
        return text[: cm.start()].strip(), cm.group(1).strip().title()

    return text, ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 ─ BRAND NAME HELPERS (hardcoded fallback, no CSV required)
# ─────────────────────────────────────────────────────────────────────────────

_SPECIAL_BRANDS = {
    "l_oreal_paris":    "L'Oreal Paris",
    "l_oreal":          "L'Oreal",
    "m_s":              "M&S",
    "marks_and_spencer":"Marks & Spencer",
    "a_h":              "A&H",
    "a_t":              "A&T",
    "make_p_rem":       "make p:rem",
    "i_m_from":         "I'm From",
    "dr_c_tuna":        "Dr.C.Tuna",
    "dr_althea":        "Dr.Althea",
    "the_ordinary":     "The Ordinary",
    "the_inkey_list":   "The Inkey List",
    "7up":              "7Up",
    "no_brand":         "",
    "unbranded":        "",
    "new_brand":        "",
    "household_essentials": "",
}


def _brand_id_to_display(brand_id: str) -> str:
    """Convert snake_case brand_id to a human-readable display name."""
    if not brand_id or not isinstance(brand_id, str):
        return ""
    lo = brand_id.lower()
    if lo in _SPECIAL_BRANDS:
        return _SPECIAL_BRANDS[lo]
    if lo in _ALLCAPS_BRAND_IDS:
        return brand_id.replace("_", " ").upper()
    parts = brand_id.replace("_", " ").split()
    return " ".join(p.capitalize() for p in parts)


def _detect_brand_all_caps(brand_id: str, first_word: str) -> bool:
    """Return True if the brand should appear ALL CAPS in the title."""
    if brand_id and brand_id.lower() in _ALLCAPS_BRAND_IDS:
        return True
    stripped = re.sub(r"[^a-zA-Z]", "", first_word)
    return len(stripped) >= 3 and stripped == stripped.upper()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 ─ STRUCTURED SIZE BUILDER (from separate columns)
# ─────────────────────────────────────────────────────────────────────────────

def _build_structured_size(contents_value: str, contents_unit: str) -> str:
    """
    Build a canonical size string from structured contentsValue + contentsUnit.
    Handles "1 Piece", "3 Sachets", "120ml", "2x500g" etc.
    Returns empty string if inputs are blank/zero/invalid.
    """
    cv_str = str(contents_value).strip().replace("nan", "").replace("None", "")
    cu_str = str(contents_unit).strip().replace("nan", "").replace("None", "").lower()

    if not cv_str or not cu_str:
        return ""

    # Remove trailing .0 from float-ish integers
    try:
        cv_float = float(cv_str)
    except ValueError:
        return ""

    # 0 is genuinely no quantity; negative is invalid
    if cv_float <= 0:
        return ""

    # Format value: drop .0 suffix for whole numbers
    cv_clean = str(int(cv_float)) if cv_float == int(cv_float) else cv_str.rstrip("0").rstrip(".")

    uc = _UNIT_NORMALISE.get(cu_str, cu_str)

    if uc in _COMPACT_UNITS:
        return f"{cv_clean}{uc}"
    elif uc in _SPACED_UNITS:
        return f"{cv_clean} {uc}"
    else:
        return f"{cv_clean} {uc}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 ─ MAIN format_title() FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def format_title(
    raw_title: str,
    brand_id: str = "",
    brand_name: str = "",
    contents_value: str = "",
    contents_unit: str = "",
    product_type: str = "",
    brands_list: Optional[List[dict]] = None,
) -> dict:
    """
    Format a raw vendor product title into the Talabat catalogue standard.

    Parameters
    ----------
    raw_title      : The messy/raw title from the vendor file.
    brand_id       : Internal brand ID (snake_case) — overridden by brands_list scan.
    brand_name     : Human-readable brand name — overridden by brands_list scan.
    contents_value : Numeric size value (e.g. '120', '1').
    contents_unit  : Size unit (e.g. 'ml', 'piece').
    product_type   : Product category type from taxonomy.
    brands_list    : Pre-sorted list of {'brand_id': str, 'brand::en': str} dicts
                     from master_brands.csv. Sort ONCE at load time (longest first).

    Returns
    -------
    dict:
        formatted_title – Clean, properly formatted title string.
        extracted_size  – The size/unit portion that was detected (or '').
        brand_id        – Matched brand_id from master brands list (or '').
        brand_name      – Matched brand display name (or '').
        issues          – List of warning strings (empty = perfect).
        confidence      – 'high' | 'medium' | 'low'
    """
    issues = []

    # ── Input validation ──────────────────────────────────────────────────
    if not raw_title or not isinstance(raw_title, str):
        return {
            "formatted_title": "",
            "extracted_size": "",
            "brand_id": "",
            "brand_name": "",
            "issues": ["Empty or invalid title"],
            "confidence": "low",
        }

    # ── Step 1: Clean ──────────────────────────────────────────────────────
    text = _clean_raw(raw_title)

    # Remove marketing filler phrases
    _FILLER = [
        r"\bBuy\s+\d+\s+Get\s+\d+\s+Free\b",
        r"\(\s*\d+[a-zA-Z]*\s+Extra\s+Free\s*\)",
        r"\bValue\s+Pack\b",
        r"\bOpen\s+Box\b",
        r"\bAssorted\b(?=\s*\))",
    ]
    for pat in _FILLER:
        m = re.search(pat, text, re.I)
        if m:
            issues.append(f"Removed filler: '{m.group(0)}'")
            text = re.sub(r"\s{2,}", " ", re.sub(pat, "", text, flags=re.I)).strip(" ,")

    # ── Step 2: Brand detection ────────────────────────────────────────────
    # Priority: brands_list scan > explicit brand_id param
    detected_brand_id = ""
    detected_brand_name = ""

    if brands_list:
        detected_brand_id, detected_brand_name = _scan_brand_from_title(text, brands_list)

    # Fall back to hardcoded brand_id if master scan found nothing
    resolved_brand_id = detected_brand_id or brand_id
    resolved_brand_name = (
        detected_brand_name
        or (brand_name.strip() if brand_name else "")
        or _brand_id_to_display(brand_id)
    )

    # Flag unbranded products (only when brands_list is provided, so we had
    # a chance to find it and still didn't)
    if brands_list and not resolved_brand_id:
        issues.append("Unbranded - Audit Required")

    # Casing flags
    words = text.split()
    first_word = words[0] if words else ""
    brand_is_allcaps = _detect_brand_all_caps(resolved_brand_id, first_word)
    preserve_first_lower = resolved_brand_id.lower() in _LOWERCASE_BRAND_IDS or (
        resolved_brand_name and resolved_brand_name[0].islower()
    )

    # ── Step 3: Extract size suffix ────────────────────────────────────────
    body, raw_size = _extract_size_from_end(text)

    # Build structured size from separate columns (if provided)
    structured_size = _build_structured_size(contents_value, contents_unit)

    # Decide which size to use
    extracted_size = ""
    if raw_size:
        try:
            extracted_size = _format_size_suffix(raw_size)
        except Exception:
            extracted_size = raw_size

    if structured_size and not extracted_size:
        extracted_size = structured_size
        body = text
        issues.append("Size added from structured data columns")
    elif structured_size and extracted_size and structured_size != extracted_size:
        issues.append(
            f"Size note: title='{extracted_size}' vs columns='{structured_size}'"
        )

    # ── Step 4: Title casing ───────────────────────────────────────────────
    body_cased = _smart_title_case(
        body.strip(),
        brand_all_caps=brand_is_allcaps,
        preserve_first_lower=preserve_first_lower,
    )

    # ── Step 5: Assemble ───────────────────────────────────────────────────
    final_title = f"{body_cased}, {extracted_size}" if extracted_size else body_cased
    final_title = re.sub(r",\s*,", ",", final_title).strip(" ,")
    final_title = re.sub(r" {2,}", " ", final_title)

    # ── Step 6: Confidence score ───────────────────────────────────────────
    # "Unbranded" counts as a real issue; size notes are softer
    hard_issues = [i for i in issues if "Unbranded" in i or "Empty" in i]
    soft_issues = [i for i in issues if i not in hard_issues]

    if not issues:
        confidence = "high"
    elif hard_issues:
        confidence = "low"
    elif len(soft_issues) == 1:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "formatted_title": final_title,
        "extracted_size":  extracted_size,
        "brand_id":        resolved_brand_id,
        "brand_name":      resolved_brand_name,
        "issues":          issues,
        "confidence":      confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 ─ SELF-TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Simulate a tiny brands_list (normally loaded from master_brands.csv)
    mock_brands = [
        {"brand_id": "the_ordinary",     "brand::en": "The Ordinary"},
        {"brand_id": "wellage",           "brand::en": "WELLAGE"},
        {"brand_id": "plu",               "brand::en": "Plu"},
        {"brand_id": "cornetto",          "brand::en": "Cornetto"},
        {"brand_id": "natural_factors",   "brand::en": "Natural Factors"},
        {"brand_id": "belkin",            "brand::en": "Belkin"},
        {"brand_id": "atyab",             "brand::en": "Atyab"},
        {"brand_id": "m_s",               "brand::en": "M&S"},
        {"brand_id": "jbl",               "brand::en": "JBL"},
        {"brand_id": "make_p_rem",        "brand::en": "make p:rem"},
        {"brand_id": "sif",               "brand::en": "Sif"},
        {"brand_id": "malu",              "brand::en": "Malu Wilz"},
        {"brand_id": "gatorade",          "brand::en": "Gatorade"},
        {"brand_id": "voolga",            "brand::en": "Voolga"},
        {"brand_id": "life_extension",    "brand::en": "Life Extension"},
        {"brand_id": "juniors",           "brand::en": "Juniors"},
        {"brand_id": "al_alali",          "brand::en": "Al Alali"},
    ]
    # Sort longest-first (normally done once at app startup via prepare_brands_list)
    mock_brands.sort(key=lambda b: len(b["brand::en"]), reverse=True)

    TESTS = [
        # (raw_title, expected_formatted, description)
        ("the ordinary salicylic acid 2% masque 100ml",
         "The Ordinary Salicylic Acid 2% Masque, 100ml",
         "lowercase input + inline size"),
        ("WELLAGE real hyaluronic blue 100 ampoule, 60ML",
         "WELLAGE Real Hyaluronic Blue 100 Ampoule, 60ml",
         "ALL-CAPS brand + uppercase unit"),
        ("plu 3-in-1 cotton blossom body scrub, 200G",
         "Plu 3-in-1 Cotton Blossom Body Scrub, 200g",
         "hyphenated descriptor"),
        ("cornetto classico ice cream, 6x90ml",
         "Cornetto Classico Ice Cream, 6x90ml",
         "multipack"),
        ("natural factors vitamin k2 mk-7, 180 capsules",
         "Natural Factors Vitamin K2 MK-7, 180 Capsules",
         "canonical token MK-7 + count unit"),
        ("belkin soundform mini kids wired headphones blue",
         "Belkin Soundform Mini Kids Wired Headphones, Blue",
         "colour suffix, no comma"),
        ("Atyab White Beans 750G",
         "Atyab White Beans, 750g",
         "inline size, no comma"),
        ("M&S Rich & Fruity Hot Cross Buns, 2x2 Pieces",
         "M&S Rich & Fruity Hot Cross Buns, 2x2 Pieces",
         "ampersand brand + multipack count"),
        ("JBL charge red portable bluetooth speaker",
         "JBL Charge Red Portable Bluetooth Speaker",
         "ALL-CAPS brand, no size"),
        ("make p:rem glutamin antioxidant radiance serum 50ml",
         "make p:rem Glutamin Antioxidant Radiance Serum, 50ml",
         "intentional lowercase brand"),
        ("Sif Dishwashing Liquid Lemon Scent, 3x1L",
         "Sif Dishwashing Liquid Lemon Scent, 3x1l",
         "multipack litres"),
        ("Malu Wilz Vitamin C Collagen Cream, 50 Ml",
         "Malu Wilz Vitamin C Collagen Cream, 50ml",
         "spaced uppercase unit"),
        ("gatorade fit tropical mango beverage, 16.9 fl oz",
         "Gatorade FIT Tropical Mango Beverage, 16.9 fl oz",
         "fl oz unit"),
        ("Voolga Sodium Hyaluronate Repair Set, 5x1.3ml",
         "Voolga Sodium Hyaluronate Repair Set, 5x1.3ml",
         "decimal multipack"),
        ("Life Extension D-L Phenylalanine Capsules 500mg, 100 capsules",
         "Life Extension D-L Phenylalanine Capsules 500mg, 100 Capsules",
         "inline mg + count capsules"),
        # ── NEW v3 tests: 1 Piece / 1 Pack / structured data ──────────────
        ("Multipurpose Plastic Basket",
         "Multipurpose Plastic Basket, 1 Piece",
         "1 Piece from structured data"),
        ("Juniors Popper Walker",
         "Juniors Popper Walker, 1 Piece",
         "toy, 1 piece from structured"),
        ("Al Alali Ground Red Pepper In Olive Oil",
         "Al Alali Ground Red Pepper in Olive Oil, 340g",
         "preposition lowercase + structured size"),
    ]

    # Last 3 tests use structured data, simulate here
    STRUCTURED = {
        "Multipurpose Plastic Basket":                  ("1", "piece"),
        "Juniors Popper Walker":                        ("1", "piece"),
        "Al Alali Ground Red Pepper In Olive Oil":      ("340", "g"),
    }

    print("=" * 72)
    print("SMART TITLE FORMATTER v3 — SELF TEST")
    print("=" * 72)
    passed = failed = 0

    for raw, expected, desc in TESTS:
        cv, cu = STRUCTURED.get(raw, ("", ""))
        result = format_title(
            raw_title=raw,
            contents_value=cv,
            contents_unit=cu,
            brands_list=mock_brands,
        )
        ok = result["formatted_title"].lower() == expected.lower()
        flag = "✅" if ok else "⚠️ "
        passed += ok
        failed += (not ok)
        print(f"\n{flag} [{result['confidence'].upper()}] {desc}")
        print(f"   IN : {raw!r}")
        print(f"   OUT: {result['formatted_title']!r}")
        if not ok:
            print(f"   EXP: {expected!r}")
        if result["brand_id"]:
            print(f"   BID: {result['brand_id']!r}")
        for iss in result["issues"]:
            print(f"   ⚠  {iss}")

    print()
    print(f"Results: {passed}/{len(TESTS)} passed  ({failed} diffs)")
    print("=" * 72)
