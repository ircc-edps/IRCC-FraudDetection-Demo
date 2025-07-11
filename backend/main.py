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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info(f"Container {container_name} is ready")
        return True
    except Exception as e:
        logger.error(f"Error ensuring container {container_name} exists: {str(e)}")
        return False


# Create containers at startup
@app.on_event("startup")
def startup_event():
    logger.info("Ensuring blob containers exist...")
    ensure_container_exists(DOCUMENTS_CONTAINER)
    logger.info("Startup completed.")


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    logger.info(f"Received upload request for file: {file.filename}")
    try:
        # Check if file has allowed extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ALLOWED_FILE_EXTENSIONS:
            allowed_formats = ", ".join(ALLOWED_FILE_EXTENSIONS)
            logger.warning(
                f"File {file.filename} rejected: invalid format. Allowed formats: {allowed_formats}"
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
            logger.info(f"Reading content from uploaded file: {file.filename}")
            content = await file.read()
            logger.info(f"Uploading {len(content)} bytes to blob storage")
            blob_client.upload_blob(content, overwrite=True)
            logger.info(f"Upload successful for file: {file.filename}")
            return {"filename": file.filename}
        except Exception as e:
            logger.error(f"Error uploading file {file.filename}: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error uploading file: {str(e)}"
            )
    except Exception as e:
        if not isinstance(e, HTTPException):
            logger.error(f"Unexpected error in upload: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
        else:
            raise e


@app.get("/status/{filename}")
def get_status(filename: str):
    logger.info(f"Checking status for file: {filename}")
    report_blob_name = filename.replace(".pdf", "_report.json")
    try:
        blob_client = blob_service_client.get_blob_client(
            container=REPORT_CONTAINER, blob=report_blob_name
        )
        try:
            data = blob_client.download_blob().readall()
            logger.info(f"Found report for file: {filename}")
            return JSONResponse(content={"ready": True, "report": data.decode()})
        except Exception as e:
            logger.info(f"Report not ready for file: {filename}. Reason: {str(e)}")
            return JSONResponse(content={"ready": False})
    except Exception as e:
        logger.error(f"Error checking status for {filename}: {str(e)}")
        return JSONResponse(content={"ready": False, "error": str(e)})
