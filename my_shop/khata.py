import frappe
from frappe import _
from frappe.query_builder.functions import Count, Min, Sum
from frappe.utils import flt, fmt_money, getdate, nowdate

from my_shop.payments import CASH, PAYMENT_MODES, UDHAAR, record_payment, upi_link, whatsapp_link


def _settings():
	return frappe.get_cached_doc("Shop Voice Settings")


@frappe.whitelist()
def find_customers(query: str = ""):
	query = (query or "").strip()
	filters = {"disabled": 0}
	or_filters = None
	if query:
		or_filters = {"customer_name": ["like", f"%{query}%"], "mobile_no": ["like", f"%{query}%"]}
	customers = frappe.get_all(
		"Customer",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "customer_name", "mobile_no"],
		order_by="modified desc",
		limit=8,
	)
	dues = _outstanding_by_customer([c.name for c in customers])
	for customer in customers:
		customer["due"] = dues.get(customer.name, 0)
	return customers


@frappe.whitelist()
def add_customer(customer_name: str, mobile_no: str = ""):
	customer_name = (customer_name or "").strip()
	mobile_no = "".join(ch for ch in (mobile_no or "") if ch.isdigit() or ch == "+")
	if not customer_name:
		frappe.throw(_("Customer needs a name"))

	if mobile_no:
		existing = frappe.db.get_value("Customer", {"mobile_no": mobile_no}, "name")
		if existing:
			return _customer_card(existing)

	customer = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": customer_name,
		"customer_type": "Individual",
		"customer_group": frappe.db.get_single_value("Selling Settings", "customer_group")
			or frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
		"territory": frappe.db.get_single_value("Selling Settings", "territory")
			or frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		"mobile_no": mobile_no or None,
	}).insert()
	return _customer_card(customer.name)


def _customer_card(name: str) -> dict:
	card = frappe.db.get_value("Customer", name, ["name", "customer_name", "mobile_no"], as_dict=True)
	card["due"] = _outstanding_by_customer([name]).get(name, 0)
	return card


def _outstanding_by_customer(customers: list | None = None) -> dict:
	invoice = frappe.qb.DocType("Sales Invoice")
	query = (
		frappe.qb.from_(invoice)
		.select(invoice.customer, Sum(invoice.outstanding_amount).as_("due"))
		.where((invoice.docstatus == 1) & (invoice.outstanding_amount > 0))
		.where(invoice.company == _settings().company)
		.groupby(invoice.customer)
	)
	if customers is not None:
		if not customers:
			return {}
		query = query.where(invoice.customer.isin(customers))
	return {row.customer: flt(row.due) for row in query.run(as_dict=True)}


@frappe.whitelist()
def dues():
	outstanding = _outstanding_by_customer()
	if not outstanding:
		return []
	details = frappe.get_all(
		"Customer",
		filters={"name": ["in", list(outstanding)]},
		fields=["name", "customer_name", "mobile_no"],
	)
	invoice = frappe.qb.DocType("Sales Invoice")
	oldest = dict(
		frappe.qb.from_(invoice)
		.select(invoice.customer, Min(invoice.posting_date))
		.where((invoice.docstatus == 1) & (invoice.outstanding_amount > 0))
		.where(invoice.customer.isin(list(outstanding)))
		.groupby(invoice.customer)
		.run()
	)
	today = getdate(nowdate())
	rows = []
	for customer in details:
		due = outstanding[customer.name]
		since = oldest.get(customer.name)
		rows.append({
			**customer,
			"due": due,
			"days": (today - getdate(since)).days if since else 0,
			"reminder_url": whatsapp_link(customer.mobile_no, _reminder_text(customer.customer_name, due)),
		})
	return sorted(rows, key=lambda r: r["due"], reverse=True)


def _reminder_text(customer_name: str, due: float) -> str:
	settings = _settings()
	shop = settings.shop_name or "our shop"
	text = f"Hello {customer_name}, your outstanding balance at {shop} is {_money(due)}."
	link = upi_link(due, f"Balance {customer_name}")
	if link:
		text += f"\nPay by UPI: {link}"
	return text + "\nThank you!"


def _money(amount: float) -> str:
	return fmt_money(amount, precision=2, currency="INR")


@frappe.whitelist()
def customer_bills(customer: str):
	return frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1},
		fields=["name", "posting_date", "grand_total", "outstanding_amount", "status"],
		order_by="posting_date desc, creation desc",
		limit=20,
	)


@frappe.whitelist()
def receive_payment(customer: str, amount: float, mode: str = CASH):
	amount = flt(amount, 2)
	if amount <= 0:
		frappe.throw(_("Enter the amount received"))
	if mode not in PAYMENT_MODES or mode == UDHAAR:
		frappe.throw(_("Payment must be Cash or UPI"))

	open_bills = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1, "outstanding_amount": [">", 0], "company": _settings().company},
		fields=["name", "outstanding_amount"],
		order_by="posting_date asc, creation asc",
	)
	total_due = sum(flt(b.outstanding_amount) for b in open_bills)
	if amount > flt(total_due, 2):
		frappe.throw(_("{0} owes only {1}").format(customer, _money(total_due)))

	remaining, settled = amount, []
	for bill in open_bills:
		if remaining <= 0:
			break
		part = min(remaining, flt(bill.outstanding_amount))
		record_payment(bill.name, mode, part)
		settled.append({"invoice": bill.name, "amount": part})
		remaining = flt(remaining - part, 2)

	return {"settled": settled, "due": _outstanding_by_customer([customer]).get(customer, 0)}


@frappe.whitelist()
def today_summary():
	settings = _settings()
	today = nowdate()
	invoice = frappe.qb.DocType("Sales Invoice")
	sales = (
		frappe.qb.from_(invoice)
		.select(Count(invoice.name).as_("bills"), Sum(invoice.grand_total).as_("total"),
			Sum(invoice.outstanding_amount).as_("on_credit"))
		.where((invoice.docstatus == 1) & (invoice.posting_date == today) & (invoice.company == settings.company))
		.where(invoice.is_return == 0)
		.run(as_dict=True)[0]
	)

	payment = frappe.qb.DocType("Payment Entry")
	collected = (
		frappe.qb.from_(payment)
		.select(payment.mode_of_payment, Sum(payment.paid_amount).as_("amount"))
		.where((payment.docstatus == 1) & (payment.posting_date == today) & (payment.company == settings.company))
		.where(payment.payment_type == "Receive")
		.groupby(payment.mode_of_payment)
		.run(as_dict=True)
	)

	recent = frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1, "posting_date": today, "company": settings.company},
		fields=["name", "customer_name", "grand_total", "outstanding_amount", "status"],
		order_by="creation desc",
		limit=10,
	)

	return {
		"bills": sales.bills or 0,
		"total": flt(sales.total),
		"on_credit": flt(sales.on_credit),
		"collected": {row.mode_of_payment or CASH: flt(row.amount) for row in collected},
		"recent": recent,
	}
