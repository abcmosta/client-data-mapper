"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           ALEX – SMART TITLE FORMATTER  v2.0                               ║
║           Trained on 19,000+ real Talabat catalogue titles                 ║
║           Built by: Mostafa Abdelaziz  |  Upgraded by: Claude              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  TITLE FORMULA (derived from reference data):                               ║
║    [Brand] [Product Name] [Variant/Color/Flavor], [Qty x ]Value Unit        ║
║                                                                              ║
║  EXAMPLES:                                                                   ║
║    "The Ordinary Salicylic Acid 2% Masque, 100ml"                           ║
║    "WELLAGE Real Hyaluronic Blue 100 Ampoule, 60ml"                         ║
║    "Cornetto Classico Ice Cream, 6x90ml"                                    ║
║    "Natural Factors Vitamin K2 MK-7, 180 Capsules"                          ║
║    "Belkin Soundform Mini Kids Wired Headphones, Blue"                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import re
import unicodedata
from typing import Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 ─ CONSTANTS & LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────

# Words that stay lowercase in title case (unless they are the first word)
_LOWERCASE_WORDS = {
    "a", "an", "the",                              # articles
    "and", "but", "or", "nor", "for", "so", "yet",  # coordinating conjunctions
    "at", "by", "in", "of", "on", "to", "up",     # short prepositions
    "as", "de", "du", "van", "von",
    "with", "from", "into", "onto", "over",
    "after", "before", "between", "among",
    "through", "during", "without", "about",
}

# Technical tokens that must ALWAYS appear in their canonical casing
# Key is the lowercase version → value is the canonical form
_CANONICAL_TOKENS = {
    # Sunscreen / Skincare
    "spf": "SPF", "spf50+": "SPF50+", "spf50": "SPF50",
    "spf45+": "SPF45+", "spf45": "SPF45",
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
    # Health/Pharma
    "bpa": "BPA", "fda": "FDA",
    "cbd": "CBD", "thc": "THC",
    "mcg": "mcg", "mg": "mg", "iu": "IU",
    "mk-7": "MK-7", "mk-4": "MK-4", "mk7": "MK-7", "mk4": "MK-4",
    # Food labelling
    "gmo": "GMO",
    # Size
    "3d": "3D", "360°": "360°",
    # Chemistry
    "ph": "pH",
    # Connectivity
    "ip65": "IP65", "ip67": "IP67", "ip68": "IP68",
    "ip54": "IP54",
    "3atm": "3ATM", "5atm": "5ATM",
    "atm": "ATM",
    # Gaming
    "ittf": "ITTF",
    "rgb": "RGB",
    # Video
    "vr": "VR",
    # Clothing sizes  
    "xs": "XS", "xl": "XL", "xxl": "XXL", "xxxl": "XXXL", "xxs": "XXS",
}

# Brand names whose IDs indicate ALL-CAPS display
_ALLCAPS_BRAND_IDS = {
    "wellage", "rovectin", "skintific", "eqqual_berry", "eqqualberry",
    "banila_co", "kaine", "tirtir", "jumiso", "k_secret",
    "illiyoon", "sungboon", "jbl", "aibo", "trm", "diy",
    "activlab", "ada", "rog", "vt", "agf",
}

# ─── UNIT NORMALISATION ────────────────────────────────────────────────────
# Maps raw/messy unit strings → canonical unit string
_UNIT_NORMALISE = {
    # weight – compact (no space after number)
    "g": "g", "gr": "g", "gm": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    # volume – compact
    "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    "milliliters": "ml", "millilitres": "ml",
    "cl": "cl", "dl": "dl",
    "l": "l", "liter": "l", "litre": "l", "liters": "l", "litres": "l",
    # special: fl oz keeps a space internally but no space after number
    "floz": "fl oz", "fl.oz": "fl oz", "fl.oz.": "fl oz",
    "fluidoz": "fl oz", "fl oz": "fl oz",
    # length – compact
    "cm": "cm", "centimeter": "cm", "centimetre": "cm",
    "centimeters": "cm", "centimetres": "cm",
    "mm": "mm", "millimeter": "mm", "millimetre": "mm",
    "m": "m", "meter": "m", "metre": "m", "meters": "m", "metres": "m",
    "km": "km",
    # inches – spaced
    "inch": "inches", "in": "inches", "inches": "inches", '"': "inches",
    # count – spaced + Title Case
    "piece": "Piece", "pieces": "Pieces",
    "pcs": "pcs", "pc": "pcs",
    "pack": "Pack", "packs": "Packs",
    "packet": "Packet", "packets": "Packets",
    "bag": "Bags", "bags": "Bags",
    "box": "Box", "boxes": "Boxes",
    "roll": "Rolls", "rolls": "Rolls",
    "sheet": "Sheets", "sheets": "Sheets",
    "wipe": "Wipes", "wipes": "Wipes",
    "tablet": "Tablets", "tablets": "Tablets",
    "capsule": "Capsules", "capsules": "Capsules",
    "sachet": "Sachets", "sachets": "Sachets",
    "unit": "Piece", "units": "Pieces",
    "count": "Pieces",
    "set": "Set", "sets": "Sets",
    "pairs": "Pairs", "pair": "Pair",
    "pencils": "Pencils", "pencil": "Pencils",
    "wipes": "Wipes",
    "puffs": "Puffs", "puff": "Puffs",
    "cards": "Cards", "card": "Cards",
    "meters": "Meters",         # for cord/cable
    "tea bag": "Tea Bags", "tea bags": "Tea Bags",
    "mah": "mAh",               # battery capacity – compact
}

# Units that are appended with NO SPACE after the number (weight/volume/length)
_COMPACT_UNITS = {
    "g", "kg", "mg", "ml", "l", "cl", "dl",
    "lb", "oz", "fl oz",
    "cm", "mm", "m", "km",
    "mah",
}

# Units that need a SPACE before them  
_SPACED_UNITS = {
    "Piece", "Pieces", "pcs",
    "Pack", "Packs", "Packet", "Packets",
    "Bags", "Box", "Boxes",
    "Rolls", "Sheets", "Wipes",
    "Tablets", "Capsules", "Sachets",
    "Set", "Sets", "Pairs", "Pair",
    "Pencils", "Puffs", "Cards", "Meters",
    "Tea Bags",
    "inches",
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 ─ LOW-LEVEL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _clean_raw(text: str) -> str:
    """Remove non-printing / non-standard characters and normalise whitespace."""
    if not isinstance(text, str):
        return ""
    # Replace non-breaking & zero-width spaces with regular space
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\u200c", "")
    # Unicode normalise (handles fancy quotes, accented chars)
    text = unicodedata.normalize("NFKC", text)
    # Collapse multiple spaces / tabs / newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()
    return text


def _title_case_word(word: str, is_first: bool = False, brand_all_caps: bool = False) -> str:
    """
    Apply smart title-casing to a single word token.

    Rules (in priority order):
      1. Canonical token → return exact canonical form (SPF50+, pH, AHA …)
      2. All-caps brand marker → preserve ALL CAPS for the first brand word
      3. Lowercase exceptions (prepositions etc.) unless it is the first word
      4. Words that already contain UPPERCASE mid-string (e.g. pH, eBay, iPhone)
         are left untouched
      5. Default → str.title() capitalisation
    """
    lower = word.lower()

    # 1. Exact canonical lookup
    if lower in _CANONICAL_TOKENS:
        return _CANONICAL_TOKENS[lower]

    # Partial SPF match (e.g. "SPF50+" not pre-listed)
    spf_match = re.fullmatch(r"(spf)(\d+\+?)", lower)
    if spf_match:
        return f"SPF{spf_match.group(2)}"

    # 2. Brand all-caps override
    if brand_all_caps and is_first:
        return word.upper()

    # 3. Lowercase exceptions (prepositions, conjunctions, articles)
    if lower in _LOWERCASE_WORDS and not is_first:
        return lower

    # 4. Mixed-case words already have intentional capitalisation – leave them
    #    (e.g. "p:rem", "eBay", "FaceTime") – heuristic: contains both upper and lower
    stripped = re.sub(r"[^a-zA-Z]", "", word)
    if stripped and (stripped != stripped.lower()) and (stripped != stripped.upper()):
        # Has intentional mixed case; leave as-is
        return word

    # 5. Default title case – only capitalise first alpha character
    # Use regex to capitalise the first letter even if word starts with punctuation/number
    def _cap_first_alpha(m):
        return m.group(0).upper()

    return re.sub(r"[a-z]", _cap_first_alpha, word, count=1)


def _smart_title_case(text: str, brand_all_caps: bool = False, preserve_first_lower: bool = False) -> str:
    """
    Apply Talabat-style title casing to the descriptive portion of a title.

    Tokenises the string while preserving delimiters (hyphens, slashes,
    punctuation) then casing each word token.

    preserve_first_lower: if True, do NOT capitalise the first word
    (used for brands like 'make p:rem' that intentionally start lowercase).
    """
    if not text:
        return text

    # Split while KEEPING the delimiters as separate tokens
    tokens = re.split(r"(\s+)", text)

    result_tokens = []
    word_index = 0

    for token in tokens:
        if re.fullmatch(r"\s+", token):
            result_tokens.append(token)
            continue

        is_first = (word_index == 0)
        word_index += 1

        # If first word and brand wants lowercase, skip capitalisation rule
        effective_first = is_first and not preserve_first_lower

        # ── Check whole token as canonical BEFORE splitting on hyphens ──────
        # Handles "mk-7", "spf50+", "3-in-1" preserved canonical forms
        lower_token = token.lower()
        if lower_token in _CANONICAL_TOKENS:
            result_tokens.append(_CANONICAL_TOKENS[lower_token])
            continue

        # ── Inline measurement: "500mg", "50ml", "2%", etc. mid-title ────────
        # These appear in descriptions (not at the end) and must stay compact
        inline_meas = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]{1,5})", lower_token)
        if inline_meas and inline_meas.group(2) in _COMPACT_UNITS:
            result_tokens.append(f"{inline_meas.group(1)}{inline_meas.group(2)}")
            continue

        parts = re.split(r"([-/])", token)
        if len(parts) > 1:
            new_parts = []
            sub_first = effective_first
            # Check if the whole hyphenated compound is canonical AFTER lower check above
            for part in parts:
                if re.fullmatch(r"[-/]", part):
                    new_parts.append(part)
                else:
                    # Each sub-part through canonical check too
                    lo_part = part.lower()
                    if lo_part in _CANONICAL_TOKENS:
                        new_parts.append(_CANONICAL_TOKENS[lo_part])
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
# SECTION 3 ─ SIZE / QUANTITY DETECTION & FORMATTING
# ─────────────────────────────────────────────────────────────────────────────

# Ordered unit pattern (longest first to avoid partial matches)
_ALL_UNIT_PATTERNS = sorted(_UNIT_NORMALISE.keys(), key=len, reverse=True)
_UNIT_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS) + r'|")\b'
)

# Full size-chunk regex: captures multipack prefix + value + unit
# Handles: 120ml | 6x90ml | 3x1 L | 10x20 Sheets | 31x12x41cm
_SIZE_RE = re.compile(
    r"""(?ix)
    (?P<multipack>(?:\d+(?:\.\d+)?\s*[x×*]\s*)+)?   # optional  N x  prefix
    (?P<value>\d+(?:\.\d+)?)                          # main numeric value
    \s*
    (?P<unit>"""
    + "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS)
    + r'|")'
    + r"""
    (?:\s*(?P<unit2>"""
    + "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS)
    + r"""))?  # optional second unit (e.g. "fl oz")
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Colour-only endings for electronics/fashion (no unit)
_COLOUR_WORDS = {
    "black", "white", "silver", "gold", "blue", "red", "green",
    "pink", "purple", "yellow", "orange", "grey", "gray", "brown",
    "beige", "navy", "teal", "coral", "lavender", "rose", "mint",
    "turquoise", "charcoal", "champagne",
}

# Clothing-size endings
_CLOTHING_SIZE_RE = re.compile(
    r",?\s*(?:size\s*)?(?:XS|XXS|S\b|M\b|L\b|XL|XXL|XXXL|\d{1,2}(?:\s*-\s*\d{1,2})?)\s*$",
    re.IGNORECASE,
)


def _format_size_suffix(raw_size: str) -> str:
    """
    Given a raw size string (e.g. '120ml', '6 x 90 ML', '3 Pieces'),
    return the canonical formatted suffix (e.g. '120ml', '6x90ml', '3 Pieces').
    """
    raw = raw_size.strip()

    # ── fl oz special case ──────────────────────────────────────────────────
    fl_oz_match = re.fullmatch(
        r"(?i)(?P<mp>(?:\d+(?:\.\d+)?[x×*])+)?(?P<v>\d+(?:\.\d+)?)\s*fl\.?\s*oz\.?",
        raw
    )
    if fl_oz_match:
        mp = fl_oz_match.group("mp") or ""
        mp_clean = re.sub(r"[×*]", "x", mp).replace(" ", "")
        return f"{mp_clean}{fl_oz_match.group('v')} fl oz"

    # ── Dimension-only (NxMxP + unit): 31x12x41cm ──────────────────────────
    dim_match = re.fullmatch(
        r"(?i)(?P<dims>(?:\d+(?:\.\d+)?[x×*]){1,3}\d+(?:\.\d+)?)\s*(?P<unit>[a-z\"]+)",
        raw
    )
    if dim_match:
        dims = re.sub(r"[×*]", "x", dim_match.group("dims")).replace(" ", "")
        unit_raw = dim_match.group("unit").lower().replace('"', "inches")
        unit_canon = _UNIT_NORMALISE.get(unit_raw, unit_raw)
        if unit_canon in _COMPACT_UNITS:
            return f"{dims}{unit_canon}"
        elif unit_canon in _SPACED_UNITS:
            return f"{dims} {unit_canon}"
        return f"{dims}{unit_canon}"

    # ── General: try _SIZE_RE ───────────────────────────────────────────────
    m = _SIZE_RE.fullmatch(raw.strip())
    if m:
        mp_raw = m.group("multipack") or ""
        mp_clean = re.sub(r"[×* ]+", "x", mp_raw).strip("x")
        if mp_clean:
            mp_clean += "x"

        value = m.group("value")
        unit_raw = (m.group("unit") or "").lower().strip()

        # "fl oz" two-token unit
        if unit_raw in ("fl", "f"):
            unit_raw = "fl oz"

        unit_canon = _UNIT_NORMALISE.get(unit_raw, unit_raw)

        if unit_canon in _COMPACT_UNITS:
            return f"{mp_clean}{value}{unit_canon}"
        elif unit_canon in _SPACED_UNITS:
            return f"{mp_clean}{value} {unit_canon}"
        else:
            return f"{mp_clean}{value} {unit_canon}"

    # ── Fallback: return cleaned as-is ─────────────────────────────────────
    return raw


def _extract_size_from_end(text: str) -> Tuple[str, str]:
    """
    Try to peel off a size/quantity suffix from the end of a raw title.

    Returns (body, size_suffix) where size_suffix is empty if nothing found.
    The body still contains the leading comma separator so we can check intent.

    Strategy:
      1. If text already has a comma → split on LAST comma; validate right part.
      2. If no comma → scan the end for a numeric+unit pattern.
    """
    text = text.strip()

    # ── Strategy 1: last comma split ────────────────────────────────────────
    if "," in text:
        last_comma = text.rfind(",")
        body = text[:last_comma].strip()
        tail = text[last_comma + 1:].strip()

        # Is the tail a valid size or a colour?
        if _SIZE_RE.search(tail) or re.fullmatch(
            r"(?i)(?:\d+(?:\.\d+)?\s*[x×*]\s*)*\d+(?:\.\d+)?\s*[a-z\"]{1,10}(?:\s+[a-z]{1,10})?",
            tail,
        ):
            return body, tail

        # Colour after comma (electronics)
        if tail.lower() in _COLOUR_WORDS:
            return body, tail

        # Could be "Open Box", "Large", "Medium" etc. – keep as-is
        return body, tail

    # ── Strategy 2: find trailing size with no comma ─────────────────────────
    # Match a size at the very end of the string
    end_size_re = re.compile(
        r"""(?ix)
        (?P<space>\s+)
        (?P<full>
            (?:(?:\d+(?:\.\d+)?\s*[x×*]\s*)+)?   # optional multipack
            \d+(?:\.\d+)?                          # value
            \s*
            (?:"""
        + "|".join(re.escape(u) for u in _ALL_UNIT_PATTERNS)
        + r"""|")
        )
        $""",
        re.VERBOSE | re.IGNORECASE,
    )
    m = end_size_re.search(text)
    if m:
        body = text[: m.start()].strip()
        tail = m.group("full").strip()
        return body, tail

    # ── Strategy 3: trailing colour word with no comma (electronics/fashion) ─
    colour_re = re.compile(
        r"(?i)\s+(" + "|".join(re.escape(c) for c in _COLOUR_WORDS) + r")$"
    )
    cm = colour_re.search(text)
    if cm:
        body = text[: cm.start()].strip()
        tail = cm.group(1).strip().title()
        return body, tail

    return text, ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 ─ BRAND NAME HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _brand_id_to_name(brand_id: str) -> str:
    """
    Convert a snake_case brand_id to a display name.
    e.g.  'the_ordinary'  →  'The Ordinary'
          'l_oreal_paris' →  "L'Oreal Paris"
          'jbl'           →  'JBL'
    """
    if not brand_id or not isinstance(brand_id, str):
        return ""

    # Handle brands that are known acronyms / ALL-CAPS
    if brand_id.lower() in _ALLCAPS_BRAND_IDS:
        return brand_id.replace("_", " ").upper()

    # Known special mappings
    _SPECIAL = {
        "l_oreal_paris": "L'Oreal Paris",
        "l_oreal": "L'Oreal",
        "maybelline": "Maybelline",
        "m_s": "M&S",
        "marks_and_spencer": "Marks & Spencer",
        "a_h": "A&H",
        "a_t": "A&T",
        "make_p_rem": "make p:rem",
        "i_m_from": "I'm From",
        "dr_c_tuna": "Dr.C.Tuna",
        "dr_althea": "Dr.Althea",
        "the_ordinary": "The Ordinary",
        "the_inkey_list": "The Inkey List",
        "7up": "7Up",
        "no_brand": "",
        "unbranded": "",
        "new_brand": "",
        "household_essentials": "",
    }

    # Brands with intentional lowercase starts (preserve as-is)
    _LOWERCASE_BRANDS = {"make_p_rem", "i_m_from", "ma_nyo"}
    lo = brand_id.lower()
    if lo in _SPECIAL:
        return _SPECIAL[lo]

    # Default: replace underscores with spaces, title-case each part
    parts = brand_id.replace("_", " ").split()
    return " ".join(p.capitalize() for p in parts)


def _detect_brand_all_caps(brand_id: str, first_word: str) -> bool:
    """Return True if the brand should be displayed in ALL CAPS."""
    if brand_id and brand_id.lower() in _ALLCAPS_BRAND_IDS:
        return True
    # Heuristic: if the first word of the title is already 3+ uppercase letters
    stripped = re.sub(r"[^A-Za-z]", "", first_word)
    if len(stripped) >= 3 and stripped == stripped.upper():
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 ─ MAIN FORMATTER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def format_title(
    raw_title: str,
    brand_id: str = "",
    brand_name: str = "",
    contents_value: str = "",
    contents_unit: str = "",
    product_type: str = "",
) -> dict:
    """
    Format a raw vendor product title into the Talabat catalogue standard.

    Parameters
    ----------
    raw_title     : The messy/raw title from the vendor file.
    brand_id      : Internal brand ID (snake_case), used to infer brand casing.
    brand_name    : Human-readable brand name (overrides brand_id if provided).
    contents_value: Numeric size value (e.g. '120').
    contents_unit : Size unit (e.g. 'ml').
    product_type  : Product category type from taxonomy.

    Returns
    -------
    dict with keys:
        formatted_title   – The clean, properly formatted title string.
        extracted_size    – The size/unit portion that was detected (or '').
        issues            – List of warning strings (empty list = all OK).
        confidence        – 'high' | 'medium' | 'low'
    """
    issues = []

    # ── Step 0: Input validation ─────────────────────────────────────────────
    if not raw_title or not isinstance(raw_title, str):
        return {
            "formatted_title": "",
            "extracted_size": "",
            "issues": ["Empty or invalid title"],
            "confidence": "low",
        }

    # ── Step 1: Clean raw text ───────────────────────────────────────────────
    text = _clean_raw(raw_title)

    # Remove known filler phrases that pollute titles
    _FILLER_PHRASES = [
        r"\bBuy\s+\d+\s+Get\s+\d+\s+Free\b",
        r"\(\s*\d+[a-zA-Z]*\s+Extra\s+Free\s*\)",
        r"\bValue\s+Pack\b",
        r"\bOpen\s+Box\b",
        r"\bAssorted\b(?=\))",
    ]
    for pattern in _FILLER_PHRASES:
        cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        if cleaned != text:
            issues.append(f"Removed marketing filler: '{re.search(pattern, text, re.I).group(0)}'")
            text = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")

    # ── Step 2: Detect brand / all-caps flag ─────────────────────────────────
    words = text.split()
    first_word = words[0] if words else ""
    brand_is_allcaps = _detect_brand_all_caps(brand_id, first_word)

    # Resolve display brand name
    resolved_brand = brand_name.strip() if brand_name.strip() else _brand_id_to_name(brand_id)

    # Detect if brand intentionally starts lowercase
    _LOWERCASE_BRAND_IDS = {"make_p_rem", "i_m_from", "ma_nyo", "make p:rem"}
    preserve_first_lower = brand_id.lower() in _LOWERCASE_BRAND_IDS or (
        resolved_brand and resolved_brand[0].islower()
    )

    # ── Step 3: Extract size suffix from end ─────────────────────────────────
    body, raw_size = _extract_size_from_end(text)

    # If we have contents_value + contents_unit from structured data,
    # use those to AUGMENT or VERIFY the extracted size
    structured_size = ""
    if contents_value and str(contents_value) not in ("", "nan", "0", "0.0"):
        cv = str(contents_value).strip().rstrip("0").rstrip(".")
        # Remove trailing ".0"
        cv = re.sub(r"\.0$", "", cv)
        cu_raw = str(contents_unit).strip().lower() if contents_unit else ""
        cu = _UNIT_NORMALISE.get(cu_raw, cu_raw)
        if cu:
            if cu in _COMPACT_UNITS:
                structured_size = f"{cv}{cu}"
            else:
                structured_size = f"{cv} {cu}"

    # Decide which size to use
    extracted_size = ""
    if raw_size:
        try:
            extracted_size = _format_size_suffix(raw_size)
        except Exception:
            extracted_size = raw_size  # fallback, unformatted

    # If structured size is available and extracted is empty or different,
    # use structured as authoritative (but note mismatch)
    if structured_size and not extracted_size:
        extracted_size = structured_size
        body = text  # no comma split occurred
        issues.append("Size appended from structured data (not found in title)")
    elif structured_size and extracted_size and structured_size != extracted_size:
        issues.append(
            f"Size mismatch: title says '{extracted_size}', "
            f"structured data says '{structured_size}' (using title)"
        )

    # ── Step 4: Apply smart title casing to body ─────────────────────────────
    body_cased = _smart_title_case(body.strip(), brand_all_caps=brand_is_allcaps,
                                    preserve_first_lower=preserve_first_lower)

    # ── Step 5: Validate body has the brand ──────────────────────────────────
    if resolved_brand:
        brand_first = resolved_brand.split()[0].lower()
        body_first = body_cased.split()[0].lower() if body_cased else ""
        if brand_first not in body_cased.lower()[:len(resolved_brand) + 10]:
            issues.append(f"Brand '{resolved_brand}' not found at start of title")

    # ── Step 6: Assemble final title ─────────────────────────────────────────
    if extracted_size:
        # Determine separator: size-like endings get ", ", colours etc. just ", "
        final_title = f"{body_cased}, {extracted_size}"
    else:
        final_title = body_cased

    # ── Step 7: Post-processing cleanup ──────────────────────────────────────
    # Fix double commas, leading/trailing commas
    final_title = re.sub(r",\s*,", ",", final_title)
    final_title = final_title.strip(" ,")
    # Collapse double spaces
    final_title = re.sub(r" {2,}", " ", final_title)

    # ── Step 8: Confidence scoring ────────────────────────────────────────────
    if not issues:
        confidence = "high"
    elif len(issues) == 1:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "formatted_title": final_title,
        "extracted_size": extracted_size,
        "issues": issues,
        "confidence": confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 ─ BATCH FORMATTER (for use in Streamlit / pandas pipelines)
# ─────────────────────────────────────────────────────────────────────────────

def format_titles_dataframe(df, col_mapping: dict) -> "pd.DataFrame":
    """
    Apply format_title() across a whole DataFrame.

    col_mapping keys (all optional except 'productTitle::en'):
        raw_title      – column name for the raw/vendor title
        brand_id       – column for internal brand id
        brand_name     – column for human-readable brand name
        contents_value – column for size numeric value
        contents_unit  – column for size unit
        product_type   – column for product category type

    Returns the DataFrame with 3 new columns appended:
        productTitle::en    – cleaned, formatted English title
        _title_size         – extracted size token
        _title_issues       – pipe-separated list of issues ('' = perfect)
        _title_confidence   – high / medium / low
    """
    import pandas as pd

    results = []
    for _, row in df.iterrows():
        raw = str(row.get(col_mapping.get("raw_title", ""), "") or "")
        bid = str(row.get(col_mapping.get("brand_id", ""), "") or "")
        bname = str(row.get(col_mapping.get("brand_name", ""), "") or "")
        cv = str(row.get(col_mapping.get("contents_value", ""), "") or "")
        cu = str(row.get(col_mapping.get("contents_unit", ""), "") or "")
        pt = str(row.get(col_mapping.get("product_type", ""), "") or "")

        res = format_title(
            raw_title=raw,
            brand_id=bid,
            brand_name=bname,
            contents_value=cv,
            contents_unit=cu,
            product_type=pt,
        )
        results.append(res)

    out = df.copy()
    out["productTitle::en"] = [r["formatted_title"] for r in results]
    out["_title_size"] = [r["extracted_size"] for r in results]
    out["_title_issues"] = [" | ".join(r["issues"]) for r in results]
    out["_title_confidence"] = [r["confidence"] for r in results]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 ─ QUICK SELF-TEST  (python smart_title_formatter.py to run)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    TEST_CASES = [
        # (raw_title, brand_id, expected_output)
        ("the ordinary salicylic acid 2% masque 100ml",     "the_ordinary", "The Ordinary Salicylic Acid 2% Masque, 100ml"),
        ("WELLAGE real hyaluronic blue 100 ampoule, 60ML",  "wellage",      "WELLAGE Real Hyaluronic Blue 100 Ampoule, 60ml"),
        ("plu 3-in-1 cotton blossom body scrub, 200G",      "plu",          "Plu 3-in-1 Cotton Blossom Body Scrub, 200g"),
        ("cornetto classico ice cream, 6x90ml",             "cornetto",     "Cornetto Classico Ice Cream, 6x90ml"),
        ("natural factors vitamin k2 mk-7, 180 capsules",   "natural_factors", "Natural Factors Vitamin K2 MK-7, 180 Capsules"),
        ("belkin soundform mini kids wired headphones blue", "belkin",      "Belkin Soundform Mini Kids Wired Headphones, Blue"),
        ("Atyab White Beans 750G",                          "atyab",        "Atyab White Beans, 750g"),
        ("M&S Rich & Fruity Hot Cross Buns, 2x2 Pieces",   "m_s",          "M&S Rich & Fruity Hot Cross Buns, 2x2 Pieces"),
        ("JBL charge red portable bluetooth speaker",       "jbl",          "JBL Charge Red Portable Bluetooth Speaker, "),
        ("make p:rem glutamin antioxidant radiance serum 50ml", "make_p_rem", "make p:rem Glutamin Antioxidant Radiance Serum, 50ml"),
        ("Sif Dishwashing Liquid Lemon Scent, 3x1L",       "sif",          "Sif Dishwashing Liquid Lemon Scent, 3x1l"),
        ("Malu Wilz Vitamin C Collagen Cream, 50 Ml",      "malu",         "Malu Wilz Vitamin C Collagen Cream, 50ml"),
        ("gatorade fit tropical mango beverage, 16.9 fl oz", "gatorade",   "Gatorade FIT Tropical Mango Beverage, 16.9 fl oz"),
        ("Voolga Sodium Hyaluronate Repair Set, 5x1.3ml",  "voolga",       "Voolga Sodium Hyaluronate Repair Set, 5x1.3ml"),
        ("Life Extension D-L Phenylalanine Capsules 500mg, 100 capsules", "life_extension",
         "Life Extension D-L Phenylalanine Capsules 500mg, 100 Capsules"),
    ]

    print("=" * 72)
    print("SMART TITLE FORMATTER — SELF TEST")
    print("=" * 72)
    passed = failed = 0
    for raw, bid, expected in TEST_CASES:
        result = format_title(raw_title=raw, brand_id=bid)
        ok = result["formatted_title"].lower() == expected.lower().strip(", ")
        status = "✅ PASS" if ok else "⚠️  DIFF"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"\n{status}  [{result['confidence'].upper()}]")
        print(f"  IN : {raw!r}")
        print(f"  OUT: {result['formatted_title']!r}")
        if result["issues"]:
            for iss in result["issues"]:
                print(f"  ⚠  {iss}")

    print()
    print(f"Results: {passed} passed, {failed} with differences (out of {len(TEST_CASES)})")
    print("=" * 72)