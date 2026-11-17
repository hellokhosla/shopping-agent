"""Colour enrichment (PRD M3) and shopper colour vocabulary.

Nordstrom colour codes: the first digit is the family. Shade overrides cover the
most frequent codes and are PROVISIONAL until hand-checked (PRD agreed change 4).
"""

from __future__ import annotations

import re

FAMILY_BY_DIGIT = {
    "0": "black/grey",
    "1": "white",
    "2": "brown",
    "3": "green",
    "4": "blue",
    "5": "purple",
    "6": "red/pink",
    "7": "yellow/gold",
    "8": "orange",
    "9": "multi",
}

DEFAULT_SHADE = {
    "black/grey": "black",
    "white": "white",
    "brown": "brown",
    "green": "green",
    "blue": "blue",
    "purple": "purple",
    "red/pink": "red",
    "yellow/gold": "yellow",
    "orange": "orange",
    "multi": "multi",
}

NORDSTROM_SHADE_OVERRIDES = {
    "001": "black", "002": "black", "003": "black", "004": "black", "005": "black",
    "006": "black", "007": "black", "009": "black",
    "010": "grey", "011": "grey", "019": "grey", "020": "grey", "021": "grey",
    "030": "grey", "050": "grey", "051": "grey",
    "040": "silver", "041": "silver",
    "100": "white", "101": "ivory", "102": "ivory", "103": "ivory", "110": "cream",
    "200": "brown", "201": "brown", "210": "brown", "230": "brown",
    "240": "tan", "250": "tan", "251": "tan", "260": "tan", "270": "beige", "280": "beige",
    "300": "green", "301": "green", "310": "olive", "330": "olive",
    "400": "blue", "401": "blue", "402": "blue", "403": "blue", "404": "blue", "405": "blue",
    "410": "navy", "411": "navy", "415": "navy",
    "420": "light blue", "425": "light blue", "430": "teal",
    "500": "purple", "530": "lavender",
    "600": "red", "601": "red", "604": "red", "610": "red",
    "620": "burgundy", "680": "burgundy",
    "650": "pink", "651": "pink", "660": "pink", "670": "coral",
    "700": "yellow", "710": "gold", "711": "gold", "712": "gold", "715": "gold",
    "800": "orange",
    "900": "multi", "930": "multi", "950": "multi",
}

# Shopper word -> (family, accepted shades). None means any shade in the family is exact.
COLOR_WORDS: dict[str, tuple[str, frozenset[str] | None]] = {
    "black": ("black/grey", frozenset({"black"})),
    "grey": ("black/grey", frozenset({"grey"})),
    "gray": ("black/grey", frozenset({"grey"})),
    "charcoal": ("black/grey", frozenset({"grey"})),
    "silver": ("black/grey", frozenset({"silver"})),
    "white": ("white", frozenset({"white", "ivory", "cream"})),
    "ivory": ("white", frozenset({"ivory", "cream"})),
    "cream": ("white", frozenset({"cream", "ivory"})),
    "brown": ("brown", None),
    "tan": ("brown", frozenset({"tan", "beige"})),
    "beige": ("brown", frozenset({"beige", "tan"})),
    "camel": ("brown", frozenset({"tan"})),
    "nude": ("brown", frozenset({"beige", "tan"})),
    "neutral": ("brown", frozenset({"beige", "tan"})),
    "green": ("green", None),
    "olive": ("green", frozenset({"olive"})),
    "blue": ("blue", None),
    "navy": ("blue", frozenset({"navy"})),
    "light blue": ("blue", frozenset({"light blue"})),
    "teal": ("blue", frozenset({"teal"})),
    "purple": ("purple", None),
    "lavender": ("purple", frozenset({"lavender"})),
    "red": ("red/pink", frozenset({"red"})),
    "burgundy": ("red/pink", frozenset({"burgundy"})),
    "wine": ("red/pink", frozenset({"burgundy"})),
    "pink": ("red/pink", frozenset({"pink"})),
    "coral": ("red/pink", frozenset({"coral"})),
    "yellow": ("yellow/gold", frozenset({"yellow"})),
    "gold": ("yellow/gold", frozenset({"gold"})),
    "orange": ("orange", None),
    "multi": ("multi", None),
    "print": ("multi", None),
}


def nordstrom_color(code: str) -> tuple[str, str]:
    """Map a Nordstrom colour code to (family, shade)."""
    code = (code or "").strip().zfill(3)
    family = FAMILY_BY_DIGIT.get(code[:1], "multi")
    return family, NORDSTROM_SHADE_OVERRIDES.get(code, DEFAULT_SHADE[family])


CALPAK_COLOR_ALIASES = {
    "black": ("black/grey", "black"), "obsidian": ("black/grey", "black"),
    "silver": ("black/grey", "silver"), "gunmetal": ("black/grey", "grey"),
    "grey": ("black/grey", "grey"), "gray": ("black/grey", "grey"), "slate": ("black/grey", "grey"),
    "white": ("white", "white"), "ivory": ("white", "ivory"), "cream": ("white", "cream"),
    "oatmeal": ("brown", "beige"), "mushroom": ("brown", "beige"), "greige": ("brown", "beige"),
    "sand": ("brown", "beige"), "stone": ("brown", "beige"), "taupe": ("brown", "beige"),
    "brown": ("brown", "brown"), "chocolate": ("brown", "brown"), "walnut": ("brown", "brown"),
    "hazelnut": ("brown", "brown"), "mocha": ("brown", "brown"), "latte": ("brown", "brown"),
    "toffee": ("brown", "brown"), "caramel": ("brown", "brown"), "cognac": ("brown", "brown"),
    "navy": ("blue", "navy"), "indigo": ("blue", "blue"), "blue": ("blue", "blue"),
    "cobalt": ("blue", "blue"), "sky": ("blue", "light blue"), "french blue": ("blue", "blue"),
    "green": ("green", "green"), "celadon": ("green", "green"), "sage": ("green", "green"),
    "pine": ("green", "green"), "kale": ("green", "green"), "juniper": ("green", "green"),
    "moss": ("green", "green"), "emerald": ("green", "green"), "olive": ("green", "olive"),
    "pistachio": ("green", "green"), "lime": ("green", "green"), "wasabi": ("green", "green"),
    "pink": ("red/pink", "pink"), "rose quartz": ("red/pink", "pink"), "blossom": ("red/pink", "pink"),
    "peony": ("red/pink", "pink"), "petal": ("red/pink", "pink"), "dragonfruit": ("red/pink", "pink"),
    "cherry": ("red/pink", "burgundy"), "rouge": ("red/pink", "red"), "tomato": ("red/pink", "red"),
    "red": ("red/pink", "red"), "coral": ("red/pink", "coral"),
    "purple": ("purple", "purple"), "orchid": ("purple", "purple"), "amethyst": ("purple", "purple"),
    "lilac": ("purple", "lavender"), "lavender": ("purple", "lavender"), "mauve": ("purple", "purple"),
    "plum": ("purple", "purple"), "iris": ("purple", "purple"),
    "gold": ("yellow/gold", "gold"), "yellow": ("yellow/gold", "yellow"), "butter": ("yellow/gold", "yellow"),
    "orange": ("orange", "orange"),
}


def calpak_color_name(value: str) -> tuple[str, str]:
    """Reduce CALPAK's descriptive variant colors to the shared family/shade vocabulary."""
    normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    for alias in sorted(CALPAK_COLOR_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return CALPAK_COLOR_ALIASES[alias]
    return "multi", "multi"


COLOR_LOOKUPS = {
    "nordstrom_color_codes": nordstrom_color,
    "calpak_color_names": calpak_color_name,
}


def normalize_color_word(word: str | None) -> tuple[str, frozenset[str] | None] | None:
    if not word:
        return None
    return COLOR_WORDS.get(word.strip().lower())
