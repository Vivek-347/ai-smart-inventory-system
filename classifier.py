import json
from ai import ask_ai


def detect_product_details(product_name):

    prompt = f"""
You are an Inventory Product Classification AI.

Product

{product_name}

Return ONLY JSON.

Rules

1. Detect Brand.
2. Detect Category.
3. Detect Sub Category.
4. Detect Model Number.
5. Detect Color.
6. Detect Warranty if obvious.
7. GST:
   Electronics = 18
   Accessories = 18
   Computer Parts = 18
   Cable = 18
   Others = 18

Category must be one of:

Computer
Laptop
Desktop
Mouse
Keyboard
Monitor
Printer
Scanner
RAM
SSD
Hard Disk
Graphics Card
Motherboard
Processor
Networking
Router
Switch
CCTV
Mobile
Tablet
Speaker
Headphone
Power Supply
Cable
Accessories
General

Return ONLY

{{
"brand":"",
"category":"General",
"sub_category":"",
"model_number":"",
"color":"",
"warranty":"",
"gst":18
}}
"""

    answer = ask_ai(prompt)

    answer = answer.replace("```json", "")
    answer = answer.replace("```", "").strip()

    try:
        return json.loads(answer)

    except:

        return {
            "brand": "",
            "category": "General",
            "sub_category": "",
            "model_number": "",
            "color": "",
            "warranty": "",
            "gst": 18
        }