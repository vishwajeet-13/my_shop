import frappe

from my_shop.payments import require

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/khata"
		raise frappe.Redirect
	require("Sales Invoice")

	context.csrf_token = frappe.sessions.get_csrf_token()
	settings = frappe.get_cached_doc("Shop Voice Settings")
	context.shop_name = settings.shop_name or "My Shop"
	return context
