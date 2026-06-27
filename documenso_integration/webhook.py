import frappe
import hmac
import json
from frappe import _
from documenso_integration.api import download_signed_contract  

@frappe.whitelist(allow_guest=True)
def incoming_webhook():
    settings = frappe.get_single("Documenso Settings")
    expected_secret = settings.get_password("webhook_secret")

    if not expected_secret:
        frappe.throw(_("Webhook secret is not configured in Documenso Settings."), frappe.PermissionError)

    received_signature = frappe.request.headers.get("X-Documenso-Secret") or frappe.request.headers.get("X-Documenso-Signature")
    
    if not received_signature or not hmac.compare_digest(received_signature, expected_secret):
        frappe.throw(_("Unauthorized request signature."), frappe.PermissionError)

    payload = frappe.request.get_json()
    if not payload:
        frappe.throw(_("Invalid or missing JSON payload"), frappe.BadRequest)

    frappe.log_error(json.dumps(payload, indent=2), "Incoming Documenso Webhook")

    event = payload.get('event')
    document_data = payload.get('payload', {})
    document_id = document_data.get('id')
    status = document_data.get('status')

    if not document_id or not status:
        frappe.throw(_("Missing required data in payload"))

    try:
        doc = frappe.get_doc("API Information", {"document_id": document_id})
        frappe.log_error(f"API Information document found: {doc.name}", "Documenso Webhook Document Found")
    except frappe.DoesNotExistError:
        frappe.throw(_("API Information record not found for external Document ID: {0}").format(document_id))

    if event == "DOCUMENT_COMPLETED" and status == "COMPLETED":
        try:
            download_signed_contract(doc.name)  
            
            contract_name = frappe.db.get_value("Contract", {"documenso_id": doc.name}, "name")
            if contract_name:
                contract = frappe.get_doc("Contract", contract_name)
                if contract.workflow_state != "Active":
                    contract.db_set("workflow_state", "Active")
                    frappe.log_error(f"Contract {contract.name} set to 'Active' on DOCUMENT_COMPLETED", "Documenso Webhook")
                    
                    frappe.publish_realtime('workflow_state_updated', {
                        'contract_name': contract.name,
                        'workflow_state': "Active"
                    })
            else:
                frappe.log_error(f"No Contract found with documenso_id (API Info name): {doc.name}", "Documenso Completed Event")
        except Exception as e:
            frappe.log_error(f"Error downloading/updating signed contract for {doc.name}: {str(e)}", "Documenso Download Error")
            
    elif event == "DOCUMENT_REJECTED":
        try:
            contract_name = frappe.db.get_value("Contract", {"documenso_id": doc.name}, "name")
            if contract_name:
                contract = frappe.get_doc("Contract", contract_name)
                if contract.workflow_state != "Rejected":
                    contract.db_set("workflow_state", "Rejected")
                    frappe.log_error(f"Contract {contract.name} set to 'Rejected' on DOCUMENT_REJECTED", "Documenso Webhook")
                    
                    frappe.publish_realtime('workflow_state_updated', {
                        'contract_name': contract.name,
                        'workflow_state': "Rejected"
                    })
            else:
                frappe.log_error(f"No Contract found with documenso_id (API Info name): {doc.name}", "Documenso Rejected Event")
        except Exception as e:
            frappe.log_error(f"Error handling DOCUMENT_REJECTED for {doc.name}: {str(e)}", "Documenso Rejected Event Error")

    return {"status": "success", "message": "Webhook processed successfully"}

def api_information_after_save(doc, method):
    if doc.download_url:
        try:
            contract_name = frappe.db.get_value("Contract", {"documenso_id": doc.name}, "name")
            
            if contract_name:
                contract = frappe.get_doc("Contract", contract_name)
                if contract.workflow_state != "Active":
                    contract.db_set("workflow_state", "Active")
                    
                    frappe.publish_realtime('workflow_state_updated', {
                        'contract_name': contract.name,
                        'workflow_state': "Active"
                    })
            else:
                frappe.log_error(f"No Contract found with documenso_id (API Info name): {doc.name}", "API Information Doc Events")

        except Exception as e:
            frappe.log_error(f"Failed to update Contract for API Info name {doc.name}: {str(e)}", "API Information Doc Events")
