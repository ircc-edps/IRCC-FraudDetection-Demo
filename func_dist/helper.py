import fitz
import os
import time
from PIL import Image
from PyPDF2 import PdfReader

ALLOWED_FORMATS = ["JPEG", "PNG", "PDF"]
MIN_DPI = 300


def validate_file(file_path):
    ext = file_path.split(".")[-1].upper()
    if ext not in ALLOWED_FORMATS:
        return False, "Unsupported file format."

    if ext in ["JPEG", "PNG"]:
        with Image.open(file_path) as img:
            dpi = img.info.get("dpi", (0, 0))[0]
            if dpi < MIN_DPI:
                return False, f"Image DPI too low: {dpi} (minimum {MIN_DPI})"
    elif ext == "PDF":
        with open(file_path, "rb") as f:
            reader = PdfReader(f)
            # Optionally, check PDF quality here
            pass

    return True, "File meets quality standards."


# def pdf_to_jpg(pdf_path, output_folder):
#     pdf_document = fitz.open(pdf_path)
#     for page_number in range(len(pdf_document)):
#         page = pdf_document[page_number]
#         pix = page.get_pixmap()
#         output_path = f"{output_folder}/page_{page_number + 1}.jpg"
#         pix.save(output_path)
#     pdf_document.close()


# TODO: Modify this function to handle a stream of PDF data
def pdf_to_jpg(pdf_path, output_folder, dpi=300):
    pdf_document = fitz.open(pdf_path)
    scale = dpi / 72  # 72 is the default PDF DPI
    matrix = fitz.Matrix(scale, scale)
    os.makedirs(output_folder, exist_ok=True)
    for page_number in range(len(pdf_document)):
        page = pdf_document[page_number]
        pix = page.get_pixmap(matrix=matrix)
        output_path = os.path.join(output_folder, f"page_{page_number + 1}.jpg")
        pix.save(output_path)
    pdf_document.close()


def extract_metadata(file_path):
    metadata = {
        "file_name": os.path.basename(file_path),
        "file_size": os.path.getsize(file_path),
        "created_time": time.ctime(os.path.getctime(file_path)),
        "modified_time": time.ctime(os.path.getmtime(file_path)),
    }
    ext = file_path.split(".")[-1].lower()
    if ext in ["jpg", "jpeg", "png"]:
        with Image.open(file_path) as img:
            metadata["format"] = img.format
            metadata["mode"] = img.mode
            metadata["size"] = img.size
            metadata["info"] = img.info
    elif ext == "pdf":
        with open(file_path, "rb") as f:
            reader = PdfReader(f)
            metadata["pdf_info"] = reader.metadata
            metadata["num_pages"] = len(reader.pages)
    return metadata
