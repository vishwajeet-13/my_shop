from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CLIENT_REF = "my_shop_client_ref"

CUSTOM_FIELDS = {
	"Sales Invoice": [
		{
			"fieldname": CLIENT_REF,
			"label": "Offline Bill Ref",
			"fieldtype": "Data",
			"insert_after": "customer",
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
			"unique": 1,
			"print_hide": 1,
		}
	]
}


def after_install():
	create_custom_fields(CUSTOM_FIELDS, update=True)
