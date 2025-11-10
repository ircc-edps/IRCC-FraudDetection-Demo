import os
import time
import logging
import uuid
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from azure.storage.blob import BlobServiceClient, ContainerClient
from azure.core.exceptions import ResourceExistsError
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
    logger.debug(
        "Ensuring container exists",
        extra={"container": container_name},
    )
    container_client = blob_service_client.get_container_client(container_name)
    try:
        container_client.create_container()
        logger.debug("Created container", extra={"container": container_name})
    except ResourceExistsError:
        logger.debug(
            "Container already exists",
            extra={"container": container_name},
        )
    except Exception:
        logger.exception(
            "Error ensuring container exists",
            extra={"container": container_name},
        )
        raise
    return container_client


# Create containers at startup
@app.on_event("startup")
def startup_event():
    logger.info("Starting backend service")
    ensure_container_exists(DOCUMENTS_CONTAINER)
    logger.info("Startup completed")


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    operation_id = str(uuid.uuid4())
    logger.info(
        "Received upload request",
        extra={"file_name": file.filename, "operation_id": operation_id},
    )
    try:
        # Check if file has allowed extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ALLOWED_FILE_EXTENSIONS:
            allowed_formats = ", ".join(ALLOWED_FILE_EXTENSIONS)
            logger.warning(
                "Rejected upload due to invalid format",
                extra={
                    "file_name": file.filename,
                    "allowed_formats": allowed_formats,
                    "operation_id": operation_id,
                },
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
                extra={"file_name": file.filename, "operation_id": operation_id},
            )
            content = await file.read()
            logger.info(
                "Uploading file to blob storage",
                extra={
                    "file_name": file.filename,
                    "bytes": len(content),
                    "operation_id": operation_id,
                },
            )
            blob_client.upload_blob(content, overwrite=True)
            logger.info(
                "Upload successful",
                extra={"file_name": file.filename, "operation_id": operation_id},
            )
            return {"filename": file.filename}
        except Exception as e:
            logger.exception(
                "Error uploading file",
                extra={"file_name": file.filename, "operation_id": operation_id},
            )
            raise HTTPException(
                status_code=500, detail=f"Error uploading file: {str(e)}"
            )
    except Exception as e:
        if not isinstance(e, HTTPException):
            logger.exception(
                "Unexpected error handling upload",
                extra={"file_name": file.filename, "operation_id": operation_id},
            )
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
        else:
            raise e


@app.get("/status/{filename}")
def get_status(filename: str):
    request_id = str(uuid.uuid4())
    logger.info(
        "Checking status",
        extra={"file_name": filename, "request_id": request_id},
    )
    report_blob_name = filename.replace(".pdf", "_report.json")
    try:
        blob_client = blob_service_client.get_blob_client(
            container=REPORT_CONTAINER, blob=report_blob_name
        )
        try:
            data = blob_client.download_blob().readall()
            logger.info(
                "Found report",
                extra={
                    "file_name": filename,
                    "bytes": len(data),
                    "request_id": request_id,
                },
            )
            return JSONResponse(content={"ready": True, "report": data.decode()})
        except Exception as e:
            logger.info(
                "Report not ready yet",
                extra={
                    "file_name": filename,
                    "reason": str(e),
                    "request_id": request_id,
                },
            )
            return JSONResponse(content={"ready": False})
    except Exception as e:
        logger.exception(
            "Error checking status",
            extra={"file_name": filename, "request_id": request_id},
        )
        return JSONResponse(content={"ready": False, "error": str(e)})
