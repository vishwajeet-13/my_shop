from io import BytesIO
from urllib.parse import quote, urlencode

import frappe
import pyqrcode
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from frappe.utils import flt

CASH, UPI, UDHAAR = "Cash", "UPI", "Udhaar"
PAYMENT_MODES = (CASH, UPI, UDHAAR)


def require(doctype: str, ptype: str = "read"):
	frappe.has_permission(doctype, ptype, throw=True)


def ensure_mode_of_payment(mode: str):
	if not frappe.db.exists("Mode of Payment", mode):
		frappe.get_doc({
			"doctype": "Mode of Payment",
			"mode_of_payment": mode,
			"type": "Cash" if mode == CASH else "Bank",
		}).insert(ignore_permissions=True)


def _mode_account(mode: str, company: str) -> str | None:
	return frappe.db.get_value(
		"Mode of Payment Account", {"parent": mode, "company": company}, "default_account"
	)


def record_payment(invoice_name: str, mode: str, amount: float | None = None, posting_date=None):
	ensure_mode_of_payment(mode)
	payment = get_payment_entry("Sales Invoice", invoice_name, party_amount=amount)
	payment.mode_of_payment = mode
	if posting_date:
		payment.posting_date = posting_date
	account = _mode_account(mode, payment.company)
	if account and account != payment.paid_to:
		payment.paid_to = account
		payment.paid_to_account_currency = frappe.get_cached_value("Account", account, "account_currency")
	payment.reference_no = invoice_name
	payment.reference_date = payment.posting_date
	payment.insert(ignore_permissions=True)
	payment.submit()
	return payment


def upi_link(amount: float, note: str) -> str | None:
	settings = frappe.get_cached_doc("Shop Voice Settings")
	if not settings.upi_id:
		return None
	params = {
		"pa": settings.upi_id,
		"pn": settings.shop_name or "Shop",
		"am": f"{flt(amount):.2f}",
		"cu": "INR",
		"tn": note,
	}
	return "upi://pay?" + urlencode(params, quote_via=quote)


def upi_qr_svg(link: str) -> str:
	buffer = BytesIO()
	pyqrcode.create(link, error="M").svg(buffer, scale=4, quiet_zone=2, xmldecl=False)
	return buffer.getvalue().decode()


def whatsapp_link(mobile: str | None, text: str) -> str:
	digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
	if len(digits) == 10:
		digits = "91" + digits
	return f"https://wa.me/{digits}?text={quote(text, safe="")}" if digits else f"https://wa.me/?text={quote(text, safe="")}"
