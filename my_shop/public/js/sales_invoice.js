// Voice billing sends the shopkeeper into the invoice form to fix a qty or rate.
// Without this they have no way back to the mic except the browser back button.
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		frm.add_custom_button(__("Back to Billing"), () => {
			window.location.href = "/voice";
		}).addClass("btn-primary");
	},
});
