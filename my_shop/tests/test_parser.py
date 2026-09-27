from frappe.tests import UnitTestCase

from my_shop.parser import match_item, parse_transcript
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


class TestWhatsappLink(UnitTestCase):
	def test_ten_digit_mobile_gets_india_code(self):
		self.assertTrue(whatsapp_link("98765 43210", "hi").startswith("https://wa.me/919876543210?text=hi"))

	def test_no_mobile_opens_contact_picker(self):
		self.assertEqual(whatsapp_link(None, "a b"), "https://wa.me/?text=a%20b")
