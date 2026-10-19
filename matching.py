"""Conservative local product matching avoids one Gemini request per invoice line."""
import re
from difflib import SequenceMatcher

def _norm(value):
    return " ".join(re.sub(r"[^a-z0-9]+"," ",str(value or "").strip().lower()).split())

def _parse_db_product(value):
    parts=[p.strip() for p in str(value).split("|")]; parts += [""]*(4-len(parts))
    return {"product":parts[0],"brand":parts[1],"category":parts[2],"model_number":parts[3]}

def find_best_product(ocr_product,database_products):
    if not isinstance(ocr_product,dict): return {"match":"NEW PRODUCT","confidence":0}
    name=_norm(ocr_product.get("product")); brand=_norm(ocr_product.get("brand")); category=_norm(ocr_product.get("category")); model=_norm(ocr_product.get("model_number"))
    if not name: return {"match":"NEW PRODUCT","confidence":0}
    candidates=[]
    for raw in database_products or []:
        db=_parse_db_product(raw); db_name=_norm(db["product"]); db_brand=_norm(db["brand"]); db_category=_norm(db["category"]); db_model=_norm(db["model_number"])
        if model and db_model and model != db_model: continue
        if model and db_model != model: continue
        if brand and db_brand and brand != db_brand: continue
        if category and db_category and category != db_category: continue
        ratio=SequenceMatcher(None,name,db_name).ratio()
        if name == db_name: confidence=100
        elif ratio >= 0.97: confidence=96
        else: continue
        candidates.append((confidence,db["product"]))
    if not candidates: return {"match":"NEW PRODUCT","confidence":0}
    candidates.sort(reverse=True)
    if len(candidates)>1 and candidates[0][0]==candidates[1][0]: return {"match":"NEW PRODUCT","confidence":0}
    return {"match":candidates[0][1],"confidence":candidates[0][0]}
