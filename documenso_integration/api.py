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
    # Retrieve all signees from the child table
    signees = contract.signee  # Assuming 'signee' is the child table fieldname

    if not signees:
        return {"error": "No signees found in the contract."}

    # Construct the recipients list
    recipients = []
    for idx, signee in enumerate(signees):
        recipients.append({
            "email": signee.email,
            "name": signee.name or "Signee",  # Replace with appropriate field if available
            "role": "SIGNER",
            "signingOrder": idx  # Adjust signing order as needed
        })

    payload = {
        "title": contract.name,
        "externalId": contract.name,
        "recipients": recipients,
        "meta": {
            "signingOrder": "SEQUENTIAL"  # Use "PARALLEL" if order doesn't matter
        },
        "authOptions": {},
        "formValues": {}
    }


    response = requests.post(DOCUMENSO_BASE_URL, json=payload, headers=headers)
    if response.status_code == 200:
        doc_data = response.json()
        print(doc_data)
        frappe.db.set_value("Contract", contract.name, "document_id", doc_data.get("documentId"))
        frappe.db.set_value("Contract", contract.name, "upload_url", doc_data.get("uploadUrl"))

        if "recipients" in doc_data and doc_data["recipients"]:
            print("\nRecipients:", doc_data["recipients"], "\n")
            recipient_ids = [str(r.get("recipientId")) for r in doc_data["recipients"] if r.get("recipientId")]
            joined_ids = ",".join(recipient_ids)
            frappe.db.set_value("Contract", contract.name, "recipient_id", joined_ids)
            signing_url = [str(r.get("signingUrl")) for r in doc_data["recipients"] if r.get("signingUrl")]
            joined_urls = ",".join(signing_url)
            frappe.db.set_value("Contract", contract.name, "signing_url", joined_urls)

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
    document_id = contract.document_id
    recipient_ids_str = contract.recipient_id

    if not document_id or not recipient_ids_str:
        return {"error": "Document ID or Recipient ID(s) is missing."}

    try:
        document_id = int(document_id)
    except ValueError:
        return {"error": "Invalid Document ID format."}

    # Split the recipient IDs and convert to integers
    try:
        recipient_ids = [int(rid.strip()) for rid in recipient_ids_str.split(",") if rid.strip()]
    except ValueError:
        return {"error": "Invalid Recipient ID(s) format."}

    url = f"{DOCUMENSO_BASE_URL}/{document_id}/fields"
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

        response = requests.post(url, json=payload, headers=headers)
        if response.status_code not in [200, 201]:
            errors.append({
                "recipient_id": recipient_id,
                "error": response.text
            })

    if errors:
        return {"error": "Some fields could not be created.", "details": errors}
    else:
        return {"success": True}


@frappe.whitelist()
def send_contract_for_signature(contract_name):
    # Fetch contract document
    contract = frappe.get_doc("Contract", contract_name)
    document_id = contract.document_id

    if not document_id:
        return {"error": "Document ID is missing."}

    url = f"{DOCUMENSO_BASE_URL}/{int(document_id)}/send"
    print("\nSending to:", url, "\n")

    payload = {
        "sendEmail": True,
        "sendCompletionEmails": True
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response_data = response.json()
        print(response_data)
    except Exception as e:
        frappe.log_error(
            title="Documenso Response Error",
            message=f"Error parsing response: {e}\nRaw response: {response.text}"
        )
        return {"error": "Failed to parse Documenso response."}

    if response.status_code in [200, 201]:
        try:
            recipients = []
            if isinstance(response_data, dict):
                recipients = response_data.get("recipients", [])
            elif isinstance(response_data, list):
                recipients = response_data

            if not recipients:
                return {"error": "No recipients found in response."}

            # Extract signing URLs corresponding to existing recipient IDs
            recipient_ids = [rid.strip() for rid in contract.recipient_id.split(",") if rid.strip()]
            print(recipient_ids)

            # Update the contract document
            contract.save(ignore_permissions=True)
            frappe.db.commit()

            return {"message": "Document sent and signing URLs saved successfully."}

        except Exception as e:
            frappe.log_error(
                title="Error Saving Signing URLs",
                message=f"Exception: {e}\nResponse: {frappe.as_json(response_data)}"
            )
            return {"error": "Error while saving signing URLs."}

    else:
        frappe.log_error(
            title="Documenso API Error",
            message=f"Status Code: {response.status_code}\nResponse: {frappe.as_json(response_data)}"
        )
        return {"error": response_data}

@frappe.whitelist()
def download_signed_contract(contract_name):
    contract = frappe.get_doc("Contract", contract_name)
    document_id = contract.document_id

    if not document_id:
        return {"error": "Document ID is missing."}

    url = f"{DOCUMENSO_BASE_URL}/{int(document_id)}/download"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        try:
            data = response.json()
            download_url = data.get("downloadUrl")
            frappe.log_error("Download URL:", download_url)

            if not download_url:
                return {"error": "Download URL not found in the response."}

            # Save the download URL to the Contract doctype
            frappe.db.set_value("Contract", contract.name, "download_url", download_url)
            frappe.db.commit()

            return {
                "success": True,
                "message": "Download URL saved successfully.",
                "download_url": download_url
            }
        except Exception as e:
            frappe.log_error(f"Download URL Parsing Error: {e}\nResponse: {response.text}")
            return {"error": "Failed to parse download URL from Documenso."}
    else:
        frappe.log_error(f"Documenso Download URL Error: {response.text}")
        return {"error": f"Failed to get download URL. Status code: {response.status_code}"}
