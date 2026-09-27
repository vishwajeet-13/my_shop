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
	"dozen": 12, "darjan": 12,
}

# words that carry no meaning for matching
STOPWORDS = {
	"and", "aur", "plus", "then", "also", "add", "please", "ka", "ke", "ki",
	"or", "with", "the", "of", "chahiye", "dena", "de", "dedo", "bhi",
}

# unit words stripped from the front of an item phrase
UNIT_WORDS = {
	"kg", "kilo", "kilos", "kilogram", "gram", "grams", "gm", "piece", "pieces",
	"pcs", "pc", "nos", "no", "meter", "meters", "metre", "metres", "mtr", "feet",
	"foot", "ft", "inch", "inches", "packet", "packets", "pkt", "box", "boxes",
	"unit", "units", "set", "sets", "bundle", "bundles", "roll", "rolls",
	"m", "mm", "cm", "mtrs", "kgs", "litre", "litres", "ltr",
}

MATCH_THRESHOLD = 0.34


def _normalise(text: str) -> str:
	text = (text or "").lower()
	text = re.sub(r"[^a-z0-9\s.]", " ", text)
	return re.sub(r"\s+", " ", text).strip()


def _as_number(token: str):
	"""Return the numeric value of a token, or None if it is not a number."""
	if token.isdigit():
		return int(token)
	return NUM_WORDS.get(token)


def _combine(previous: int, current: int) -> int:
	"""Fold two adjacent numbers. "twenty five" is 25, "two dozen" is 24."""
	if previous >= 20 and previous % 10 == 0 and current < 10:
		return previous + current
	return previous * current


def parse_transcript(transcript: str) -> list[dict]:
	"""Split a spoken order into [{"qty": 5, "phrase": "nut bolt"}, ...].

	A new line item starts every time a number appears after some item words.
	Anything spoken before the first number is ignored.
	"""
	tokens = _normalise(transcript).split()
	segments = []
	qty = None
	words = []

	def close():
		phrase = " ".join(w for w in words if w not in STOPWORDS)
		while True:
			parts = phrase.split(" ", 1)
			if len(parts) == 2 and parts[0] in UNIT_WORDS:
				phrase = parts[1]
			else:
				break
		if qty and phrase:
			segments.append({"qty": qty, "phrase": phrase})

	for token in tokens:
		value = _as_number(token)
		if value is not None:
			if qty is not None and not words:
				# two numbers in a row, e.g. "twenty five" or "two dozen"
				qty = _combine(qty, value)
				continue
			close()
			qty, words = value, []
		elif token in STOPWORDS:
			continue
		else:
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


def match_item(phrase: str, items: list[dict]) -> dict | None:
	"""Best matching item for a spoken phrase, or None if nothing is close."""
	best, best_score = None, 0.0
	for item in items:
		score = max(
			_score(phrase, item.get("item_name") or ""),
			_score(phrase, item.get("name") or ""),
			_score(phrase, item.get("description") or ""),
		)
		if score > best_score:
			best, best_score = item, score

	if best_score < MATCH_THRESHOLD:
		return None
	return {
		"item_code": best["name"],
		"item_name": best["item_name"],
		"uom": best["stock_uom"],
		"score": round(best_score, 3),
	}


def parse_and_match(transcript: str, item_group: str | None = None) -> dict:
	"""Full pipeline: transcript in, matched rows plus anything we could not find."""
	items = get_shop_items(item_group)
	rows, unmatched = [], []

	for segment in parse_transcript(transcript):
		match = match_item(segment["phrase"], items)
		if match:
			rows.append({**match, "qty": segment["qty"], "heard": segment["phrase"]})
		else:
			unmatched.append(segment)

	return {"rows": rows, "unmatched": unmatched}
