"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           ALEX – SMART TITLE FORMATTER  v3.1                               ║
║           Trained on 19,000+ real Talabat catalogue titles                 ║
║           Built by: Mostafa Abdelaziz              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  NEW in v3.1:                                                                ║
║    • PIM-compliant contentsUnit output (exact Talabat system strings)       ║
║    • numberOfUnits extraction from multipack pattern (10x50g → 10)         ║
║    • pim_contents_value / pim_contents_unit returned in result              ║
║    • to_pim_unit() public helper for app-level unit normalisation           ║
║    • Prohibited content scanner (tobacco + pork word lists)                 ║
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
    "edp": "EDP", "edt": "EDT", "edc": "EDC",
    "usb": "USB", "usb-c": "USB-C", "usb-a": "USB-A",
    "hdmi": "HDMI", "4k": "4K", "8k": "8K",
    "led": "LED", "lcd": "LCD", "oled": "OLED",
    "hdr": "HDR", "uhd": "UHD", "fhd": "FHD",
    "wifi": "WiFi", "wi-fi": "Wi-Fi",
    "nfc": "NFC", "gps": "GPS",
    "mah": "mAh",
    "bpa": "BPA", "fda": "FDA",
    "cbd": "CBD", "thc": "THC",
    "mcg": "mcg", "mg": "mg", "iu": "IU",
    "mk-7": "MK-7", "mk-4": "MK-4", "mk7": "MK-7", "mk4": "MK-4",
    "gmo": "GMO",
    "3d": "3D", "360°": "360°",
    "ph": "pH",
    "ip65": "IP65", "ip67": "IP67", "ip68": "IP68", "ip54": "IP54",
    "3atm": "3ATM", "5atm": "5ATM", "atm": "ATM",
    "ittf": "ITTF", "rgb": "RGB", "vr": "VR",
    "xs": "XS", "xl": "XL", "xxl": "XXL", "xxxl": "XXXL", "xxs": "XXS",
}

_ALLCAPS_BRAND_IDS = {
    "wellage", "rovectin", "skintific", "eqqual_berry", "eqqualberry",
    "banila_co", "kaine", "tirtir", "jumiso", "k_secret",
    "illiyoon", "sungboon", "jbl", "aibo", "trm", "diy",
    "activlab", "ada", "rog", "vt", "agf",
}

_LOWERCASE_BRAND_IDS = {"make_p_rem", "i_m_from", "ma_nyo"}

# ─── UNIT NORMALISATION (for TITLE DISPLAY) ───────────────────────────────
_UNIT_NORMALISE = {
    "g": "g", "gr": "g", "gm": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg",
    "mg": "mg",
    "lb": "lb", "lbs": "lb",
    "oz": "oz",
    "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    "milliliters": "ml", "millilitres": "ml",
    "cl": "cl", "dl": "dl",
    "l": "l", "liter": "l", "litre": "l", "liters": "l", "litres": "l",
    "fl oz": "fl oz", "floz": "fl oz", "fl.oz": "fl oz", "fl.oz.": "fl oz",
    "cm": "cm", "mm": "mm",
    "m": "m", "meter": "m", "metre": "m", "meters": "m", "metres": "m",
    "km": "km",
    "inch": "inches", "in": "inches", "inches": "inches", '"': "inches",
    "piece": "Piece",    "pieces": "Pieces",
    "pcs": "pcs",        "pc": "pcs",
    "pack": "Pack",      "packs": "Packs",
    "packet": "Packet",  "packets": "Packets",
    "bag": "Bags",       "bags": "Bags",
    "box": "Box",        "boxes": "Boxes",
    "roll": "Rolls",     "rolls": "Rolls",
    "sheet": "Sheets",   "sheets": "Sheets",
    "wipe": "Wipes",     "wipes": "Wipes",
    "tablet": "Tablets", "tablets": "Tablets",
    "capsule": "Capsules","capsules": "Capsules",
    "sachet": "Sachets", "sachets": "Sachets",
    "unit": "Piece",     "units": "Pieces",
    "count": "Pieces",
    "set": "Set",        "sets": "Sets",
    "pair": "Pair",      "pairs": "Pairs",
    "pencils": "Pencils","pencil": "Pencils",
    "puffs": "Puffs",    "puff": "Puffs",
    "cards": "Cards",    "card": "Cards",
    "meters": "Meters",
    "tea bag": "Tea Bags","tea bags": "Tea Bags",
    "mah": "mAh",
    "bunch": "Bunches",  "bunches": "Bunches",
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
    "Tea Bags", "inches", "Bunches",
}

_COLOUR_WORDS = {
    "black", "white", "silver", "gold", "blue", "red", "green",
    "pink", "purple", "yellow", "orange", "grey", "gray", "brown",
    "beige", "navy", "teal", "coral", "lavender", "rose", "mint",
    "turquoise", "charcoal", "champagne",
}

# ─── PIM UNITS (exact Talabat system strings) ─────────────────────────────
_PIM_VALID_UNITS = {
    "bags", "bouquets - flowers", "boxes", "bunches", "capsules",
    "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m",
    "mg", "ml", "oz", "packets", "pieces", "rolls", "sachets",
    "sheets", "tablets", "units",
}

_TO_PIM_UNIT = {
    # weight
    "g": "g", "gr": "g", "gm": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg",
    "kilogram": "kg", "kilograms": "kg",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "oz": "oz", "fl oz": "oz", "floz": "oz", "ounce": "oz", "ounces": "oz",
    # volume
    "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    "milliliters": "ml", "millilitres": "ml",
    "cl": "cl", "centiliter": "cl", "centilitre": "cl",
    "dl": "dl", "deciliter": "dl", "decilitre": "dl",
    "l": "l", "liter": "l", "litre": "l", "liters": "l", "litres": "l",
    # length
    "cm": "cm", "centimeter": "cm", "centimetre": "cm",
    "centimeters": "cm", "centimetres": "cm",
    "cm2": "cm2", "cm3": "cm3",
    "m": "m", "meter": "m", "metre": "m", "meters": "m", "metres": "m",
    # count → PIM strings
    "piece": "pieces",    "pieces": "pieces",
    "pcs": "pieces",      "pc": "pieces",
    "pack": "packets",    "packs": "packets",
    "packet": "packets",  "packets": "packets",
    "bag": "bags",        "bags": "bags",
    "box": "boxes",       "boxes": "boxes",
    "roll": "rolls",      "rolls": "rolls",
    "sheet": "sheets",    "sheets": "sheets",
    "wipe": "units",      "wipes": "units",
    "tablet": "tablets",  "tablets": "tablets",
    "capsule": "capsules","capsules": "capsules",
    "sachet": "sachets",  "sachets": "sachets",
    "unit": "units",      "units": "units",
    "count": "units",
    "bunch": "bunches",   "bunches": "bunches",
    "bouquet": "bouquets - flowers", "bouquets": "bouquets - flowers",
    "flower": "bouquets - flowers",  "flowers": "bouquets - flowers",
    # Title-case display variants
    "Piece": "pieces",    "Pieces": "pieces",
    "Pack": "packets",    "Packs": "packets",
    "Packet": "packets",  "Packets": "packets",
    "Bags": "bags",       "Bag": "bags",
    "Box": "boxes",       "Boxes": "boxes",
    "Roll": "rolls",      "Rolls": "rolls",
    "Sheet": "sheets",    "Sheets": "sheets",
    "Tablet": "tablets",  "Tablets": "tablets",
    "Capsule": "capsules","Capsules": "capsules",
    "Sachet": "sachets",  "Sachets": "sachets",
    "Set": "units",       "Sets": "units",
    "Pair": "units",      "Pairs": "units",
    "Bunches": "bunches", "Bunch": "bunches",
    "Tea Bags": "units",  "pcs": "pieces",
}


def to_pim_unit(raw_unit: str) -> str:
    """Convert any raw unit string → exact Talabat PIM unit string."""
    if not raw_unit:
        return ""
    result = _TO_PIM_UNIT.get(raw_unit) or _TO_PIM_UNIT.get(raw_unit.lower().strip())
    return result or raw_unit.lower().strip()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1b ─ PROHIBITED CONTENT SCANNER
# ─────────────────────────────────────────────────────────────────────────────

_TOBACCO_WORDS = {
    "cigarette", "cigarettes", "cigar", "cigars", "tobacco", "tobaccos",
    "nicotine", "vape", "vaping", "vaper", "e-cigarette", "e-cigarettes",
    "ecigarette", "ecigarettes", "hookah", "shisha", "nargileh",
    "marlboro", "winston", "juul", "iqos", "heets", "heated tobacco",
    "snuff", "snus", "chewing tobacco", "rolling tobacco",
    "pipe tobacco", "smokeless tobacco",
    "vape juice", "vape liquid", "e-liquid", "eliquid",
    "vape pod", "disposable vape", "vape kit",
    "nicotine patch", "nicotine gum", "nicotine pouch",
    "cigarette holder", "cigarette case",
    "rolling paper", "cigarette filter", "tobacco tin",
}

_PORK_WORDS = {
    "pork", "pig", "piglet", "swine", "hog",
    "bacon", "ham", "lard", "prosciutto",
    "pepperoni", "pancetta", "gammon",
    "pork belly", "pork chop", "pork chops",
    "pork ribs", "pork loin", "pulled pork",
    "pork sausage", "pork mince", "pork meatball",
    "pork tenderloin", "pork rind", "pork scratching",
    "pork roast", "pork shoulder", "pork leg",
    "pork fillet", "pork neck", "pork knuckle",
    "suckling pig", "crackling", "chicharron",
    "lardon", "guanciale",
    "pork dumpling", "pork bun", "pork wonton",
    "pork spring roll", "pork gyoza",
}


def scan_prohibited(title: str) -> List[str]:
    """
    Scan a product title for prohibited content (tobacco & pork).
    Returns list of violation strings, or empty list if clean.
    """
    if not title or not isinstance(title, str):
        return []

    title_lower = title.lower()
    violations = []

    for word in _TOBACCO_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", title_lower):
            violations.append(f"TOBACCO: '{word}'")
            break

    for word in _PORK_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", title_lower):
            violations.append(f"PORK: '{word}'")
            break

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 ─ BRAND SCANNING
# ─────────────────────────────────────────────────────────────────────────────

def _scan_brand_from_title(title: str, brands_list: List[dict]) -> Tuple[str, str]:
    if not brands_list or not title:
        return "", ""
    title_lower = title.lower().strip()
    for brand in brands_list:
        bn = str(brand.get("brand::en", "")).strip()
        if not bn or bn.lower() in ("nan", "none", ""):
            continue
        bn_lower = bn.lower()
        if title_lower.startswith(bn_lower):
            rest = title_lower[len(bn_lower):]
            if rest == "" or rest[0] in (" ", ",", "-", "/", "(", "0123456789"):
                return str(brand.get("brand_id", "")), bn
    return "", ""


def prepare_brands_list(brands_df) -> List[dict]:
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
    if not isinstance(text, str):
        return ""
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\u200c", "")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _title_case_word(word: str, is_first: bool = False, brand_all_caps: bool = False) -> str:
    lower = word.lower()
    if lower in _CANONICAL_TOKENS:
        return _CANONICAL_TOKENS[lower]
    spf_m = re.fullmatch(r"(spf)(\d+\+?)", lower)
    if spf_m:
        return f"SPF{spf_m.group(2)}"
    if brand_all_caps and is_first:
        return word.upper()
    if lower in _LOWERCASE_WORDS and not is_first:
        return lower
    stripped = re.sub(r"[^a-zA-Z]", "", word)
    if stripped and (stripped != stripped.lower()) and (stripped != stripped.upper()):
        return word
    return re.sub(r"[a-z]", lambda m: m.group(0).upper(), word, count=1)


def _smart_title_case(text: str,
                      brand_all_caps: bool = False,
                      preserve_first_lower: bool = False) -> str:
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
        if token.lower() in _CANONICAL_TOKENS:
            result_tokens.append(_CANONICAL_TOKENS[token.lower()])
            continue
        inline_m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]{1,5})", token.lower())
        if inline_m and inline_m.group(2) in _COMPACT_UNITS:
            result_tokens.append(f"{inline_m.group(1)}{inline_m.group(2)}")
            continue
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
    raw = raw_size.strip()
    fl_match = re.fullmatch(
        r"(?i)(?P<mp>(?:\d+(?:\.\d+)?[x×*])+)?(?P<v>\d+(?:\.\d+)?)\s*fl\.?\s*oz\.?", raw
    )
    if fl_match:
        mp = re.sub(r"[×*]", "x", fl_match.group("mp") or "").replace(" ", "")
        return f"{mp}{fl_match.group('v')} fl oz"
    dim_match = re.fullmatch(
        r"(?i)(?P<dims>(?:\d+(?:\.\d+)?[x×*]){1,3}\d+(?:\.\d+)?)\s*(?P<unit>[a-z\"]+)", raw
    )
    if dim_match:
        dims = re.sub(r"[×*]", "x", dim_match.group("dims")).replace(" ", "")
        uc = _UNIT_NORMALISE.get(dim_match.group("unit").lower().replace('"', "inches"),
                                  dim_match.group("unit").lower())
        sep = "" if uc in _COMPACT_UNITS else " "
        return f"{dims}{sep}{uc}"
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


def _clean_val(v: str) -> str:
    """Remove trailing .0 from float-formatted integers."""
    if "." in v:
        try:
            f = float(v)
            if f == int(f):
                return str(int(f))
        except ValueError:
            pass
    return v


def _parse_size_components(size_str: str) -> Tuple[int, str, str]:
    """
    Parse a formatted size string into (numberOfUnits, contentsValue, pim_unit).

    "6x90ml"       → (6,  "90",  "ml")
    "10x50g"       → (10, "50",  "g")
    "120ml"        → (1,  "120", "ml")
    "180 Capsules" → (1,  "180", "capsules")
    "1 Piece"      → (1,  "1",   "pieces")
    "2x2 Pieces"   → (2,  "2",   "pieces")
    "31x12x41cm"   → (1,  "",    "")   ← 3-way dimension, not multipack
    """
    if not size_str:
        return 1, "", ""
    s = size_str.strip()

    # Three-number = physical dimension, not a multipack
    if re.fullmatch(r"(?i)\d+(?:\.\d+)?[x×]\d+(?:\.\d+)?[x×]\d+(?:\.\d+)?[a-z]*", s):
        return 1, "", ""

    # Multipack: NxV unit
    mp = re.fullmatch(
        r"(?i)(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*([a-z][a-z0-9 ]*)", s
    )
    if mp:
        n = int(float(mp.group(1)))
        val = _clean_val(mp.group(2))
        return n, val, to_pim_unit(mp.group(3).strip())

    # Compact: Vunit (120ml, 200g)
    compact = re.fullmatch(r"(?i)(\d+(?:\.\d+)?)([a-z]{1,5})", s)
    if compact:
        return 1, _clean_val(compact.group(1)), to_pim_unit(compact.group(2))

    # Spaced: V unit (180 Capsules, 1 Piece)
    spaced = re.fullmatch(r"(?i)(\d+(?:\.\d+)?)\s+([a-z][a-z ]*)", s)
    if spaced:
        return 1, _clean_val(spaced.group(1)), to_pim_unit(spaced.group(2).strip())

    return 1, "", ""


def _extract_size_from_end(text: str) -> Tuple[str, str]:
    text = text.strip()
    if "," in text:
        last_comma = text.rfind(",")
        body = text[:last_comma].strip()
        tail = text[last_comma + 1:].strip()
        if tail.lower() in _COLOUR_WORDS:
            return body, tail.title()
        if _SIZE_RE.search(tail) or re.fullmatch(
            r"(?i)(?:\d+(?:\.\d+)?\s*[x×*]\s*)*\d+(?:\.\d+)?\s*[a-z\"]{1,10}(?:\s+[a-z]{1,10})?",
            tail,
        ):
            return body, tail
        return body, tail
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
    colour_re = re.compile(
        r"(?i)\s+(" + "|".join(re.escape(c) for c in _COLOUR_WORDS) + r")$"
    )
    cm = colour_re.search(text)
    if cm:
        return text[: cm.start()].strip(), cm.group(1).strip().title()
    return text, ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 ─ BRAND NAME HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_SPECIAL_BRANDS = {
    "l_oreal_paris":        "L'Oreal Paris",
    "l_oreal":              "L'Oreal",
    "m_s":                  "M&S",
    "marks_and_spencer":    "Marks & Spencer",
    "a_h":                  "A&H",
    "a_t":                  "A&T",
    "make_p_rem":           "make p:rem",
    "i_m_from":             "I'm From",
    "dr_c_tuna":            "Dr.C.Tuna",
    "dr_althea":            "Dr.Althea",
    "the_ordinary":         "The Ordinary",
    "the_inkey_list":       "The Inkey List",
    "7up":                  "7Up",
    "no_brand":             "",
    "unbranded":            "",
    "new_brand":            "",
    "household_essentials": "",
}


def _brand_id_to_display(brand_id: str) -> str:
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
    if brand_id and brand_id.lower() in _ALLCAPS_BRAND_IDS:
        return True
    stripped = re.sub(r"[^a-zA-Z]", "", first_word)
    return len(stripped) >= 3 and stripped == stripped.upper()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 ─ STRUCTURED SIZE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_structured_size(contents_value: str, contents_unit: str) -> str:
    cv_str = str(contents_value).strip().replace("nan", "").replace("None", "")
    cu_str = str(contents_unit).strip().replace("nan", "").replace("None", "").lower()
    if not cv_str or not cu_str:
        return ""
    try:
        cv_float = float(cv_str)
    except ValueError:
        return ""
    if cv_float <= 0:
        return ""
    cv_clean = str(int(cv_float)) if cv_float == int(cv_float) else cv_str.rstrip("0").rstrip(".")
    uc = _UNIT_NORMALISE.get(cu_str, cu_str)
    if uc in _COMPACT_UNITS:
        return f"{cv_clean}{uc}"
    elif uc in _SPACED_UNITS:
        return f"{cv_clean} {uc}"
    else:
        return f"{cv_clean} {uc}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 ─ MAIN format_title()
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

    Returns dict with keys:
        formatted_title    – Clean English title string.
        extracted_size     – Size/unit portion detected (or '').
        brand_id           – Matched brand_id (or '').
        brand_name         – Matched brand display name (or '').
        number_of_units    – int: 1 for single, N for multipack.
        pim_contents_value – str: unit value for PIM contentsValue column.
        pim_contents_unit  – str: PIM-compliant unit (e.g. "ml", "pieces").
        prohibited         – list: violation strings (tobacco/pork).
        issues             – list: warning strings.
        confidence         – 'high' | 'medium' | 'low'
    """
    issues = []

    if not raw_title or not isinstance(raw_title, str):
        return {
            "formatted_title":    "",
            "extracted_size":     "",
            "brand_id":           "",
            "brand_name":         "",
            "number_of_units":    1,
            "pim_contents_value": "",
            "pim_contents_unit":  "",
            "prohibited":         [],
            "issues":             ["Empty or invalid title"],
            "confidence":         "low",
        }

    text = _clean_raw(raw_title)

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

    detected_brand_id, detected_brand_name = "", ""
    if brands_list:
        detected_brand_id, detected_brand_name = _scan_brand_from_title(text, brands_list)

    resolved_brand_id = detected_brand_id or brand_id
    resolved_brand_name = (
        detected_brand_name
        or (brand_name.strip() if brand_name else "")
        or _brand_id_to_display(brand_id)
    )

    if brands_list and not resolved_brand_id:
        issues.append("Unbranded - Audit Required")

    words = text.split()
    first_word = words[0] if words else ""
    brand_is_allcaps = _detect_brand_all_caps(resolved_brand_id, first_word)
    preserve_first_lower = resolved_brand_id.lower() in _LOWERCASE_BRAND_IDS or (
        resolved_brand_name and resolved_brand_name[0].islower()
    )

    body, raw_size = _extract_size_from_end(text)
    structured_size = _build_structured_size(contents_value, contents_unit)

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
        issues.append(f"Size note: title='{extracted_size}' vs columns='{structured_size}'")

    # Parse numberOfUnits + PIM columns from extracted size
    number_of_units, pim_value, pim_unit = _parse_size_components(extracted_size)

    # Fallback: derive PIM columns from structured data if still empty
    if not pim_value:
        cv_str = str(contents_value).strip().replace("nan", "")
        cu_str = str(contents_unit).strip().replace("nan", "")
        try:
            cv_f = float(cv_str) if cv_str else 0
            if cv_f > 0:
                pim_value = str(int(cv_f)) if cv_f == int(cv_f) else cv_str.rstrip("0").rstrip(".")
                pim_unit  = to_pim_unit(cu_str.lower())
        except (ValueError, TypeError):
            pass

    body_cased = _smart_title_case(
        body.strip(),
        brand_all_caps=brand_is_allcaps,
        preserve_first_lower=preserve_first_lower,
    )

    final_title = f"{body_cased}, {extracted_size}" if extracted_size else body_cased
    final_title = re.sub(r",\s*,", ",", final_title).strip(" ,")
    final_title = re.sub(r" {2,}", " ", final_title)

    prohibited = scan_prohibited(final_title)

    hard_issues = [i for i in issues if "Unbranded" in i or "Empty" in i]
    soft_issues = [i for i in issues if i not in hard_issues]

    if prohibited:
        confidence = "low"
    elif not issues:
        confidence = "high"
    elif hard_issues:
        confidence = "low"
    elif len(soft_issues) == 1:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "formatted_title":    final_title,
        "extracted_size":     extracted_size,
        "brand_id":           resolved_brand_id,
        "brand_name":         resolved_brand_name,
        "number_of_units":    number_of_units,
        "pim_contents_value": pim_value,
        "pim_contents_unit":  pim_unit,
        "prohibited":         prohibited,
        "issues":             issues,
        "confidence":         confidence,
    }