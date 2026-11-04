import frappe
from erpnext import get_default_company
from frappe.integrations.utils import make_get_request
from frappe.model.document import Document

WALK_IN_CUSTOMER = "Walk-in Customer"


class ShopVoiceSettings(Document):
	def onload(self):
		if not frappe.conf.openrouter_key:
			return
		try:
			key = make_get_request(
				"https://openrouter.ai/api/v1/key",
				headers={"Authorization": f"Bearer {frappe.conf.openrouter_key}"},
				timeout=5,
			)["data"]
		except Exception:
			frappe.log_error("OpenRouter usage check failed")
			return
		self.usage_daily, self.usage_weekly, self.usage_monthly, self.usage_total = (
			key["usage_daily"], key["usage_weekly"], key["usage_monthly"], key["usage"]
		)

	def validate(self):
		self.company = self.company or get_default_company()
		self.default_customer = self.default_customer or walk_in_customer()


def walk_in_customer():
	if not frappe.db.exists("Customer", WALK_IN_CUSTOMER):
		frappe.get_doc({
			"doctype": "Customer",
			"customer_name": WALK_IN_CUSTOMER,
			"customer_type": "Individual",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		}).insert(ignore_permissions=True)
	return WALK_IN_CUSTOMER
