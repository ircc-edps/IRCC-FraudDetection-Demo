
import os
import base64
from openai import AzureOpenAI
from PIL import Image, ImageDraw
import json
import re

"""

"""

endpoint = os.getenv("ENDPOINT_URL", "https://ircc-openai.openai.azure.com/")
deployment = os.getenv("DEPLOYMENT_NAME", "gpt-4o")
subscription_key = os.getenv("AZURE_OPENAI_API_KEY", "REPLACE_WITH_YOUR_KEY_VALUE_HERE")

# Initialize Azure OpenAI client with key-based authentication
client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=subscription_key,
    api_version="2025-01-01-preview",
)

#Prepare the chat prompt
chat_prompt = [
    {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": (
                    "You are a fraud detection service. Given a series of chunks that together make up one document, "
                    "detect if there has been any doctoring to the image. In your response, specify which chunks were doctored. "
                    "You will be looking for signs of altercation like font differences, inconsistent text, inconsistent colors, inconsistent spacing, "
                    "Don't worry about any black chunks, as those were due to the image being being chunked. "
                    "You will also provide a confidence level of your response on a scale of 1 to 10, with 10 being the most confident. "
                    "Finally, finish the analysis with an object where the contents look like this: "
                    "{\"chunks\": [1, 2, 3], \"confidence\": 8, \"reasoning\": \"The chunks were cropped and the metadata was altered.\"}"
                )
            }
        ]
    }
]


messages = chat_prompt




def chunk_image(image_path, chunk_size):
    # Open the image
    img = Image.open(image_path)
    #img = img.resize((400, 600), Image.Resampling.LANCZOS)
    img_width, img_height = img.size
    print(img.size)
    # Calculate the number of chunks in each dimension
    chunks_x = img_width // chunk_size + 1
    chunks_y = img_height // chunk_size + 1

    # Create a list to hold the chunked images
    chunked_images = []
    chunked_dims = []
    # Loop through the image and create chunks
    for y in range(0, chunks_y):
        for x in range(0, chunks_x):
            left = x * chunk_size
            upper = y * chunk_size
            right = left + chunk_size
            lower = upper + chunk_size

            # Crop the image to create a chunk
            chunk = img.crop((left, upper, right, lower))
            chunked_images.append(chunk)
            chunked_dims.append((left, upper, right, lower))
    return chunked_images, chunked_dims


# Chunk the image 
image_path= 'lorem_ipsum_2.jpg' # Replace with your image path
chunk_size = 300 

chunks, dims = chunk_image(image_path, chunk_size)

# Save each chunk as a separate image file
for i, chunk in enumerate(chunks):
    chunk.save(f'./chunked/chunk_{i}.png')

print(f"Image has been broken into {len(chunks)} chunks and saved as separate files.")

# Pass the image chunks to the model

# IMAGE_PATH = "YOUR_IMAGE_PATH"
# encoded_image = base64.b64encode(open(IMAGE_PATH, 'rb').read()).decode('ascii')


# Define the folder containing the images
folder_path = "chunked"

# Iterate through each file in the folder
for filename in os.listdir(folder_path):
    if filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
        image_path = os.path.join(folder_path, filename)
        encoded_image = base64.b64encode(open(image_path, 'rb').read()).decode('ascii')
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{encoded_image}"
                    }
                }
            ]
        })
        print(f"Encoded image for {filename}: {encoded_image}")


# Process the response, making note of which chunk was said to be doctored by the model 

# Generate the completion
completion = client.chat.completions.create(
    model=deployment,
    messages=messages,
    max_tokens=800,
    temperature=0.7,
    top_p=0.95,
    frequency_penalty=0,
    presence_penalty=0,
    stop=None,
    stream=False
)

print(completion.to_json())

response = completion.choices[0].message.content

def extract_tampered_chunks(message_content):
    # Use regex to find the JSON object within the message content
    json_match = re.search(r'\{.*\}', message_content, re.DOTALL)

    tampered_chunks = []

    if json_match:
        json_str = json_match.group(0)
        # Parse the JSON string
        json_obj = json.loads(json_str)
        # Extract the chunk
        tampered_chunks = json_obj.get("chunks", [])

    return tampered_chunks

tampered_chunks = extract_tampered_chunks(response)

print(f"Tampered chunks identified: {tampered_chunks}")

# Apply a heat layering to the image to highlight the doctored areas

def overlay_boxes(image_path):
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

image_path= 'lorem_ipsum_2.jpg'
overlay_boxes(image_path)
