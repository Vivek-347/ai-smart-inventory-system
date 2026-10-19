"""Hybrid purchase invoice extraction: Gemini first, then local PDF/image OCR.

Local OCR is best-effort. Its structured output must be reviewed before import.
"""
import os, json, re
from dotenv import load_dotenv
from google import genai

load_dotenv()
_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=_key) if _key else None


def _empty_bill(error, source="local OCR"):
    return {"supplier": "", "invoice_number": "", "invoice_date": "", "items": [], "_error": error, "_source": source}


def _clean_items(items):
    clean_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        product = str(item.get("product", "")).strip()
        if not product:
            continue
        clean = dict(item)
        clean["product"] = product
        try: clean["quantity"] = max(1, int(float(item.get("quantity", 1) or 1)))
        except (ValueError, TypeError): clean["quantity"] = 1
        try: clean["cost_price"] = max(0.0, float(item.get("cost_price", 0) or 0))
        except (ValueError, TypeError): clean["cost_price"] = 0.0
        try: clean["gst"] = float(item.get("gst", 18) or 18)
        except (ValueError, TypeError): clean["gst"] = 18.0
        for key, default in (("brand", ""), ("category", "General"), ("sub_category", ""), ("model_number", ""), ("color", ""), ("warranty", "")):
            clean.setdefault(key, default)
        clean_items.append(clean)
    return clean_items


def _read_local_text(filepath):
    """Extract embedded PDF text; use Tesseract for scanned PDFs or images."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(filepath)
            text = "\n".join(page.get_text("text") for page in doc).strip()
            if len(text) >= 40:
                return text
            # Scanned PDF: OCR each page. Tesseract executable must be installed.
            import pytesseract
            from PIL import Image
            import io
            pages = []
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                pages.append(pytesseract.image_to_string(image))
            return "\n".join(pages).strip()
        except ImportError as exc:
            raise RuntimeError("Local PDF OCR dependencies are missing. Install PyMuPDF and pytesseract.") from exc
    try:
        from PIL import Image
        import pytesseract
        return pytesseract.image_to_string(Image.open(filepath)).strip()
    except ImportError as exc:
        raise RuntimeError("Local image OCR dependencies are missing. Install Pillow and pytesseract.") from exc


def _parse_local_invoice(text):
    """Conservative heuristic parser; returns items only when product/price rows are found."""
    if not text or len(text.strip()) < 10:
        return _empty_bill("Local OCR could not read enough text from this invoice.")
    supplier = ""
    lines = [re.sub(r"\s+", " ", x).strip(" |\t") for x in text.splitlines()]
    lines = [x for x in lines if x]
    for line in lines[:6]:
        if len(line) > 2 and not re.search(r"invoice|tax invoice|gstin|phone|email|bill to|ship to", line, re.I):
            supplier = line[:120]
            break
    inv = re.search(r"(?:invoice\s*(?:no|number|#)|bill\s*(?:no|number|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{2,})", text, re.I)
    date = re.search(r"(?:invoice\s*date|date)\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})", text, re.I)
    items = []
    # Only accept rows with a plausible trailing quantity and unit price; do not guess when unclear.
    for line in lines:
        if re.search(r"subtotal|grand total|taxable|cgst|sgst|igst|round.?off|shipping|discount|total amount|amount in words|hsn", line, re.I):
            continue
        nums = re.findall(r"(?<![A-Za-z])\d+(?:,\d{3})*(?:\.\d{1,2})?", line)
        if len(nums) < 2:
            continue
        # Typical item rows end in quantity, unit price, line total (or quantity and price).
        try:
            vals = [float(n.replace(",", "")) for n in nums]
            qty = int(vals[-3]) if len(vals) >= 3 and vals[-3].is_integer() and 0 < vals[-3] <= 100000 else (int(vals[-2]) if vals[-2].is_integer() and 0 < vals[-2] <= 100000 else None)
            price = vals[-2] if len(vals) >= 3 and qty == int(vals[-3]) else vals[-1]
            # Exclude improbable or ambiguous rows.
            if not qty or price <= 0 or price > 100000000:
                continue
            product = line[:line.rfind(nums[-3] if len(nums) >= 3 else nums[-2])].strip(" .:-|\t")
            product = re.sub(r"^\d+\s+", "", product).strip()
            if len(product) < 2 or re.search(r"invoice|gst|phone|total|date", product, re.I):
                continue
            items.append({"product": product[:150], "brand": "", "category": "General", "sub_category": "", "model_number": "", "color": "", "warranty": "", "gst": 18, "quantity": qty, "cost_price": price})
        except (ValueError, IndexError):
            continue
    items = _clean_items(items)
    if not items:
        return _empty_bill("Gemini was unavailable and local OCR could not confidently identify product rows. Please enter invoice items manually; no stock was changed.")
    return {"supplier": supplier, "invoice_number": inv.group(1) if inv else "", "invoice_date": date.group(1) if date else "", "items": items, "_source": "Local OCR — please verify all fields"}


def _extract_with_gemini(filepath):
    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    uploaded_file = client.files.upload(file=filepath)
    prompt = '''You are an enterprise purchase invoice OCR system. Extract only visibly present information; never invent products. Return ONLY valid JSON, no markdown, schema: {"supplier":"","invoice_number":"","invoice_date":"","items":[{"product":"","brand":"","category":"General","sub_category":"","model_number":"","color":"","warranty":"","gst":18,"quantity":1,"cost_price":0}]}. One item per actual invoice line. Ignore totals, tax-summary rows, shipping, discounts, bank details, HSN-only rows and terms. Missing brand/model/color/warranty use empty string; missing GST 18, quantity 1, cost_price 0. Cost price should be per-unit price, not line total, when clear.'''
    response = client.models.generate_content(model="gemini-2.5-flash", contents=[uploaded_file, prompt])
    raw = (response.text or "").strip().replace("```json", "").replace("```", "").strip()
    bill = json.loads(raw)
    if not isinstance(bill, dict) or not isinstance(bill.get("items", []), list):
        raise ValueError("Gemini returned an invalid invoice format.")
    items = _clean_items(bill.get("items", []))
    if not items:
        raise ValueError("Gemini could not identify invoice products.")
    bill["items"] = items
    bill["_source"] = "Gemini AI — please verify before import"
    return bill


def extract_purchase_bill(filepath):
    if not os.path.isfile(filepath):
        return _empty_bill("The uploaded invoice file was not found.")
    gemini_error = None
    try:
        return _extract_with_gemini(filepath)
    except Exception as exc:
        gemini_error = str(exc).lower()
        print("Gemini purchase OCR unavailable; trying local OCR:", repr(exc))
    try:
        text = _read_local_text(filepath)
        bill = _parse_local_invoice(text)
        if bill.get("items"):
            bill["_gemini_fallback"] = True
            return bill
        return bill
    except Exception as exc:
        print("Local purchase OCR failed:", repr(exc))
        if any(token in gemini_error for token in ("429", "quota", "resource_exhausted", "rate limit")):
            reason = "Gemini quota is exhausted and local OCR could not run. Install/configure local OCR dependencies and verify this invoice manually."
        else:
            reason = "Both Gemini and local OCR were unavailable. Verify this invoice manually."
        return _empty_bill(reason)
