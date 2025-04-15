import os
import requests
import frappe
# from dotenv import load_dotenv
from frappe.utils.pdf import get_pdf

# load_dotenv()

DOCUMENSO_API_KEY = os.getenv("DOCUMENSO_API_KEY")
DOCUMENSO_BASE_URL = os.getenv("DOCUMENSO_BASE_URL")

headers = {
    "Authorization": f"Bearer {DOCUMENSO_API_KEY}",
    "Content-Type": "application/json"
}

@frappe.whitelist()
def sign_contract(contract_name):
    create_response = create_documenso_record(contract_name)
    if "error" in create_response:
        frappe.throw(f"Documenso record creation failed: {create_response['error']}")
        return  

    upload_response = upload_contract_to_documenso(contract_name)

    if "error" in upload_response:
        frappe.throw(f"Documenso Upload Error: {upload_response['error']}")
    
    field_response = create_field_in_documenso(contract_name)
    if "error" in field_response:
        frappe.throw(f"Documenso Field Creation Error: {field_response['error']}")

    send_response = send_contract_for_signature(contract_name)
    if "error" in send_response:
        frappe.throw(f"Documenso Send Error: {send_response['error']}")

@frappe.whitelist()
def create_documenso_record(contract_name):
    contract = frappe.get_doc("Contract", contract_name)
    payload = {
        "title": "Contract Agreement",
        "externalId": contract.name,
        "recipients": [
            {
                "email": contract.counterparty_email,
                "name": contract.counterparty_name,
                "role": "SIGNER"
            }
        ],
        "meta": {},
        "authOptions": {},
        "formValues": {}
    }

    response = requests.post(DOCUMENSO_BASE_URL, json=payload, headers=headers)
    if response.status_code == 200:
        doc_data = response.json()
        frappe.db.set_value("Contract", contract.name, "document_id", doc_data.get("documentId"))
        frappe.db.set_value("Contract", contract.name, "upload_url", doc_data.get("uploadUrl"))

        if "recipients" in doc_data and doc_data["recipients"]:
            recipient = doc_data["recipients"][0]
            frappe.db.set_value("Contract", contract.name, "recipient_id", recipient.get("recipientId"))

        frappe.db.commit()
        return doc_data
    else:
        frappe.log_error(f"Documenso Error: {response.text}", "Documenso API")
        return {"error": response.text}

@frappe.whitelist()
def upload_contract_to_documenso(contract_name):
    try:
        contract = frappe.get_doc("Contract", contract_name)
        pdf_file = get_pdf(frappe.get_print("Contract", contract_name, print_format="Contract Final Print"))
        upload_url = contract.upload_url  
        if not upload_url:
            frappe.throw("Upload URL is missing. Ensure the document is created in Documenso.")

        files = {'file': (f"{contract_name}.pdf", pdf_file, "application/pdf")}
        response = requests.put(upload_url, files=files)

        if response.status_code in [200, 201]:
            return {"success": True}
        else:
            return {"error": response.text}
    except Exception as e:
        return {"error": str(e)}

@frappe.whitelist()
def create_field_in_documenso(contract_name):
    contract = frappe.get_doc("Contract", contract_name)
    document_id = int(contract.document_id)
    recipient_id = int(contract.recipient_id)

    if not document_id or not recipient_id:
        return {"error": "Document ID or Recipient ID is missing."}

    url = f"{DOCUMENSO_BASE_URL}/{document_id}/fields"
    payload = {
        "recipientId": recipient_id,
        "type": "SIGNATURE",
        "pageNumber": 1,
        "pageX": 1,
        "pageY": 1,
        "pageWidth": 1,
        "pageHeight": 1,
        "fieldMeta": {}
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code in [200, 201]:
        return {"success": True}
    else:
        return {"error": response.text}

@frappe.whitelist()
def send_contract_for_signature(contract_name):
    contract = frappe.get_doc("Contract", contract_name)
    document_id = int(contract.document_id)

    if not document_id:
        return {"error": "Document ID is missing."}

    url = f"{DOCUMENSO_BASE_URL}{document_id}/send"

    payload = {
        "sendEmail": True,
        "sendCompletionEmails": True
    }

    response = requests.post(url, headers=headers, json=payload)
    try:
        response_data = response.json()
    except Exception:
        return {"error": response.text}

    if response.status_code in [200, 201]:
        try:
            # Extract signing URL from the response
            recipients = response_data.get("recipients", [])
            if recipients:
                signing_url = recipients[0].get("signingUrl")
                if signing_url:
                    frappe.db.set_value("Contract", contract.name, "signing_url", signing_url)
                    frappe.db.commit()
                    
        except Exception as e:
            frappe.log_error(f"Error saving signing URL: {str(e)}", "Documenso Integration")

        return {"message": "Document sent and signing URL saved successfully."}
    else:
        return {"error": response_data}