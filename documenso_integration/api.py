import requests
import frappe
from frappe import _
from frappe.utils.pdf import get_pdf

def get_settings():
    return frappe.get_single("Documenso Settings")

def get_headers():
    settings = get_settings()
    api_key = settings.get_password("api_key")
    if not api_key:
        frappe.throw(_("Documenso API Key is not configured in Documenso Settings."))
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

def get_base_url():
    settings = get_settings()
    return settings.base_url or "https://documenso.com/api/v1/documents"

@frappe.whitelist(methods=["POST"])
def sign_contract(contract_name):
    frappe.has_permission("Contract", "write", doc=contract_name, throw=True)
    
    create_response = create_documenso_record(contract_name)
    if "error" in create_response:
        frappe.throw(_("Documenso record creation failed: {0}").format(create_response['error']))
        return  

    upload_response = upload_contract_to_documenso(contract_name)
    if "error" in upload_response:
        frappe.throw(_("Documenso Upload Error: {0}").format(upload_response['error']))
    
    field_response = create_field_in_documenso(contract_name)
    if "error" in field_response:
        frappe.throw(_("Documenso Field Creation Error: {0}").format(field_response['error']))

    send_response = send_contract_for_signature(contract_name)
    if "error" in send_response:
        frappe.throw(_("Documenso Send Error: {0}").format(send_response['error']))

@frappe.whitelist(methods=["POST"])
def create_documenso_record(contract_name):
    frappe.has_permission("Contract", "write", doc=contract_name, throw=True)
    
    contract = frappe.get_doc("Contract", contract_name)
    signees = contract.signee 

    if not signees:
        return {"error": _("No signees found in the contract.")}

    recipients = []
    for idx, signee in enumerate(signees):
        recipients.append({
            "email": signee.email,
            "name": signee.name or _("Signee"), 
            "role": "SIGNER",
            "signingOrder": idx 
        })

    payload = {
        "title": contract.name,
        "externalId": contract.name,
        "recipients": recipients,
        "meta": {
            "signingOrder": "SEQUENTIAL" 
        },
        "authOptions": {},
        "formValues": {}
    }

    response = requests.post(get_base_url(), json=payload, headers=get_headers(), timeout=10)
    if response.status_code == 200:
        doc_data = response.json()

        if "recipients" in doc_data and doc_data["recipients"]:
            recipient_ids = [str(r.get("recipientId")) for r in doc_data["recipients"] if r.get("recipientId")]
            joined_ids = ",".join(recipient_ids)
            
            signing_url = [str(r.get("signingUrl")) for r in doc_data["recipients"] if r.get("signingUrl")]
            joined_urls = ",".join(signing_url)

            api_info = frappe.get_doc({
                "doctype": "API Information",
                "document_id": doc_data.get("documentId"),
                "upload_url": doc_data.get("uploadUrl"),
                "recipient_id": joined_ids,
                "signing_url": joined_urls,
            })
            api_info.insert(ignore_permissions=True)

            contract.db_set("documenso_id", api_info.name)

        return doc_data
    else:
        frappe.log_error(f"Documenso Error: {response.text}", "Documenso API")
        return {"error": response.text}

@frappe.whitelist(methods=["POST"])
def upload_contract_to_documenso(contract_name):
    try:
        frappe.has_permission("Contract", "write", doc=contract_name, throw=True)
        
        contract = frappe.get_doc("Contract", contract_name)
        pdf_file = get_pdf(frappe.get_print("Contract", contract_name, print_format="Contract Final Print"))
        api_info = frappe.get_doc("API Information", contract.documenso_id)
        
        upload_url = api_info.upload_url  
        if not upload_url:
            frappe.throw(_("Upload URL is missing. Ensure the document is created in Documenso."))

        files = {'file': (f"{contract_name}.pdf", pdf_file, "application/pdf")}
        response = requests.put(upload_url, files=files, timeout=10)

        if response.status_code in [200, 201]:
            return {"success": True}
        else:
            return {"error": response.text}
    except Exception as e:
        return {"error": str(e)}

@frappe.whitelist(methods=["POST"])
def create_field_in_documenso(contract_name):
    frappe.has_permission("Contract", "write", doc=contract_name, throw=True)
    
    contract = frappe.get_doc("Contract", contract_name)
    api_info = frappe.get_doc("API Information", contract.documenso_id)
    document_id = api_info.document_id
    recipient_ids_str = api_info.recipient_id

    if not document_id or not recipient_ids_str:
        return {"error": _("Document ID or Recipient ID(s) is missing.")}

    try:
        document_id = int(document_id)
    except ValueError:
        return {"error": _("Invalid Document ID format.")}

    try:
        recipient_ids = [int(rid.strip()) for rid in recipient_ids_str.split(",") if rid.strip()]
    except ValueError:
        return {"error": _("Invalid Recipient ID(s) format.")}

    url = f"{get_base_url()}/{document_id}/fields"
    errors = []

    for recipient_id in recipient_ids:
        payload = {
            "recipientId": recipient_id,
            "type": "SIGNATURE",
            "pageNumber": 1,
            "pageX": 30,
            "pageY": 150,
            "pageWidth": 80,
            "pageHeight": 30,
            "fieldMeta": {}
        }

        response = requests.post(url, json=payload, headers=get_headers(), timeout=10)
        if response.status_code not in [200, 201]:
            errors.append({
                "recipient_id": recipient_id,
                "error": response.text
            })

    if errors:
        return {"error": _("Some fields could not be created."), "details": errors}
    else:
        return {"success": True}

@frappe.whitelist(methods=["POST"])
def send_contract_for_signature(contract_name):
    frappe.has_permission("Contract", "write", doc=contract_name, throw=True)
    
    contract = frappe.get_doc("Contract", contract_name)
    api_info = frappe.get_doc("API Information", contract.documenso_id)
    document_id = api_info.document_id

    if not document_id:
        return {"error": _("Document ID is missing.")}

    url = f"{get_base_url()}/{int(document_id)}/send"
    payload = {
        "sendEmail": True,
        "sendCompletionEmails": True
    }

    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        response_data = response.json()
    except Exception as e:
        frappe.log_error(
            title="Documenso Response Error",
            message=f"Error parsing response: {e}\nRaw response: {response.text}"
        )
        return {"error": _("Failed to parse Documenso response.")}

    if response.status_code in [200, 201]:
        try:
            recipients = []
            if isinstance(response_data, dict):
                recipients = response_data.get("recipients", [])
            elif isinstance(response_data, list):
                recipients = response_data

            if not recipients:
                return {"error": _("No recipients found in response.")}

            api_info.save(ignore_permissions=True)
            return {"message": _("Document sent and signing URLs saved successfully.")}

        except Exception as e:
            frappe.log_error(
                title="Error Saving Signing URLs",
                message=f"Exception: {e}\nResponse: {frappe.as_json(response_data)}"
            )
            return {"error": _("Error while saving signing URLs.")}
    else:
        frappe.log_error(
            title="Documenso API Error",
            message=f"Status Code: {response.status_code}\nResponse: {frappe.as_json(response_data)}"
        )
        return {"error": response_data}

@frappe.whitelist(methods=["POST"])
def download_signed_contract(contract_name):
    frappe.has_permission("Contract", "write", doc=contract_name, throw=True)
    
    contract = frappe.get_doc("Contract", contract_name)
    api_info = frappe.get_doc("API Information", contract.documenso_id)
    document_id = api_info.document_id

    if not document_id:
        return {"error": _("Document ID is missing.")}

    url = f"{get_base_url()}/{int(document_id)}/download"
    response = requests.get(url, headers=get_headers(), timeout=10)

    if response.status_code == 200:
        try:
            data = response.json()
            download_url = data.get("downloadUrl")

            if not download_url:
                return {"error": _("Download URL not found in the response.")}

            frappe.db.set_value("API Information", api_info.name, "download_url", download_url)

            return {
                "success": True,
                "message": _("Download URL saved successfully."),
                "download_url": download_url
            }
        except Exception as e:
            frappe.log_error(f"Download URL Parsing Error: {e}\nResponse: {response.text}")
            return {"error": _("Failed to parse download URL from Documenso.")}
    else:
        frappe.log_error(f"Documenso Download URL Error: {response.text}")
        return {"error": _("Failed to get download URL. Status code: {0}").format(response.status_code)}
