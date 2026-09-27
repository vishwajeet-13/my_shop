import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from frappe import _
from frappe.utils import flt

from my_shop.parser import parse_and_match

COMMON_UOMS = ("Nos", "Kg", "Meter", "Litre", "Packet", "Box", "Dozen")


def _settings():
	return frappe.get_cached_doc("Shop Voice Settings")


def _selling_price_list():
	"""Sales Invoice needs a price list before it can work out currency."""
	return (
		frappe.db.get_single_value("Selling Settings", "selling_price_list")
		or frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
	)


def _rates(item_codes: list) -> dict:
	price_list = _selling_price_list()
	if not (price_list and item_codes):
		return {}
	rows = frappe.get_all(
		"Item Price",
		filters={"price_list": price_list, "item_code": ["in", item_codes]},
		fields=["item_code", "price_list_rate"],
	)
	return {r.item_code: r.price_list_rate for r in rows}


@frappe.whitelist()
def preview(transcript: str):
	"""What we heard, matched against the catalogue. Creates nothing."""
	result = parse_and_match(transcript, _settings().item_group)

	rates = _rates([r["item_code"] for r in result["rows"]])
	for row in result["rows"]:
		row["rate"] = rates.get(row["item_code"], 0)

	result["uoms"] = list(COMMON_UOMS)
	result["currency"] = frappe.db.get_default("currency") or "INR"
	return result


@frappe.whitelist()
def add_item(item_name: str, rate: float = 0, uom: str = "Nos"):
	"""Create a missing item on the spot so the sale is never blocked.

	The shopkeeper types the name and rate, so nothing enters the catalogue
	without a human confirming it. Items are non-stock by design: this is a
	billing app, and a brand new item would have zero stock anyway.
	"""
	item_name = (item_name or "").strip()
	if not item_name:
		frappe.throw(_("Item needs a name"))

	settings = _settings()

	if not frappe.db.exists("UOM", uom):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)

	if not frappe.db.exists("Item", item_name):
		frappe.get_doc({
			"doctype": "Item",
			"item_code": item_name,
			"item_name": item_name,
			"description": item_name,
			"item_group": settings.item_group
				or frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": uom,
			"is_stock_item": 0,
			"is_sales_item": 1,
		}).insert(ignore_permissions=True)

	rate = frappe.utils.flt(rate)
	price_list = _selling_price_list()
	if rate and price_list and not frappe.db.exists(
		"Item Price", {"item_code": item_name, "price_list": price_list}
	):
		frappe.get_doc({
			"doctype": "Item Price",
			"item_code": item_name,
			"price_list": price_list,
			"price_list_rate": rate,
		}).insert(ignore_permissions=True)

	return {"item_code": item_name}


def _mark_paid_in_cash(invoice):
	"""A counter sale is cash in hand, not a receivable. Record the payment
	immediately so the invoice does not sit around marked Unpaid."""
	if not frappe.db.exists("Mode of Payment", "Cash"):
		return  # no Cash mode configured for this shop; leave it Unpaid

	payment = get_payment_entry(invoice.doctype, invoice.name)
	payment.mode_of_payment = "Cash"
	payment.reference_no = invoice.name
	payment.reference_date = invoice.posting_date
	payment.insert(ignore_permissions=True)
	payment.submit()


@frappe.whitelist()
def create_invoice(rows: str):
	"""Create the draft Sales Invoice from the rows as edited on the billing page.

	Quantities and rates come from the grid, not from the transcript, so whatever
	the shopkeeper corrected on screen is exactly what gets billed.
	"""
	rows = frappe.parse_json(rows)
	if not rows:
		frappe.throw(_("Add at least one item"))

	settings = _settings()
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = settings.default_customer
	invoice.company = settings.company
	invoice.selling_price_list = _selling_price_list()

	for row in rows:
		qty = flt(row.get("qty"))
		if qty <= 0:
			continue
		invoice.append("items", {
			"item_code": row["item_code"],
			"qty": qty,
			# setting both stops ERPNext refetching the list price over the edit
			"rate": flt(row.get("rate")),
			"price_list_rate": flt(row.get("rate")),
		})

	if not invoice.items:
		frappe.throw(_("Add at least one item"))

	invoice.set_missing_values()
	invoice.insert()
	invoice.submit()  # a spoken order is a real sale, not a draft awaiting review
	_mark_paid_in_cash(invoice)

	return {
		"name": invoice.name,
		"url": f"/app/sales-invoice/{invoice.name}",
		"print_url": f"/invoice?name={invoice.name}",
		"grand_total": invoice.grand_total,
		"rows": [
			{"item_code": i.item_code, "item_name": i.item_name, "qty": i.qty,
			 "rate": i.rate, "amount": i.amount}
			for i in invoice.items
		],
	}
