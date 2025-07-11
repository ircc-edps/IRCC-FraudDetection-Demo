"""
Configuration module for the AI Document Validator backend.
Customize these settings to adapt the solution for different document types.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Azure Storage Configuration
AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")

# Container names - customize as needed for your use case
DOCUMENTS_CONTAINER = "documents"  # Container for uploaded documents
REPORT_CONTAINER = "reports"  # Container for generated reports
METADATA_CONTAINER = "metadata"  # Container for uploaded documents metadata

# Document validation settings
ALLOWED_FILE_EXTENSIONS = [
    ".pdf",
    ".jpg",
    ".png",
]  # Add more extensions as needed (.docx, etc.)

# API settings
CORS_ORIGINS = ["*"]  # Customize with your frontend origins

# Processing settings
POLLING_INTERVAL_MS = 2000  # Status check polling interval
