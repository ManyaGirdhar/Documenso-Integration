# import os
# import requests
# import frappe
# from dotenv import load_dotenv
# from frappe.utils.pdf import get_pdf

# load_dotenv()

# DOCUMENSO_API_KEY = os.getenv("DOCUMENSO_API_KEY")
# DOCUMENSO_BASE_URL = os.getenv("DOCUMENSO_BASE_URL")

# headers = {
#     "Authorization": f"Bearer {DOCUMENSO_API_KEY}",
#     "Content-Type": "application/json"
# }

# @frappe.whitelist()
# def sign_contract(contract_name):
#     frappe.logger().info(f"📌 Starting contract signing process for: {contract_name}")

#     create_response = create_documenso_record(contract_name)

#     if "error" in create_response:
#         frappe.logger().error(f"❌ Documenso record creation failed: {create_response['error']}")
#         frappe.throw(f"Documenso record creation failed: {create_response['error']}")  
#         return  # Ensure function stops

#     frappe.logger().info("✅ Document record created in Documenso.")

#     # 🔹 Debugging before calling upload function
#     frappe.logger().info(f"📌 Calling upload_contract_to_documenso for {contract_name}...")

#     upload_response = upload_contract_to_documenso(contract_name)

#     # 🔹 Debugging after calling upload function
#     frappe.logger().info(f"📌 Upload function called. Response: {upload_response}")

#     if "error" in upload_response:
#         frappe.logger().error(f"❌ Documenso Upload Error: {upload_response['error']}")
#         frappe.throw(f"Documenso Upload Error: {upload_response['error']}")  
#     else:
#         frappe.logger().info("✅ Contract uploaded to Documenso.")



# @frappe.whitelist()
# def create_documenso_record(contract_name):
#     """Create a document in Documenso and get the upload URL"""
#     contract = frappe.get_doc("Contract", contract_name)

#     payload = {
#         "title": "Contract Agreement",
#         "externalId": contract.name,  # Fixed incorrect externalId
#         "recipients": [
#             {
#                 "email": contract.counterparty_email,
#                 "name": contract.counterparty_name,  # Ensure this field exists in the Contract doctype
#                 "role": "SIGNER"
#             }
#         ],
#         "meta": {},
#         "authOptions": {},
#         "formValues": {}
#     }

#     response = requests.post(DOCUMENSO_BASE_URL, json=payload, headers=headers)

#     if response.status_code == 200:
#         doc_data = response.json()
#         print("setting document_id and upload_url")
#         frappe.db.set_value("Contract", contract.name, "document_id", doc_data.get("documentId"))
#         frappe.db.set_value("Contract", contract.name, "upload_url", doc_data.get("uploadUrl"))

#         # Extract recipient details and update the contract record
#         if "recipients" in doc_data and doc_data["recipients"]:
#             print("recipients found")
#             recipient = doc_data["recipients"][0]
#             frappe.db.set_value("Contract", contract.name, "recipient_id", recipient.get("recipientId"))

#         frappe.db.commit()
#         return doc_data
#     else:
#         frappe.log_error(f"Documenso Error: {response.text}", "Documenso API")
#         return {"error": response.text}




# @frappe.whitelist()
# def upload_contract_to_documenso(contract_name):
#     """Generate contract PDF and upload it to Documenso using uploadUrl."""
    
#     try:
#         frappe.logger().info(f"📌 Uploading contract: {contract_name}")

#         # Fetch contract document
#         contract = frappe.get_doc("Contract", contract_name)
#         frappe.logger().info(f"✅ Contract {contract_name} fetched successfully.")

#         # Generate PDF using the print format
#         pdf_file = get_pdf(frappe.get_print("Contract", contract_name, print_format="Contract Final Print"))
#         frappe.logger().info(f"✅ PDF generated for contract: {contract_name}")

#         # Get the upload URL from the contract document
#         upload_url = contract.upload_url  
#         if not upload_url:
#             frappe.logger().error("❌ Upload URL is missing.")
#             frappe.throw("Upload URL is missing. Ensure the document is created in Documenso.")

#         frappe.logger().info(f"📌 Uploading contract PDF to: {upload_url}")

#         # Upload the file to Documenso
#         files = {'file': (f"{contract_name}.pdf", pdf_file, "application/pdf")}
#         response = requests.put(upload_url, files=files)

#         # Debugging response
#         frappe.logger().info(f"🔄 Documenso API Response: {response.status_code} | {response.text}")

#         if response.status_code in [200, 201]:  # Successful upload
#             frappe.msgprint("✅ Contract document uploaded to Documenso successfully!")
#             frappe.logger().info("✅ Upload successful!")
#             return {"success": True}
#         else:
#             frappe.log_error(f"❌ Documenso Upload Error: {response.text}", "Documenso API")
#             return {"error": response.text}

#     except Exception as e:
#         frappe.logger().error(f"❌ Exception occurred: {str(e)}")
#         frappe.log_error(f"Exception: {str(e)}", "Documenso Upload Error")
#         return {"error": str(e)}





import os
import requests
import frappe
from dotenv import load_dotenv
from frappe.utils.pdf import get_pdf

load_dotenv()

DOCUMENSO_API_KEY = os.getenv("DOCUMENSO_API_KEY")
DOCUMENSO_BASE_URL = os.getenv("DOCUMENSO_BASE_URL")

headers = {
    "Authorization": f"Bearer {DOCUMENSO_API_KEY}",
    "Content-Type": "application/json"
}

@frappe.whitelist()
def sign_contract(contract_name):
    frappe.logger().info(f"📌 Starting contract signing process for: {contract_name}")

    create_response = create_documenso_record(contract_name)
    if "error" in create_response:
        frappe.logger().error(f"❌ Documenso record creation failed: {create_response['error']}")
        frappe.throw(f"Documenso record creation failed: {create_response['error']}")
        return  

    frappe.logger().info("✅ Document record created in Documenso.")

    upload_response = upload_contract_to_documenso(contract_name)
    frappe.logger().info(f"📌 Upload function called. Response: {upload_response}")

    if "error" in upload_response:
        frappe.logger().error(f"❌ Documenso Upload Error: {upload_response['error']}")
        frappe.throw(f"Documenso Upload Error: {upload_response['error']}")
    else:
        frappe.logger().info("✅ Contract uploaded to Documenso.")
    
    field_response = create_field_in_documenso(contract_name)
    if "error" in field_response:
        frappe.logger().error(f"❌ Documenso Field Creation Error: {field_response['error']}")
        frappe.throw(f"Documenso Field Creation Error: {field_response['error']}")

    send_response = send_contract_for_signature(contract_name)
    if "error" in send_response:
        frappe.logger().error(f"❌ Documenso Send Error: {send_response['error']}")
        frappe.throw(f"Documenso Send Error: {send_response['error']}")

    frappe.logger().info("✅ Contract sent for signature successfully!")

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
    document_id = contract.document_id
    recipient_id = contract.recipient_id

    if not document_id or not recipient_id:
        return {"error": "Document ID or Recipient ID is missing."}

    url = f"https://app.documenso.com/api/v1/documents/{document_id}/fields"
    payload = {
        "recipientId": recipient_id,
        "type": "NAME",
        "pageNumber": 3,
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
    document_id = contract.document_id

    if not document_id:
        return {"error": "Document ID is missing."}

    url = f"https://app.documenso.com/api/v1/documents/{document_id}/send"
    response = requests.post(url, headers=headers)

    if response.status_code in [200, 201]:
        return {"success": True}
    else:
        return {"error": response.text}
