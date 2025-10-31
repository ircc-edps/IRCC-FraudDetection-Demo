"""
Configuration module for the AI Document Validator Azure Function.
Customize these settings to adapt the solution for different document types.
"""

import os

# Azure Blob Storage settings
STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
DOCUMENTS_CONTAINER = "documents"  # Input documents container
REPORTS_CONTAINER = "reports"  # Validation reports
METADATA_CONTAINER = "metadata"  # Metadata storage


# Azure OpenAI settings
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.environ.get("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
