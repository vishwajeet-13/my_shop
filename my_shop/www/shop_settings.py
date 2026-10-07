import frappe

from my_shop.api import SPEECH_LANGUAGES
from my_shop.payments import require

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/shop-settings"
		raise frappe.Redirect
	require("Shop Voice Settings")

	settings = frappe.get_doc("Shop Voice Settings")
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.settings = settings
	context.shop_name = settings.shop_name or "My Shop"
	context.speech_languages = SPEECH_LANGUAGES
	context.can_edit = frappe.has_permission("Shop Voice Settings", "write")
	return context
