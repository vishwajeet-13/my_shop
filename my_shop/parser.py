"""Turn a spoken order like "5 nut bolt 3 screw" into (qty, item phrase) pairs
and match those phrases against the shop's Item list."""

import re
from difflib import SequenceMatcher

import frappe

NUM_WORDS = {
	"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
	"eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
	"fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
	"nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
	"sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
	"a": 1, "an": 1,
	# romanised hindi, which is how shops actually talk
	"ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "panch": 5,
	"paanch": 5, "chhe": 6, "che": 6, "chah": 6, "saat": 7, "sat": 7, "aath": 8,
	"ath": 8, "nau": 9, "das": 10, "dus": 10, "gyarah": 11, "barah": 12,
	"terah": 13, "chaudah": 14, "pandrah": 15, "solah": 16, "satrah": 17,
	"atharah": 18, "unnis": 19, "bees": 20, "tees": 30, "chalis": 40, "pachas": 50,
	"sau": 100,
	"aadha": 0.5, "adha": 0.5, "half": 0.5, "dedh": 1.5, "derh": 1.5,
	"dhai": 2.5, "dhaai": 2.5, "paav": 0.25, "pav": 0.25, "pao": 0.25, "quarter": 0.25,
	"dozen": 12, "darjan": 12,
}

# "saade teen" is 3.5; "sawa kilo" alone is 1.25
BUMPS = {"sawa": 0.25, "saade": 0.5, "sade": 0.5, "paune": -0.25}

RATE_WORDS = {"wala", "wali", "wale", "waala", "waali", "waale", "rupay", "rupaye", "rupee", "rupees", "rs"}

# words that carry no meaning for matching
STOPWORDS = {
	"and", "aur", "plus", "then", "also", "add", "please", "ka", "ke", "ki",
	"or", "with", "the", "of", "chahiye", "dena", "de", "dedo", "bhi",
} | RATE_WORDS

# unit words stripped from the front of an item phrase
UNIT_WORDS = {
	"kg", "kilo", "kilos", "kilogram", "gram", "grams", "gm", "piece", "pieces",
	"pcs", "pc", "nos", "no", "meter", "meters", "metre", "metres", "mtr", "feet",
	"foot", "ft", "inch", "inches", "packet", "packets", "pkt", "box", "boxes",
	"unit", "units", "set", "sets", "bundle", "bundles", "roll", "rolls",
	"m", "mm", "cm", "mtrs", "kgs", "litre", "litres", "ltr",
}

GLUED_QTY_UNITS = {"kg", "kgs", "kilo", "l", "ltr", "litre", "litres"}

MATCH_THRESHOLD = 0.34
SUGGEST_THRESHOLD = 0.12


def _normalise(text: str) -> str:
	text = (text or "").lower()
	text = re.sub(r"[^a-z0-9\s.]", " ", text)
	return re.sub(r"\s+", " ", text).strip()


def _as_number(token: str):
	"""Return the numeric value of a token, or None if it is not a number."""
	if re.fullmatch(r"\d+(\.\d+)?", token):
		return float(token) if "." in token else int(token)
	return NUM_WORDS.get(token)


def _unglue(token: str) -> list[str]:
	"""Split "2kg" into "2", "kg". Sizes like "10mm" stay whole."""
	match = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]+)", token)
	return [match[1], match[2]] if match and match[2] in GLUED_QTY_UNITS else [token]


def _combine(previous: int, current: int) -> int:
	"""Fold two adjacent numbers. "twenty five" is 25, "two dozen" is 24."""
	if previous >= 20 and previous % 10 == 0 and current < 10:
		return previous + current
	return previous * current


def parse_transcript(transcript: str) -> list[dict]:
	"""Split a spoken order into [{"qty": 5, "phrase": "nut bolt"}, ...].

	A new line item starts every time a number appears after some item words.
	Anything spoken before the first number is ignored, unless a price was spoken.
	"maggi 14 wala" adds "rate": 14 and means qty 1 when no quantity is said.
	"""
	tokens = [part for token in _normalise(transcript).split() for part in _unglue(token)]
	segments = []
	qty = None
	bump = 0
	rate = None
	words = []

	def close():
		phrase = " ".join(w for w in words if w not in STOPWORDS)
		while True:
			parts = phrase.split(" ", 1)
			if len(parts) == 2 and parts[0] in UNIT_WORDS:
				phrase = parts[1]
			else:
				break
		count = qty or (1 if rate else None)
		if count and phrase:
			segments.append({"qty": count, "phrase": phrase, **({"rate": rate} if rate else {})})

	for index, token in enumerate(tokens):
		value = _as_number(token)
		if value is not None and index + 1 < len(tokens) and tokens[index + 1] in RATE_WORDS:
			rate = value
			if words:
				close()
				qty, words, bump, rate = None, [], 0, None
		elif value is not None:
			if qty is not None and not words:
				# two numbers in a row, e.g. "twenty five" or "two dozen"
				qty = _combine(qty, value)
				continue
			close()
			qty, words, bump, rate = value + bump, [], 0, None
		elif token in BUMPS:
			close()
			qty, words, bump, rate = None, [], BUMPS[token], None
		elif token in STOPWORDS:
			continue
		else:
			if bump:
				qty, bump = 1 + bump, 0
			words.append(token)

	close()
	return segments


def _score(phrase: str, candidate: str) -> float:
	"""Blend token overlap with fuzzy string similarity."""
	candidate = _normalise(candidate)
	if not candidate:
		return 0.0

	phrase_tokens = set(phrase.split())
	candidate_tokens = set(candidate.split())
	if not phrase_tokens:
		return 0.0

	# a phrase token counts if it appears whole, or as a prefix of a longer word
	hits = sum(
		1 for pt in phrase_tokens
		if pt in candidate_tokens or any(ct.startswith(pt) for ct in candidate_tokens)
	)
	overlap = hits / len(phrase_tokens)
	fuzzy = SequenceMatcher(None, phrase, candidate).ratio()
	return 0.7 * overlap + 0.3 * fuzzy


def get_shop_items(item_group: str | None = None) -> list[dict]:
	filters = {"disabled": 0, "is_sales_item": 1}
	if item_group:
		filters["item_group"] = item_group
	return frappe.get_all(
		"Item",
		filters=filters,
		fields=["name", "item_name", "description", "stock_uom", "item_group"],
		limit_page_length=0,
	)


def _ranked(phrase: str, items: list[dict]) -> list[tuple[float, dict]]:
	scored = [
		(max(
			_score(phrase, text)
			for text in (item.get("item_name") or "", item.get("name") or "", *(item.get("description") or "").split(","))
		), item)
		for item in items
	]
	return sorted(scored, key=lambda pair: pair[0], reverse=True)


def match_item(phrase: str, items: list[dict]) -> dict | None:
	"""Best matching item for a spoken phrase, or None if nothing is close."""
	ranked = _ranked(phrase, items)
	if not ranked or ranked[0][0] < MATCH_THRESHOLD:
		return None
	best_score, best = ranked[0]
	return {
		"item_code": best["name"],
		"item_name": best["item_name"],
		"uom": best["stock_uom"],
		"score": round(best_score, 3),
	}


def suggest_items(phrase: str, items: list[dict], limit: int = 3) -> list[dict]:
	return [
		{"item_code": item["name"], "item_name": item["item_name"]}
		for score, item in _ranked(phrase, items)[:limit]
		if score >= SUGGEST_THRESHOLD
	]


def parse_and_match(transcript: str, item_group: str | None = None) -> dict:
	"""Full pipeline: transcript in, matched rows plus anything we could not find."""
	items = get_shop_items(item_group)
	rows, unmatched = [], []

	for segment in parse_transcript(transcript):
		match = match_item(segment["phrase"], items)
		if match:
			rows.append({**match, "qty": segment["qty"], "heard": segment["phrase"], "rate": segment.get("rate")})
		else:
			suggestions = [{**s, "rate": segment.get("rate")} for s in suggest_items(segment["phrase"], items)]
			unmatched.append({**segment, "suggestions": suggestions})

	return {"rows": rows, "unmatched": unmatched}
