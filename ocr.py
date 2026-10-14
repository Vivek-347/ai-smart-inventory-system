import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


def extract_purchase_bill(filepath):

    uploaded_file = client.files.upload(
        file=filepath
    )

    prompt = """
    You are an Enterprise Purchase Invoice OCR AI.

    Your task is to extract purchase invoice data accurately.

    IMPORTANT RULES

    1. Return ONLY valid JSON.
    2. Never return markdown.
    3. Never explain anything.
    4. Never invent products.
    5. Ignore logos.
    6. Ignore QR Codes.
    7. Ignore Barcodes.
    8. Ignore HSN Codes.
    9. Ignore GST Summary.
    10. Ignore CGST/SGST/IGST rows.
    11. Ignore Total Amount.
    12. Ignore Grand Total.
    13. Ignore Discount rows.
    14. Ignore Freight/Shipping.
    15. Ignore Bank Details.
    16. Ignore Terms & Conditions.

    For EVERY product detect:

    • Product Name
    • Brand (if available)
    • Category
    • Sub Category
    • Model Number
    • Color
    • Warranty
    • GST %
    • Quantity
    • Cost Price

    Rules

    If Brand is missing
    return ""

    If Category cannot be determined
    return "General"

    If Model Number missing
    return ""

    If Color missing
    return ""

    If Warranty missing
    return ""

    If GST missing
    return 18

    If Quantity missing
    return 1

    If Cost Price missing
    return 0

    Never stop because fields are missing.

    Always return JSON.

    Format

    {
    "supplier":"",
    "invoice_number":"",
    "invoice_date":"",
    "items":[
    {
    "product":"",
    "brand":"",
    "category":"",
    "sub_category":"",
    "model_number":"",
    "color":"",
    "warranty":"",
    "gst":18,
    "quantity":0,
    "cost_price":0
    }
    ]
    }
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            uploaded_file,
            prompt
        ]
    )

    text = response.text.strip()

    text = text.replace("```json", "")
    text = text.replace("```", "")
    text = text.strip()

    print("\n========== GEMINI OCR ==========\n")
    print(text)
    print("\n===============================\n")

    try:

        bill = json.loads(text)

    except Exception as e:

        print("JSON Error :", e)

        bill = {
            "supplier": "",
            "invoice_number": "",
            "invoice_date": "",
            "items": []
        }

    return bill