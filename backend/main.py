import os
import time
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from azure.storage.blob import BlobServiceClient, ContainerClient
from starlette.responses import JSONResponse
from dotenv import load_dotenv

# Import configuration settings
from config import (
    AZURE_STORAGE_CONNECTION_STRING,
    DOCUMENTS_CONTAINER,
    REPORT_CONTAINER,
    ALLOWED_FILE_EXTENSIONS,
    CORS_ORIGINS,
)

# Configure logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("backend")
logging.getLogger("azure").setLevel(logging.WARNING)

# Validate configuration
if not AZURE_STORAGE_CONNECTION_STRING:
    raise RuntimeError(
        "AZURE_STORAGE_CONNECTION_STRING is not set. Please check your .env file."
    )

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

blob_service_client = BlobServiceClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING
)


# Ensure containers exist
def ensure_container_exists(container_name):
    try:
        # Try to create the container (will succeed if it doesn't exist)
        container_client = blob_service_client.create_container(container_name)
        logger.debug("Ensured container exists", extra={"container": container_name})
        return True
    except Exception as e:
        logger.exception(
            "Error ensuring container exists",
            extra={"container": container_name},
        )
        return False


# Create containers at startup
@app.on_event("startup")
def startup_event():
    logger.info("Starting backend service")
    ensure_container_exists(DOCUMENTS_CONTAINER)
    logger.info("Startup completed")


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    logger.info("Received upload request", extra={"filename": file.filename})
    try:
        # Check if file has allowed extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ALLOWED_FILE_EXTENSIONS:
            allowed_formats = ", ".join(ALLOWED_FILE_EXTENSIONS)
            logger.warning(
                "Rejected upload due to invalid format",
                extra={"filename": file.filename, "allowed_formats": allowed_formats},
            )
            raise HTTPException(
                status_code=400, detail=f"Only {allowed_formats} files are allowed."
            )

        # Ensure container exists
        ensure_container_exists(DOCUMENTS_CONTAINER)

        try:
            # Get blob client and upload
            blob_client = blob_service_client.get_blob_client(
                container=DOCUMENTS_CONTAINER, blob=file.filename
            )
            logger.debug(
                "Reading upload content",
                extra={"filename": file.filename},
            )
            content = await file.read()
            logger.info(
                "Uploading file to blob storage",
                extra={"filename": file.filename, "bytes": len(content)},
            )
            blob_client.upload_blob(content, overwrite=True)
            logger.info("Upload successful", extra={"filename": file.filename})
            return {"filename": file.filename}
        except Exception as e:
            logger.exception(
                "Error uploading file", extra={"filename": file.filename}
            )
            raise HTTPException(
                status_code=500, detail=f"Error uploading file: {str(e)}"
            )
    except Exception as e:
        if not isinstance(e, HTTPException):
            logger.exception(
                "Unexpected error handling upload", extra={"filename": file.filename}
            )
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
        else:
            raise e


@app.get("/status/{filename}")
def get_status(filename: str):
    logger.info("Checking status", extra={"filename": filename})
    report_blob_name = filename.replace(".pdf", "_report.json")
    try:
        blob_client = blob_service_client.get_blob_client(
            container=REPORT_CONTAINER, blob=report_blob_name
        )
        try:
            data = blob_client.download_blob().readall()
            logger.info("Found report", extra={"filename": filename})
            return JSONResponse(content={"ready": True, "report": data.decode()})
        except Exception as e:
            logger.info(
                "Report not ready yet",
                extra={"filename": filename, "reason": str(e)},
            )
            return JSONResponse(content={"ready": False})
    except Exception as e:
        logger.exception("Error checking status", extra={"filename": filename})
        return JSONResponse(content={"ready": False, "error": str(e)})
