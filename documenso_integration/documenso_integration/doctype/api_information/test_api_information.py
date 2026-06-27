# Copyright (c) 2025, Manya and Contributors
# See license.txt

import frappe
import hmac
import json
from frappe.tests.utils import FrappeTestCase
from documenso_integration.webhook import incoming_webhook

class MockRequest:
	def __init__(self, headers, json_data):
		self.headers = headers
		self.json_data = json_data

	def get_json(self):
		return self.json_data

class TestAPIInformation(FrappeTestCase):
	def setUp(self):
		# Clean up any leftover test data first
		frappe.db.delete("Contract Version", {"contract": "test-webhook-contract"})
		frappe.db.delete("Contract", {"counterparty_name": "Test Acme Corp"})
		frappe.db.delete("CounterParty", {"organization": "Test Acme Corp"})
		frappe.db.delete("Contract Content", {"contract_type": "Confidentiality & Non-Disclosure Contract"})
		frappe.db.delete("API Information", {"document_id": "test_doc_123"})
		frappe.db.delete("Singles", {"doctype": "Documenso Settings"})
		
		# Create test Documenso Settings
		self.settings = frappe.get_doc({
			"doctype": "Documenso Settings",
			"base_url": "https://documenso.com/api/v1/documents",
			"api_key": "test_api_key",
			"webhook_secret": "test_webhook_secret"
		})
		self.settings.insert(ignore_permissions=True)

		# Create a test Contract Content
		if not frappe.db.exists("Contract Content", "Confidentiality & Non-Disclosure Contract"):
			self.template = frappe.get_doc({
				"doctype": "Contract Content",
				"contract_type": "Confidentiality & Non-Disclosure Contract",
				"content": "<p>Test template content</p>"
			})
			self.template.insert(ignore_permissions=True)

		# Create a test Counterparty
		if not frappe.db.exists("CounterParty", "Test Acme Corp"):
			self.counterparty = frappe.get_doc({
				"doctype": "CounterParty",
				"organization": "Test Acme Corp",
				"requester_email": "test_acme@example.com",
				"requester_phone_no": "+919999999999",
				"address": "Test Address",
				"organization_website": "https://testacme.com"
			})
			self.counterparty.insert(ignore_permissions=True)

		# Create a test Contract
		self.contract = frappe.get_doc({
			"doctype": "Contract",
			"title": "Test Webhook Contract",
			"contract_type": "Confidentiality & Non-Disclosure Contract",
			"counterparty_name": "Test Acme Corp",
			"counterparty_email": "test_acme@example.com",
			"contract_term": "Definite",
			"contract_duration": 12,
			"contract_effective_date": "2026-06-26",
			"content": "<p>Test Content</p>",
			"amount_to_receive": 1000,
			"tax": 18,
			"requester_name": "Test Requester",
			"requester_department": "Legal"
		})
		self.contract.insert(ignore_permissions=True)
		self.contract.db_set("workflow_state", "Awaiting Signature")

		# Create linked API Information
		self.api_info = frappe.get_doc({
			"doctype": "API Information",
			"document_id": "test_doc_123",
			"upload_url": "https://upload.com/test",
			"recipient_id": "999",
			"signing_url": "https://sign.com/999"
		})
		self.api_info.insert(ignore_permissions=True)

		# Link them
		self.contract.db_set("documenso_id", self.api_info.name)
		
		# Save original request
		self.original_request = getattr(frappe.local, "request", None)

	def tearDown(self):
		frappe.local.request = self.original_request
		frappe.db.delete("Contract Version", {"contract": "test-webhook-contract"})
		frappe.db.delete("Contract", {"counterparty_name": "Test Acme Corp"})
		frappe.db.delete("CounterParty", {"organization": "Test Acme Corp"})
		frappe.db.delete("Contract Content", {"contract_type": "Confidentiality & Non-Disclosure Contract"})
		frappe.db.delete("API Information", {"document_id": "test_doc_123"})
		frappe.db.delete("Singles", {"doctype": "Documenso Settings"})

	def test_webhook_unauthorized(self):
		frappe.local.request = MockRequest(
			headers={"X-Documenso-Secret": "wrong_secret"},
			json_data={}
		)
		with self.assertRaises(frappe.PermissionError):
			incoming_webhook()

	def test_webhook_document_completed(self):
		frappe.local.request = MockRequest(
			headers={"X-Documenso-Secret": "test_webhook_secret"},
			json_data={
				"event": "DOCUMENT_COMPLETED",
				"payload": {
					"id": "test_doc_123",
					"status": "COMPLETED"
				}
			}
		)

		import documenso_integration.webhook as webhook_module
		original_download = webhook_module.download_signed_contract
		webhook_module.download_signed_contract = lambda name: frappe.db.set_value("API Information", name, "download_url", "https://download.com/signed")

		try:
			response = incoming_webhook()
			self.assertEqual(response.get("status"), "success")
			
			contract_state = frappe.db.get_value("Contract", self.contract.name, "workflow_state")
			self.assertEqual(contract_state, "Active")
		finally:
			webhook_module.download_signed_contract = original_download

	def test_webhook_document_rejected(self):
		frappe.local.request = MockRequest(
			headers={"X-Documenso-Secret": "test_webhook_secret"},
			json_data={
				"event": "DOCUMENT_REJECTED",
				"payload": {
					"id": "test_doc_123",
					"status": "REJECTED"
				}
			}
		)

		response = incoming_webhook()
		self.assertEqual(response.get("status"), "success")

		contract_state = frappe.db.get_value("Contract", self.contract.name, "workflow_state")
		self.assertEqual(contract_state, "Rejected")
