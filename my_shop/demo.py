"""One-shot setup for the voice billing demo: a company, a few hardware items
with prices, a walk-in customer, and the Shop Voice Settings filled in.

Run with:  bench --site myshop.local execute my_shop.demo.seed
"""

import frappe
from frappe.utils import getdate, nowdate

from my_shop.payments import CASH, UPI, ensure_mode_of_payment

COMPANY = "My Shop"
ABBR = "MS"
ITEM_GROUP = "Hardware"
CUSTOMER = "Walk In Customer"

# item name, uom, rate. These are the words a hardware shop actually says.
ITEMS = [
	("Nut Bolt 10mm", "Nos", 12),
	("Wood Screw 2 inch", "Nos", 3),
	("Washer Steel", "Nos", 2),
	("Claw Hammer", "Nos", 340),
	("GI Pipe Half Inch", "Meter", 95),
	("Elbow Joint 15mm", "Nos", 28),
	("Door Hinge 4 inch", "Nos", 55),
	("Wire Nail 2 inch", "Kg", 88),
	("Paint Brush 3 inch", "Nos", 120),
	("Measuring Tape 5m", "Nos", 210),
]


def _ensure_erpnext_fixtures():
	"""ERPNext ships warehouse types, groups and UOMs via the setup wizard.
	We install a site headlessly, so we call that installer directly."""
	from erpnext.setup.setup_wizard.operations.install_fixtures import install

	if frappe.db.exists("Warehouse Type", "Transit"):
		return
	install("India")
	frappe.db.commit()


def _set_global_defaults():
	defaults = frappe.get_single("Global Defaults")
	defaults.default_company = COMPANY
	defaults.default_currency = "INR"
	defaults.country = "India"
	defaults.save(ignore_permissions=True)
	frappe.db.set_default("company", COMPANY)
	frappe.db.set_default("currency", "INR")


def _ensure_fiscal_year():
	today = getdate(nowdate())
	existing = frappe.db.exists(
		"Fiscal Year", {"year_start_date": ["<=", today], "year_end_date": [">=", today]}
	)
	if existing:
		return

	start_year = today.year if today.month >= 4 else today.year - 1
	frappe.get_doc({
		"doctype": "Fiscal Year",
		"year": f"{start_year}-{start_year + 1}",
		"year_start_date": f"{start_year}-04-01",
		"year_end_date": f"{start_year + 1}-03-31",
	}).insert(ignore_permissions=True)


def _ensure_company():
	if frappe.db.exists("Company", COMPANY):
		return COMPANY

	frappe.get_doc({
		"doctype": "Company",
		"company_name": COMPANY,
		"abbr": ABBR,
		"default_currency": "INR",
		"country": "India",
		"chart_of_accounts": "Standard",
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return COMPANY


def _ensure_item_group():
	if frappe.db.exists("Item Group", ITEM_GROUP):
		return
	frappe.get_doc({
		"doctype": "Item Group",
		"item_group_name": ITEM_GROUP,
		"parent_item_group": "All Item Groups",
		"is_group": 0,
	}).insert(ignore_permissions=True)


def _ensure_price_lists():
	"""A fresh headless site has no price lists, so items have nothing to price against."""
	for name, selling, buying in (("Standard Selling", 1, 0), ("Standard Buying", 0, 1)):
		if frappe.db.exists("Price List", name):
			continue
		frappe.get_doc({
			"doctype": "Price List",
			"price_list_name": name,
			"currency": "INR",
			"selling": selling,
			"buying": buying,
			"enabled": 1,
		}).insert(ignore_permissions=True)


def _ensure_uom(uom):
	if not frappe.db.exists("UOM", uom):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)


def _ensure_items():
	price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
	for item_name, uom, rate in ITEMS:
		_ensure_uom(uom)
		if not frappe.db.exists("Item", item_name):
			frappe.get_doc({
				"doctype": "Item",
				"item_code": item_name,
				"item_name": item_name,
				"description": item_name,
				"item_group": ITEM_GROUP,
				"stock_uom": uom,
				"is_stock_item": 0,   # keeps the demo free of stock ledger setup
				"is_sales_item": 1,
			}).insert(ignore_permissions=True)

		if price_list and not frappe.db.exists(
			"Item Price", {"item_code": item_name, "price_list": price_list}
		):
			frappe.get_doc({
				"doctype": "Item Price",
				"item_code": item_name,
				"price_list": price_list,
				"price_list_rate": rate,
			}).insert(ignore_permissions=True)


def _ensure_selling_settings():
	price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
	if not price_list:
		return
	selling = frappe.get_single("Selling Settings")
	selling.selling_price_list = price_list
	selling.save(ignore_permissions=True)


def _ensure_customer():
	if frappe.db.exists("Customer", CUSTOMER):
		return
	frappe.get_doc({
		"doctype": "Customer",
		"customer_name": CUSTOMER,
		"customer_type": "Individual",
		"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
		"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
	}).insert(ignore_permissions=True)


def _ensure_settings():
	settings = frappe.get_single("Shop Voice Settings")
	settings.shop_name = COMPANY
	settings.company = COMPANY
	settings.default_customer = CUSTOMER
	settings.item_group = ITEM_GROUP
	settings.speech_lang = "en-IN"
	settings.save(ignore_permissions=True)


def seed():
	_ensure_erpnext_fixtures()
	_ensure_fiscal_year()
	_ensure_company()
	_set_global_defaults()
	_ensure_item_group()
	_ensure_price_lists()
	_ensure_items()
	_ensure_selling_settings()
	_ensure_customer()
	_ensure_settings()
	for mode in (CASH, UPI):
		ensure_mode_of_payment(mode)

	frappe.db.set_single_value("System Settings", "setup_complete", 1)
	frappe.db.commit()

	print(f"Seeded {len(ITEMS)} items for {COMPANY}. Open /voice and /khata")
