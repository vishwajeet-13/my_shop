from frappe.tests import UnitTestCase

from my_shop.parser import match_item, parse_transcript, suggest_items
from my_shop.payments import whatsapp_link


class TestParseTranscript(UnitTestCase):
	def test_english_words_and_digits(self):
		self.assertEqual(
			parse_transcript("five nut bolt and 3 wood screw"),
			[{"qty": 5, "phrase": "nut bolt"}, {"qty": 3, "phrase": "wood screw"}],
		)

	def test_hinglish_and_dozen(self):
		self.assertEqual(
			parse_transcript("paanch nut bolt do dozen washer"),
			[{"qty": 5, "phrase": "nut bolt"}, {"qty": 24, "phrase": "washer"}],
		)

	def test_compound_numbers(self):
		self.assertEqual(parse_transcript("twenty five nail"), [{"qty": 25, "phrase": "nail"}])

	def test_leading_unit_is_stripped(self):
		self.assertEqual(parse_transcript("2 kg wire nail"), [{"qty": 2, "phrase": "wire nail"}])

	def test_loose_quantities(self):
		self.assertEqual(
			parse_transcript("aadha kilo chini dedh kg dal saade teen kilo aata sawa kilo ghee 0.75 kg tel"),
			[
				{"qty": 0.5, "phrase": "chini"},
				{"qty": 1.5, "phrase": "dal"},
				{"qty": 3.5, "phrase": "aata"},
				{"qty": 1.25, "phrase": "ghee"},
				{"qty": 0.75, "phrase": "tel"},
			],
		)

	def test_unit_glued_to_number(self):
		self.assertEqual(
			parse_transcript("2kg atta, 0.5kg chini, 1ltr tel, 5 nut bolt 10mm"),
			[
				{"qty": 2, "phrase": "atta"},
				{"qty": 0.5, "phrase": "chini"},
				{"qty": 1, "phrase": "tel"},
				{"qty": 5, "phrase": "nut bolt 10mm"},
			],
		)

	def test_words_before_first_number_are_ignored(self):
		self.assertEqual(parse_transcript("bhaiya 1 hammer"), [{"qty": 1, "phrase": "hammer"}])


class TestMatchItem(UnitTestCase):
	items = [
		{"name": "Claw Hammer", "item_name": "Claw Hammer", "description": "", "stock_uom": "Nos"},
		{"name": "Wood Screw 2 inch", "item_name": "Wood Screw 2 inch", "description": "", "stock_uom": "Nos"},
	]

	def test_partial_phrase_matches(self):
		self.assertEqual(match_item("hammer", self.items)["item_code"], "Claw Hammer")

	def test_unknown_phrase_is_none(self):
		self.assertIsNone(match_item("bananas", self.items))

	def test_misheard_phrase_suggests_closest(self):
		self.assertEqual(suggest_items("hammar", self.items)[0]["item_code"], "Claw Hammer")


class TestWhatsappLink(UnitTestCase):
	def test_ten_digit_mobile_gets_india_code(self):
		self.assertTrue(whatsapp_link("98765 43210", "hi").startswith("https://wa.me/919876543210?text=hi"))

	def test_no_mobile_opens_contact_picker(self):
		self.assertEqual(whatsapp_link(None, "a b"), "https://wa.me/?text=a%20b")


class TestOfflineParserParity(UnitTestCase):
	"""public/js/offline.js re-implements the parser for offline billing and must agree with it."""

	transcripts = [
		"five nut bolt and 3 wood screw",
		"paanch nut bolt do dozen washer",
		"twenty five nail",
		"2 kg wire nail",
		"bhaiya 1 hammer",
		"teen claw hammer aur ek wood screw 2 inch",
		"4 bananas and 2 hammer",
		"aadha kilo wire nail paune do kg washer sawa hammer 1.5 kg wire nail",
		"2kg wire nail, 0.5kg washer, 3 nut bolt m8",
		"",
	]
	items = TestMatchItem.items + [
		{"name": "Wire Nail", "item_name": "Wire Nail", "description": "1 kg pack", "stock_uom": "Kg"},
		{"name": "Nut Bolt M8", "item_name": "Nut Bolt M8", "description": "", "stock_uom": "Nos"},
		{"name": "Washer", "item_name": "Washer", "description": "steel washer", "stock_uom": "Nos"},
	]

	def test_js_parser_matches_python(self):
		import json
		import shutil
		import subprocess
		from pathlib import Path

		node = shutil.which("node")
		if not node:
			self.skipTest("node is not installed")

		script = Path(__file__).parents[1] / "public" / "js" / "offline.js"
		runner = (
			"const o = require(process.argv[1]);"
			"const {transcripts, items} = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
			"console.log(JSON.stringify(transcripts.map((t) => ({"
			"segments: o.parseTranscript(t),"
			"matches: o.parseTranscript(t).map((s) => o.matchItem(s.phrase, items))}))));"
		)
		out = subprocess.run(
			[node, "-e", runner, str(script)],
			input=json.dumps({"transcripts": self.transcripts, "items": self.items}),
			capture_output=True, text=True, check=True,
		)
		expected = [
			{
				"segments": parse_transcript(t),
				"matches": [match_item(s["phrase"], self.items) for s in parse_transcript(t)],
			}
			for t in self.transcripts
		]
		self.assertEqual(json.loads(out.stdout), expected)
