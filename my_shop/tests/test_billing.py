import frappe
from frappe.tests import IntegrationTestCase

from my_shop import api, khata


class TestBilling(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.settings = frappe.get_single("Shop Voice Settings")
		cls.item = frappe.get_all("Item", filters={"disabled": 0, "is_sales_item": 1}, pluck="name", limit=1)[0]

	def setUp(self):
		frappe.clear_cache(doctype="Shop Voice Settings")

	def _customer(self, mobile=""):
		return khata.add_customer(f"Test Buyer {frappe.generate_hash(length=6)}", mobile)["name"]

	def _bill(self, rate=100, qty=2, **kwargs):
		rows = frappe.as_json([{"item_code": self.item, "qty": qty, "rate": rate}])
		return api.create_invoice(rows, **kwargs)

	def _payment_modes(self, invoice):
		return frappe.get_all(
			"Payment Entry Reference",
			filters={"reference_name": invoice, "docstatus": 1},
			pluck="parent",
		) and frappe.get_all(
			"Payment Entry",
			filters={"name": ["in", frappe.get_all("Payment Entry Reference", filters={"reference_name": invoice}, pluck="parent")]},
			pluck="mode_of_payment",
		)

	def test_cash_bill_is_paid(self):
		bill = self._bill()
		self.assertEqual(bill["status"], "Paid")
		self.assertEqual(bill["outstanding"], 0)
		self.assertEqual(self._payment_modes(bill["name"]), ["Cash"])

	def test_upi_bill_is_paid_by_upi(self):
		bill = self._bill(payment_mode="UPI")
		self.assertEqual(bill["status"], "Paid")
		self.assertEqual(self._payment_modes(bill["name"]), ["UPI"])

	def test_udhaar_needs_a_named_customer(self):
		with self.assertRaises(frappe.ValidationError):
			self._bill(payment_mode="Udhaar")

	def test_udhaar_bill_stays_outstanding_and_shows_in_dues(self):
		customer = self._customer()
		bill = self._bill(customer=customer, payment_mode="Udhaar")
		self.assertEqual(bill["outstanding"], 200)
		self.assertIn(customer, {row["name"]: row for row in khata.dues()})

	def test_receive_payment_settles_oldest_bill_first(self):
		customer = self._customer()
		first = self._bill(customer=customer, payment_mode="Udhaar")
		second = self._bill(customer=customer, payment_mode="Udhaar", rate=50)

		result = khata.receive_payment(customer, 250)

		self.assertEqual([s["invoice"] for s in result["settled"]], [first["name"], second["name"]])
		self.assertEqual(frappe.db.get_value("Sales Invoice", first["name"], "outstanding_amount"), 0)
		self.assertEqual(frappe.db.get_value("Sales Invoice", second["name"], "outstanding_amount"), 50)
		self.assertEqual(result["due"], 50)

	def test_receive_more_than_due_is_refused(self):
		customer = self._customer()
		self._bill(customer=customer, payment_mode="Udhaar")
		with self.assertRaises(frappe.ValidationError):
			khata.receive_payment(customer, 1000)

	def test_discount_reduces_total(self):
		bill = self._bill(discount=20)
		self.assertEqual(bill["grand_total"], 180)
		self.assertEqual(bill["discount"], 20)

	def test_discount_larger_than_bill_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._bill(discount=500)

	def test_add_customer_reuses_existing_mobile(self):
		mobile = "9" + frappe.generate_hash(length=9).translate(str.maketrans("abcdef", "123456"))[:9]
		first = khata.add_customer("Asha", mobile)
		again = khata.add_customer("Asha Ben", mobile)
		self.assertEqual(first["name"], again["name"])

	def test_find_customers_by_mobile(self):
		mobile = "8" + frappe.generate_hash(length=9).translate(str.maketrans("abcdef", "123456"))[:9]
		name = khata.add_customer("Ravi", mobile)["name"]
		self.assertIn(name, [c.name for c in khata.find_customers(mobile[-6:])])

	def test_whatsapp_bill_carries_upi_link_when_pending(self):
		frappe.db.set_single_value("Shop Voice Settings", "upi_id", "myshop@upi")
		frappe.clear_cache(doctype="Shop Voice Settings")
		customer = self._customer("9812345678")
		bill = self._bill(customer=customer, payment_mode="Udhaar")
		self.assertTrue(bill["whatsapp_url"].startswith("https://wa.me/919812345678?text="))
		self.assertIn("upi%3A%2F%2Fpay", bill["whatsapp_url"])
		self.assertIn("pa=myshop%40upi", bill["upi_link"])

	def test_today_summary_counts_modes(self):
		before = khata.today_summary()
		self._bill(payment_mode="UPI")
		after = khata.today_summary()
		self.assertEqual(after["bills"], before["bills"] + 1)
		self.assertEqual(after["collected"].get("UPI", 0), before["collected"].get("UPI", 0) + 200)

	def test_settings_reject_malformed_upi_id(self):
		with self.assertRaises(frappe.ValidationError):
			api.save_app_settings("Shop", "not-a-upi-id")

	def test_settings_save_upi_id(self):
		saved = api.save_app_settings("Test Shop", "test.shop@okaxis", "hi-IN")
		self.assertEqual(saved["upi_id"], "test.shop@okaxis")
		self.assertEqual(frappe.db.get_single_value("Shop Voice Settings", "speech_lang"), "hi-IN")


class TestPermissions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.outsider = "shop-outsider@example.com"
		if not frappe.db.exists("User", cls.outsider):
			frappe.get_doc({
				"doctype": "User",
				"email": cls.outsider,
				"first_name": "Outsider",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}).insert(ignore_permissions=True)

	def setUp(self):
		frappe.set_user(self.outsider)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_outsider_cannot_read_dues(self):
		with self.assertRaises(frappe.PermissionError):
			khata.dues()

	def test_outsider_cannot_read_today_summary(self):
		with self.assertRaises(frappe.PermissionError):
			khata.today_summary()

	def test_outsider_cannot_record_payment(self):
		with self.assertRaises(frappe.PermissionError):
			khata.receive_payment("Anyone", 10)

	def test_outsider_cannot_add_item(self):
		with self.assertRaises(frappe.PermissionError):
			api.add_item(f"Sneaky {frappe.generate_hash(length=6)}", 10)

	def test_outsider_cannot_preview_or_bill(self):
		with self.assertRaises(frappe.PermissionError):
			api.preview("two hammer")
		with self.assertRaises(frappe.PermissionError):
			api.create_invoice(frappe.as_json([{"item_code": "x", "qty": 1, "rate": 1}]))

	def test_outsider_cannot_list_customer_bills(self):
		with self.assertRaises(frappe.PermissionError):
			khata.customer_bills("Anyone")

	def test_outsider_cannot_make_upi_qr(self):
		with self.assertRaises(frappe.PermissionError):
			api.upi_qr(10)


class TestPWA(IntegrationTestCase):
	def test_manifest_points_at_the_app(self):
		from my_shop.pwa import manifest

		data = manifest()
		self.assertEqual(data["start_url"], "/voice")
		self.assertEqual(data["display"], "standalone")
		self.assertIn("maskable", {icon["purpose"] for icon in data["icons"]})
