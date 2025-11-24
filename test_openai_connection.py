#!/usr/bin/env python3
"""
Test script to verify Azure OpenAI connection with current configuration.
"""

import os
import json
import logging
from openai import AzureOpenAI

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

def test_azure_openai_connection():
    """Test the Azure OpenAI connection with minimal API call."""

    # Read configuration from local.settings.json
    with open("local.settings.json", "r") as f:
        settings = json.load(f)
        values = settings["Values"]

    # Extract configuration
    endpoint = values["AZURE_OPENAI_ENDPOINT"]
    api_key = values["AZURE_OPENAI_KEY"]
    deployment = values["AZURE_OPENAI_DEPLOYMENT"]
    api_version = values["API_VERSION"]

    logging.info("=" * 60)
    logging.info("Testing Azure OpenAI Connection")
    logging.info("=" * 60)
    logging.info(f"Endpoint:    {endpoint}")
    logging.info(f"Deployment:  {deployment}")
    logging.info(f"API Version: {api_version}")
    logging.info("=" * 60)

    try:
        # Initialize client
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            max_retries=2
        )

        logging.info("Client initialized successfully")

        # Make a minimal test call
        logging.info("Sending test message...")
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Connection successful!' in 5 words or less."}
            ],
            max_tokens=20,
            temperature=0
        )

        # Extract response
        result = response.choices[0].message.content

        logging.info("=" * 60)
        logging.info("✅ SUCCESS! Connection is working!")
        logging.info(f"Response: {result}")
        logging.info("=" * 60)

        # Test with a small image to verify multimodal capability
        logging.info("\nTesting image capability...")

        # Create a simple 1x1 white pixel image for testing
        import base64
        from PIL import Image
        import io

        img = Image.new('RGB', (1, 1), color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('ascii')

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What color is this image? Answer in one word."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                    ]
                }
            ],
            max_tokens=10
        )

        result = response.choices[0].message.content
        logging.info(f"Image test response: {result}")
        logging.info("✅ Image processing capability confirmed!")

        return True

    except Exception as e:
        logging.error("=" * 60)
        logging.error("❌ FAILED! Connection error occurred")
        logging.error(f"Error type: {type(e).__name__}")
        logging.error(f"Error details: {str(e)}")
        logging.error("=" * 60)

        if "APIConnectionError" in str(type(e).__name__):
            logging.error("This appears to be a connection/network issue.")
            logging.error("Possible causes:")
            logging.error("  - Incorrect endpoint URL")
            logging.error("  - Network/firewall blocking the connection")
            logging.error("  - Azure OpenAI service is down")
        elif "AuthenticationError" in str(type(e).__name__):
            logging.error("This appears to be an authentication issue.")
            logging.error("Check your API key is correct and active.")
        elif "NotFoundError" in str(type(e).__name__):
            logging.error("The deployment or endpoint was not found.")
            logging.error("Verify the deployment name and endpoint URL.")

        return False

if __name__ == "__main__":
    success = test_azure_openai_connection()
    exit(0 if success else 1)