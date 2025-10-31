import azure.functions as func
import json
import logging
import base64
from typing import Dict, List
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
from datetime import datetime
import uuid
import re
import os
from PIL import Image, ImageDraw
import io
from helper import pdf_to_jpg, validate_file, extract_metadata

app = func.FunctionApp()

# Configuration from environment variables
STORAGE_CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_KEY"]
AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT"]
API_VERSION = os.environ.get("API_VERSION")

CHUNK_SIZE = 150  # Size of each chunk in pixels
OUTPUT_FOLDER = "application"


# Chunk it in horizontal strips
def chunk_image(image_path, chunk_size):

    img = Image.open(image_path)
    img_width, img_height = img.size

    # Calculate the number of chunks in each dimension
    chunks_y = (img_height + chunk_size - 1) // chunk_size

    # Create a list to hold the chunked images
    chunked_images = []
    chunked_dims = []
    # Loop through the image and create chunks
    for y in range(0, chunks_y):
        for x in range(1):
            left = x * chunk_size
            upper = y * chunk_size
            right = left + img_width
            lower = upper + chunk_size

            # Crop the image to create a chunk
            chunk = img.crop((left, upper, right, lower))
            chunked_images.append(chunk)
            chunked_dims.append((left, upper, right, lower))
    return chunked_images, chunked_dims


def overlay_boxes(image_path, tampered_chunks: List[int], dims: List[tuple]):
    # Open the image
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img, "RGBA")

    # Define the colors with 50% transparency
    green_color = (0, 255, 0, 127)  # RGBA
    red_color = (255, 0, 0, 128)
    ind = 0
    # Draw the boxes
    for dim in dims:
        if (ind + 1) in tampered_chunks:
            draw.rectangle(dim, fill=red_color)
            draw.rectangle(dim, outline=(0, 0, 0, 127), width=3)
        else:
            draw.rectangle(dim, fill=green_color)
            draw.rectangle(dim, outline=(0, 0, 0, 127), width=3)
        ind = ind + 1
    # Save the image with overlay
    img.save("overlay_image.png")


def analyze_document_with_openai(folder_path: str) -> Dict:
    """Analyze the document using Azure OpenAI."""
    try:
        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version=API_VERSION,
        )

        chat_prompt = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"""You are a fraud detection service that analyzes images of documents to detect any tampering or doctoring.

                            You are given a series of chunks that together make up one document.

                            Detect if there has been any doctoring to the image. You are looking for the following:
                            - Signs of alteration:
                                - Inconsistent fonts
                                - Inconsistent text
                                - Inconsistent colors
                                - Inconsistent spacing

                            - Highlight any anomalies:
                                - Mismatched names
                                - Incorrect or fraudulent content
                                - Any other irregularities.
                            
                            Ignore any large black chunks, as those were an artifact of the image being chunked.

                            You must conclude your analysis with a JSON object in the following format:
                            {{"suspicious_chunks": [1, 2, 3], "explanation": [{{"chunk": 1, "confidence": 9, "risk": "high", "reasoning": "Inconsistent fonts and Photoshop artifacts."}}, {{"chunk": 3, "confidence": 6, "risk": "medium", "reasoning": "Mismatched metadata."}}], "overall_risk": "high"}}
                        
                            If no suspicious activity is detected, respond with an empty JSON object: {{"suspicious_chunks": [], "explanation": [], "overall_risk": "low"}}
                        """
                        ),
                    }
                ],
            }
        ]

        messages = chat_prompt

        # Iterate through each file in the folder
        for filename in os.listdir(folder_path):
            if filename.endswith((".png", ".jpg", ".jpeg")):
                image_path = os.path.join(folder_path, filename)
                encoded_image = base64.b64encode(open(image_path, "rb").read()).decode(
                    "ascii"
                )
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{encoded_image}",
                                    # "detail": f"Chunk filename: {filename}"
                                },
                            }
                        ],
                    }
                )

        # Generate the completion
        completion = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=messages,
            max_tokens=800,
            temperature=0.7,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None,
            stream=False,
        )

        return completion.choices[0].message.content

    except Exception as e:
        logging.error(f"Error analyzing document: {str(e)}")
        return {"error": str(e)}


def extract_analysis_data(message_content):
    """Extract and parse the JSON analysis data from OpenAI response."""
    try:
        # First, try to find JSON within markdown code blocks
        markdown_json_match = re.search(
            r"```json\s*(\{.*?\})\s*```", message_content, re.DOTALL
        )

        if markdown_json_match:
            json_str = markdown_json_match.group(1)
        else:
            # Fallback: try to find any JSON object in the content
            json_match = re.search(r"\{.*\}", message_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                return {
                    "suspicious_chunks": [],
                    "explanation": [],
                    "overall_risk": "low",
                }

        # Parse the JSON string
        analysis_data = json.loads(json_str)

        # Ensure all required fields are present
        if "suspicious_chunks" not in analysis_data:
            analysis_data["suspicious_chunks"] = []
        if "explanation" not in analysis_data:
            analysis_data["explanation"] = []
        if "overall_risk" not in analysis_data:
            analysis_data["overall_risk"] = "low"

        return analysis_data

    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON from OpenAI response: {e}")
        return {"suspicious_chunks": [], "explanation": [], "overall_risk": "low"}
    except Exception as e:
        logging.error(f"Error extracting analysis data: {e}")
        return {"suspicious_chunks": [], "explanation": [], "overall_risk": "low"}


def save_json_to_blob(
    blob_service_client: BlobServiceClient,
    container_name: str,
    blob_name: str,
    data: Dict,
):
    """Save JSON data to a blob in the specified container."""
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=blob_name
    )
    blob_client.upload_blob(json.dumps(data, indent=2), overwrite=True)
    logging.info(f"Saved JSON to {container_name}/{blob_name}")


def upload_file_to_blob(
    blob_service_client: BlobServiceClient,
    container_name: str,
    blob_name: str,
    file_path: str,
):
    """Upload a file to blob storage."""
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=blob_name
    )
    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)
    logging.info(f"Uploaded file {file_path} to {container_name}/{blob_name}")


@app.function_name(name="ProcessDocuments")
@app.blob_trigger(
    arg_name="inputBlob", path="documents/{name}", connection="AzureWebJobsStorage"
)
@app.blob_output(
    arg_name="reportOutput",
    path="reports/{name}_report.json",
    connection="AzureWebJobsStorage",
)
def process_documents(inputBlob: func.InputStream, reportOutput: func.Out[str]):
    """Azure Function to process application and generate a fraud detection report."""
    logging.info(f"Processing blob: {inputBlob.name}")

    try:
        # Initialize Blob Service Client
        blob_service_client = BlobServiceClient.from_connection_string(
            STORAGE_CONNECTION_STRING
        )

        pdf_data = inputBlob.read()

        temp_pdf_path = "temp.pdf"
        with open(temp_pdf_path, "wb") as f:
            f.write(pdf_data)

        # Store metadata in blob storage
        meta = extract_metadata(temp_pdf_path)
        # with open("pdf_metadata.json", "w") as f:
        #     json.dump(meta, f, indent=2)

        save_json_to_blob(
            blob_service_client,
            "metadata",
            inputBlob.name.replace("documents/", "").replace(".pdf", "_metadata.json"),
            # "pdf_metadata.json",
            meta,
        )

        pdf_to_jpg("temp.pdf", OUTPUT_FOLDER, dpi=300)

        IMAGE_PATH = os.path.join(OUTPUT_FOLDER, "page_1.jpg")

        chunks, dims = chunk_image(IMAGE_PATH, CHUNK_SIZE)

        # Assuming the first page is the one we want to analyze
        IMAGE_PATH = os.path.join(OUTPUT_FOLDER, "page_1.jpg")

        # Save each chunk as a separate image file
        for i, chunk in enumerate(chunks):
            chunk.save(f"./chunked/chunk_{i}.png")

        # print(
        #     f"Image has been broken into {len(chunks)} chunks and saved as separate files."
        # )

        # 2. Pass the image chunks to the model
        folder_path = "chunked"
        openai_response = analyze_document_with_openai(folder_path)

        # print(f"OpenAI response: {openai_response}")

        if isinstance(openai_response, dict) and "error" in openai_response:
            logging.error(f"OpenAI analysis failed: {openai_response['error']}")
            raise RuntimeError(f"OpenAI analysis failed: {openai_response['error']}")

        # Extract and parse the analysis data
        analysis_data = extract_analysis_data(openai_response)

        tampered_chunks = analysis_data.get("suspicious_chunks", [])
        print(f"Tampered chunks identified: {tampered_chunks}")

        overlay_boxes(IMAGE_PATH, tampered_chunks=tampered_chunks, dims=dims)

        # Upload overlay image to blob storage
        overlay_blob_name = inputBlob.name.replace("documents/", "").replace(
            ".pdf", "_overlay.png"
        )
        upload_file_to_blob(
            blob_service_client,
            "overlay-images",
            overlay_blob_name,
            "overlay_image.png",
        )

        # Prepare report JSON
        report_data = {
            "form_id": inputBlob.name,
            "status": "success",
            "blob_name": inputBlob.name,
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": str(uuid.uuid4()),
            "overlay_image_url": f"https://{blob_service_client.account_name}.blob.core.windows.net/overlay-images/{overlay_blob_name}",
            "tampered_chunks": tampered_chunks,
            "response": analysis_data,
        }

        # Save report to form-reports container
        report_blob_name = inputBlob.name.replace("documents/", "").replace(
            ".pdf", "_report.json"
        )
        save_json_to_blob(blob_service_client, "reports", report_blob_name, report_data)
        reportOutput.set(json.dumps(report_data, indent=2))

        logging.info(f"Successfully processed {inputBlob.name}")

    except Exception as e:
        logging.error(f"Error processing {inputBlob.name}: {str(e)}")
        report_data = {
            "form_id": inputBlob.name,
            "status": "error",
            "blob_name": inputBlob.name,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": str(uuid.uuid4()),
        }
        report_blob_name = inputBlob.name.replace("documents/", "").replace(
            ".pdf", "_report.json"
        )
        blob_service_client = BlobServiceClient.from_connection_string(
            STORAGE_CONNECTION_STRING
        )
        save_json_to_blob(blob_service_client, "reports", report_blob_name, report_data)
        reportOutput.set(json.dumps(report_data, indent=2))
        raise
