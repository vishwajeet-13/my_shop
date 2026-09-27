import frappe

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
	context.no_cache = 1
	return context
