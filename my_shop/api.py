import re

import frappe
from frappe import _
from frappe.utils import flt

from my_shop.parser import parse_and_match
from my_shop.payments import CASH, PAYMENT_MODES, UDHAAR, record_payment, require, upi_link, upi_qr_svg, whatsapp_link

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
	require("Sales Invoice", "create")
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
	require("Sales Invoice", "create")
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


@frappe.whitelist()
def create_invoice(rows: str, customer: str | None = None, payment_mode: str = CASH, discount: float = 0):
	"""Create the Sales Invoice from the rows as edited on the billing page.

	Quantities and rates come from the grid, not from the transcript, so whatever
	the shopkeeper corrected on screen is exactly what gets billed.
	"""
	require("Sales Invoice", "submit")
	rows = frappe.parse_json(rows)
	if not rows:
		frappe.throw(_("Add at least one item"))
	if payment_mode not in PAYMENT_MODES:
		frappe.throw(_("Unknown payment mode {0}").format(payment_mode))

	settings = _settings()
	customer = customer or settings.default_customer
	if payment_mode == UDHAAR and customer == settings.default_customer:
		frappe.throw(_("Select a customer to bill on credit"))

	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.company = settings.company
	invoice.selling_price_list = _selling_price_list()
	if settings.taxes_and_charges:
		invoice.taxes_and_charges = settings.taxes_and_charges

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

	discount = flt(discount, 2)
	if discount < 0:
		frappe.throw(_("Discount cannot be negative"))
	if discount:
		invoice.apply_discount_on = "Grand Total"
		invoice.discount_amount = discount

	invoice.set_missing_values()
	invoice.insert()
	if invoice.grand_total < 0:
		frappe.throw(_("Discount is more than the bill"))
	invoice.submit()  # a spoken order is a real sale, not a draft awaiting review
	if payment_mode != UDHAAR and invoice.outstanding_amount > 0:
		record_payment(invoice.name, payment_mode)

	return bill_summary(invoice.name)


def bill_summary(name: str) -> dict:
	invoice = frappe.get_doc("Sales Invoice", name)
	mobile = frappe.db.get_value("Customer", invoice.customer, "mobile_no")
	return {
		"name": invoice.name,
		"url": f"/app/sales-invoice/{invoice.name}",
		"print_url": f"/invoice?name={invoice.name}",
		"customer": invoice.customer,
		"customer_name": invoice.customer_name,
		"grand_total": invoice.grand_total,
		"discount": invoice.discount_amount,
		"taxes": invoice.total_taxes_and_charges,
		"outstanding": invoice.outstanding_amount,
		"status": invoice.status,
		"upi_link": upi_link(invoice.outstanding_amount, invoice.name) if invoice.outstanding_amount else None,
		"whatsapp_url": whatsapp_link(mobile, bill_text(invoice)),
		"rows": [
			{"item_code": i.item_code, "item_name": i.item_name, "qty": i.qty,
			 "rate": i.rate, "amount": i.amount}
			for i in invoice.items
		],
	}


def bill_text(invoice) -> str:
	settings = _settings()
	lines = [f"*{settings.shop_name or invoice.company}*", f"Bill {invoice.name} · {frappe.utils.formatdate(invoice.posting_date)}", ""]
	for item in invoice.items:
		lines.append(f"{frappe.utils.flt(item.qty):g} × {item.item_name} = {_money(item.amount)}")
	if invoice.discount_amount:
		lines.append(f"Discount: -{_money(invoice.discount_amount)}")
	if invoice.total_taxes_and_charges:
		lines.append(f"Tax: {_money(invoice.total_taxes_and_charges)}")
	lines += ["", f"*Total: {_money(invoice.grand_total)}*"]
	if invoice.outstanding_amount > 0:
		lines.append(f"Pending: {_money(invoice.outstanding_amount)}")
		link = upi_link(invoice.outstanding_amount, invoice.name)
		if link:
			lines.append(f"Pay by UPI: {link}")
	else:
		lines.append("Paid. Thank you!")
	return "\n".join(lines)


def _money(amount: float) -> str:
	return frappe.utils.fmt_money(amount, precision=2, currency="INR")


@frappe.whitelist()
def upi_qr(amount: float, note: str = ""):
	require("Sales Invoice")
	link = upi_link(amount, note or "Bill")
	return {"link": link, "svg": upi_qr_svg(link)} if link else None


SPEECH_LANGUAGES = ("en-IN", "hi-IN", "en-US", "en-GB")


@frappe.whitelist()
def save_app_settings(shop_name: str, upi_id: str = "", speech_lang: str = "en-IN"):
	require("Shop Voice Settings", "write")
	if speech_lang not in SPEECH_LANGUAGES:
		frappe.throw(_("Unknown speech language {0}").format(speech_lang))
	upi_id = (upi_id or "").strip()
	if upi_id and not re.fullmatch(r"[\w.\-]{2,256}@[a-zA-Z][\w.\-]{1,64}", upi_id):
		frappe.throw(_("UPI ID looks wrong. It should look like name@bank"))

	settings = frappe.get_doc("Shop Voice Settings")
	settings.shop_name = (shop_name or "").strip() or settings.shop_name
	settings.upi_id = upi_id
	settings.speech_lang = speech_lang
	settings.save()
	return {"shop_name": settings.shop_name, "upi_id": settings.upi_id, "speech_lang": settings.speech_lang}
