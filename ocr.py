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
    """Parse local invoice text conservatively, prioritizing table rows over random numbers."""
    if not text or len(text.strip()) < 10:
        return _empty_bill("Local OCR could not read enough text from this invoice.")

    lines = [re.sub(r"\s+", " ", x).strip(" |\t") for x in text.splitlines()]
    lines = [x for x in lines if x]
    normalized = "\n".join(lines)

    supplier = ""
    for line in lines[:8]:
        if (len(line) > 2 and not re.search(
            r"invoice|tax invoice|gstin|phone|mobile|email|bill to|ship to|office\s*\d", line, re.I
        )):
            supplier = line[:120]
            break

    inv = re.search(r"(?:invoice\s*(?:no|number|#)|bill\s*(?:no|number|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{2,})", normalized, re.I)
    date = re.search(r"(?:invoice\s*date|date)\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})", normalized, re.I)

    items = []
    # PDF text extraction often puts each table cell on its own line. Parse only
    # rows inside a clearly identified item table and require HSN + Qty + Rate + Amount.
    header_idx = None
    # Support both flattened text and PDFs where each table heading is a separate line.
    for i, line in enumerate(lines):
        if line.strip().lower() == "#" and i + 5 < len(lines):
            header_block = " ".join(lines[i + 1:i + 6]).lower()
            if all(token in header_block for token in ("description", "hsn", "qty", "rate", "amount")):
                header_idx = i
                break
        if re.search(r"description", line, re.I) and re.search(r"hsn", line, re.I) and re.search(r"qty", line, re.I):
            header_idx = i
            break
    if header_idx is not None:
        i = header_idx + 6 if lines[header_idx].strip() == "#" else header_idx + 1
        while i < len(lines):
            # Stop before invoice totals / footer.
            if re.search(r"amount in words|sub\s*total|grand total|igst|cgst|sgst|round off|terms\s*&?\s*conditions", lines[i], re.I):
                break
            # Expected extracted cell order: row number, description, HSN, qty, rate, amount.
            if not re.fullmatch(r"\d{1,4}", lines[i]):
                i += 1
                continue
            if i + 5 >= len(lines):
                break
            row_no, product, hsn, qty_s, rate_s, amount_s = lines[i:i+6]
            # Validate cell shapes so address/phone/invoice numbers cannot become products.
            if (re.fullmatch(r"\d{1,4}", row_no)
                and len(product) >= 2
                and re.fullmatch(r"\d{4,8}", hsn.replace(" ", ""))
                and re.fullmatch(r"\d+(?:\.0+)?", qty_s.replace(",", ""))
                and re.fullmatch(r"(?:₹|Rs\.?\s*)?\d[\d,]*(?:\.\d{1,2})?", rate_s, re.I)
                and re.fullmatch(r"(?:₹|Rs\.?\s*)?\d[\d,]*(?:\.\d{1,2})?", amount_s, re.I)):
                try:
                    qty = int(float(qty_s.replace(",", "")))
                    price = float(re.sub(r"[^\d.]", "", rate_s.replace(",", "")))
                    amount = float(re.sub(r"[^\d.]", "", amount_s.replace(",", "")))
                    # Amount should roughly equal quantity × rate; this guards against shifted columns.
                    if qty > 0 and price > 0 and amount > 0 and abs(qty * price - amount) <= max(2.0, amount * 0.03):
                        items.append({"product": product.strip()[:150], "brand": "", "category": "General", "sub_category": "", "model_number": "", "color": "", "warranty": "", "gst": 18, "quantity": qty, "cost_price": price})
                        i += 6
                        continue
                except (ValueError, TypeError):
                    pass
            i += 1

    # Fallback for common single-line tables: accept only rows with an explicit
    # row number, product text, HSN, quantity, rate and line amount.
    if not items:
        for line in lines:
            if re.search(r"subtotal|grand total|taxable|cgst|sgst|igst|round.?off|shipping|discount|amount in words|terms|invoice|gstin|mobile|phone", line, re.I):
                continue
            m = re.match(r"^\s*\d{1,4}\s+(.+?)\s+\d{4,8}\s+(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$", line)
            if not m:
                continue
            product, qty_s, rate_s, amount_s = m.groups()
            try:
                qty, price, amount = int(qty_s), float(rate_s.replace(',', '')), float(amount_s.replace(',', ''))
                if qty > 0 and price > 0 and abs(qty * price - amount) <= max(2.0, amount * 0.03):
                    items.append({"product": product.strip()[:150], "brand": "", "category": "General", "sub_category": "", "model_number": "", "color": "", "warranty": "", "gst": 18, "quantity": qty, "cost_price": price})
            except ValueError:
                continue

    items = _clean_items(items)
    if not items:
        return _empty_bill("Local OCR could not confidently identify valid product-table rows. Please verify the invoice manually; no stock was changed.")
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
