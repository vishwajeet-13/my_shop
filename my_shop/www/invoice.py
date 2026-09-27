import frappe

from my_shop.payments import upi_link, upi_qr_svg

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to=/invoice?name={frappe.form_dict.name}"
		raise frappe.Redirect

	name = frappe.form_dict.name
	if not name:
		frappe.throw("Invoice name required", frappe.DoesNotExistError)

	invoice = frappe.get_doc("Sales Invoice", name)
	invoice.check_permission("read")

	settings = frappe.get_cached_doc("Shop Voice Settings")
	shop_name = settings.shop_name or invoice.company or "Shop"

	context.invoice = invoice
	context.shop_name = shop_name
	context.mark = shop_name[0].upper()
	context.is_paid = invoice.status == "Paid"
	link = upi_link(invoice.outstanding_amount, invoice.name) if invoice.outstanding_amount > 0 else None
	context.upi_qr = upi_qr_svg(link) if link else None
	context.no_cache = 1
	return context
