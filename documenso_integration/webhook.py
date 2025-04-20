import frappe
import os
import json
from frappe import _

@frappe.whitelist(allow_guest=True)
def incoming_webhook():
    # Get the webhook key from the environment variable
    expected_key = os.getenv("DOCUMENSO_WEBHOOK_KEY")
    received_key = frappe.request.args.get("key")

    # Log the keys for debugging
    frappe.logger("webhook").info(f"Expected Key: {expected_key}")
    frappe.logger("webhook").info(f"Received Key: {received_key}")

    # Check if the keys match, otherwise throw an error
    if expected_key and received_key != expected_key:
        frappe.throw(_("Unauthorized request"), frappe.PermissionError)

    # Capture the webhook payload
    payload = frappe.request.get_json()
    if not payload:
        frappe.throw(_("Invalid or missing JSON payload"), frappe.BadRequest)

    # Log the payload to verify
    frappe.logger("webhook").info(f"Incoming Documenso Webhook: {json.dumps(payload)}")

    # Extract the necessary information from the payload
    event = payload.get('event')
    document_data = payload.get('payload', {})
    document_id = document_data.get('id')
    status = document_data.get('status')

    if not document_id or not status:
        frappe.throw(_("Missing required data in payload"))

    # Get the document to update
    try:
        doc = frappe.get_doc("Contract", document_id)
    except frappe.DoesNotExistError:
        frappe.throw(_("Document not found"))

    # Handle different events and update the workflow state accordingly
    if event == "document.signed" and status == "COMPLETED":
        doc.workflow_state = "Active"
        frappe.logger("webhook").info(f"Document {document_id} signed and workflow state updated to 'Active'")

    elif event == "document.rejected" and status == "PENDING":
        doc.workflow_state = "Rejected"
        frappe.logger("webhook").info(f"Document {document_id} rejected and workflow state updated to 'Rejected'")

    elif event == "document.cancelled" and status == "PENDING":
        doc.workflow_state = "Rejected"
        frappe.logger("webhook").info(f"Document {document_id} canceled and workflow state updated to 'Canceled'")

    else:
        frappe.logger("webhook").warning(f"Unhandled event or status for document {document_id}: event={event}, status={status}")
        frappe.throw(_("Unhandled event or status"))

    # Save the document with the updated workflow state
    doc.save()

    # Optionally, you can log the updated workflow state
    frappe.logger("webhook").info(f"Document {document_id} workflow state successfully updated to {doc.workflow_state}")

    return {"status": "success", "message": "Webhook processed and document updated"}
