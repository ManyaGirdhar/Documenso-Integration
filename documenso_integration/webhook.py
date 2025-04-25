import frappe
import os
import json
from frappe import _
from documenso_integration.api import download_signed_contract  


@frappe.whitelist(allow_guest=True)
def incoming_webhook():
    # Get the webhook key from the environment variable
    expected_key = os.getenv("DOCUMENSO_WEBHOOK_KEY")
    # Get received secret key from header
    received_key = frappe.request.headers.get("X-Documenso-Secret")
    # Log the keys for debugging
    frappe.log_error(f"Expected Key: {expected_key}\nReceived Key: {received_key}", "Documenso Webhook Auth")

    # Check if the keys match, otherwise throw an error
    if expected_key and received_key != expected_key:
        frappe.throw(_("Unauthorized request"), frappe.PermissionError)

    # Capture the webhook payload
    payload = frappe.request.get_json()
    if not payload:
        frappe.throw(_("Invalid or missing JSON payload"), frappe.BadRequest)

    # Log the payload to verify
    frappe.log_error(json.dumps(payload, indent=2), "Incoming Documenso Webhook")

    # Extract the necessary information from the payload
    event = payload.get('event')
    frappe.log_error(f"Event: {event}", "Documenso Webhook Event")
    document_data = payload.get('payload', {})
    frappe.log_error(f"Document Data: {json.dumps(document_data, indent=2)}", "Documenso Webhook Document Data")
    document_id = document_data.get('id')
    frappe.log_error(f"Document ID: {document_id}", "Documenso Webhook Document ID")
    status = document_data.get('status')
    frappe.log_error(f"Status: {status}", "Documenso Webhook Status")

    if not document_id or not status:
        frappe.throw(_("Missing required data in payload"))

    # Get the document to update
    try:
        doc = frappe.get_doc("Contract", {"document_id": document_id})
        frappe.log_error(f"Document found: {doc.name}", "Documenso Webhook Document Found")
    except frappe.DoesNotExistError:
        frappe.throw(_("Document not found"))

    # Handle different events and update the workflow state accordingly
    # Handle different events and update the workflow state accordingly
    if event == "DOCUMENT_COMPLETED" and status == "COMPLETED":
        frappe.db.set_value("Contract", doc.name, "workflow_state", "Active")
        frappe.log_error(f"Before Save - Workflow State: {doc.workflow_state}", "Debug Save")

        frappe.publish_realtime('workflow_state_updated', {
                'contract_name': doc.name,
                'workflow_state': doc.workflow_state
            })
        frappe.log_error(f"Real-time event published: {doc.name} updated to Active", "Documenso Webhook Publish Realtime")

        # try:
        #     doc.flags.ignore_validate = True
        #     doc.flags.ignore_mandatory = True
        #     doc.save(ignore_permissions=True)
        #     frappe.db.commit()
        #     frappe.log_error(f"After Save - Document Saved with Workflow State: {doc.workflow_state}", "Debug Save")
        # except Exception as e:
        #     frappe.log_error(f"Error saving document {doc.name}: {str(e)}", "Documenso Save Error")

        try:
            download_signed_contract(doc.name)
        except Exception as e:
            frappe.log_error(f"Error downloading signed contract for {doc.name}: {str(e)}", "Documenso Download Error")


    elif event == "DOCUMENT_REJECTED" and status == "PENDING":
        doc.workflow_state = "Rejected"
        frappe.log_error(f"Document {document_id} rejected and updated to 'Rejected'", "Documenso Webhook")

    elif event == "DOCUMENT_CANCELLED" and status == "PENDING":
        doc.workflow_state = "Rejected"
        frappe.log_error(f"Document {document_id} canceled and updated to 'Canceled'", "Documenso Webhook")

    else:
        frappe.log_error(f"Unhandled event/status:\nEvent: {event}\nStatus: {status}\nDocument ID: {document_id}", "Documenso Webhook")
        frappe.throw(_("Unhandled event or status"))

    # Save the document with the updated workflow state
    doc.save()

    # Log the final workflow state
    frappe.log_error(f"Document {document_id} successfully updated to state: {doc.workflow_state}", "Documenso Webhook")

    return {"status": "success", "message": "Webhook processed and document updated"}
