import json
from ai import ask_ai


def find_best_product(ocr_product, database_products):

    products = "\n".join(database_products)

    prompt = f"""
    You are an Enterprise Inventory AI.

    Your job is to compare ONE OCR product with an existing product database.

    OCR Product

    Name : {ocr_product["product"]}

    Brand : {ocr_product["brand"]}

    Category : {ocr_product["category"]}

    Model Number : {ocr_product["model_number"]}

    Database Products

    {products}

    Rules

    1. Model Number is the HIGHEST priority.
    2. If Model Numbers are different, NEVER match.
    3. Same Model Number + Same Brand = Match.
    4. Same Name but Different Model Number = NEW PRODUCT.
    5. Different Brand = NEW PRODUCT.
    6. Different Category = NEW PRODUCT.
    7. Ignore upper/lower case.
    8. Ignore extra spaces.
    9. Ignore '-', '_', '/' differences.
    10. Ignore color differences.
    11. Ignore quantity.
    12. Ignore packing size.
    13. Ignore words like New, Latest, Offer, Combo, Premium, Edition.
    14. Small spelling mistakes are acceptable.
    15. If confidence is below 95%, return NEW PRODUCT.
    16. Return ONLY valid JSON.

    Return ONLY

    {{
        "match": "",
        "confidence": 0
    }}
    """

    answer = ask_ai(prompt)

    answer = answer.replace("```json", "")
    answer = answer.replace("```", "").strip()

    try:
        return json.loads(answer)

    except Exception:
        return {
            "match": "NEW PRODUCT",
            "confidence": 0
        }