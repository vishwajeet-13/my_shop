import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/voice"
		raise frappe.Redirect

	context.csrf_token = frappe.sessions.get_csrf_token()
	settings = frappe.get_cached_doc("Shop Voice Settings")
	context.shop_name = settings.shop_name or "My Shop"
	context.speech_lang = settings.speech_lang or "en-IN"
	return context
