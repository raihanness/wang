import base64
import json
import logging
import mimetypes
import re
import urllib.error
import urllib.request
from django.conf import settings

logger = logging.getLogger("tracker")

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Recommended fast & active models in order of preference (high daily free quotas first)
CANDIDATE_MODELS = [
    "gemini-3.5-flash-lite",  # 500 RPD (Requests Per Day) on free tier
    "gemini-3.6-flash",       # 20 RPD
    "gemini-3.8-flash",       # 20 RPD
    "gemini-3.5-flash",       # 20 RPD
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
]


def scan_receipt_with_gemini(
    image_file_or_bytes,
    mime_type=None,
    category_names=None,
    wallet_options=None,
    api_key=None,
    model=None,
):
    """
    Sends receipt image to Google Gemini Vision API to extract total amount, merchant,
    item summary note, transaction date, suggested category, payment method, suggested wallet,
    and discount savings amount.

    Parameters:
        image_file_or_bytes: Django UploadedFile, bytes, or file-like object.
        mime_type: Optional string like 'image/jpeg', 'image/png', 'image/webp'.
        category_names: Optional list of user expense category strings for auto-matching.
        wallet_options: Optional list of user wallet name strings or dicts for account matching.
        api_key: Optional Gemini API key (defaults to settings.GEMINI_API_KEY).
        model: Optional model name (defaults to settings.GEMINI_MODEL or 'gemini-3.6-flash').

    Returns dict:
        {
            "success": bool,
            "total_amount": int | None,
            "merchant": str,
            "note": str,
            "suggested_category": str | None,
            "payment_method": str | None,
            "suggested_wallet": str | None,
            "discount_amount": int,
            "date": str | None,
            "error": str | None
        }
    """
    key = api_key if api_key is not None else getattr(settings, "GEMINI_API_KEY", "")
    if not key:
        return {
            "success": False,
            "error": "Gemini API key is not configured. Please set GEMINI_API_KEY in .env.",
        }

    raw_model = model or getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash")
    if raw_model:
        raw_model = raw_model.replace("models/", "").strip()

    # If model is deprecated (e.g. gemini-1.5-* or gemini-2.0-* or gemini-2.5-flash), prioritize active models
    models_to_try = []
    if raw_model:
        models_to_try.append(raw_model)
    for cand in CANDIDATE_MODELS:
        if cand not in models_to_try:
            models_to_try.append(cand)

    # Read bytes and infer MIME type
    if hasattr(image_file_or_bytes, "read"):
        try:
            image_file_or_bytes.seek(0)
        except Exception:
            pass
        image_bytes = image_file_or_bytes.read()
        if not mime_type and hasattr(image_file_or_bytes, "content_type"):
            mime_type = image_file_or_bytes.content_type
        if not mime_type and hasattr(image_file_or_bytes, "name"):
            mime_type, _ = mimetypes.guess_type(image_file_or_bytes.name)
    elif isinstance(image_file_or_bytes, (bytes, bytearray)):
        image_bytes = bytes(image_file_or_bytes)
    else:
        return {"success": False, "error": "Invalid image input."}

    if not image_bytes:
        return {"success": False, "error": "Empty image provided."}

    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"

    # Optimize image resolution to max 1280px to speed up network transfer and Gemini inference
    try:
        import io
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(image_bytes))
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        max_dim = 1280
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=85, optimize=True)
        image_bytes = out_buf.getvalue()
        mime_type = "image/jpeg"
        img.close()
    except Exception:
        pass

    # Base64 encode
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    categories_clause = ""
    if category_names:
        cats_str = ", ".join(f'"{c}"' for c in category_names if c)
        categories_clause = (
            f"Select the single best matching category for this receipt strictly from this available list: [{cats_str}]. "
            "If none fit, pick the closest general category from the list."
        )
    else:
        categories_clause = "Suggest a concise 1-2 word category name for this expense (e.g. Food, Daily, Transport, Social, Groceries, Shopping)."

    wallet_clause = ""
    if wallet_options:
        if isinstance(wallet_options, list) and wallet_options and isinstance(wallet_options[0], dict):
            w_names = [w.get("name") for w in wallet_options if w.get("name")]
        else:
            w_names = [str(w) for w in wallet_options if w]
        w_str = ", ".join(f'"{name}"' for name in w_names)
        wallet_clause = (
            f"Select the single best matching account/wallet for this receipt from this user account list: [{w_str}]. "
            "If the receipt indicates Cash / Tunai, select the cash account. If it indicates a specific bank (BCA, Mandiri, BRI, etc.) or e-wallet (GoPay, QRIS, OVO, ShopeePay), select that matching account. Return null if none match."
        )
    else:
        wallet_clause = "Return null."

    prompt_text = (
        "You are an expert shopping receipt parser for a personal finance app. "
        "Analyze this receipt/invoice photo carefully and extract the following information:\n"
        "1. total_amount: The final grand total / amount paid. Return as an integer number only (in IDR / local currency without commas or currency symbols). Look for 'TOTAL', 'GRAND TOTAL', 'TOTAL BAYAR', 'JUMLAH', 'NETTO', 'TUNAI', 'BAYAR', or the largest paid sum.\n"
        "2. merchant: The store, restaurant, supermarket, or business name (e.g. 'Indomaret', 'Starbucks', 'Alfamart', 'Alfamidi', 'Circle K', 'Superindo').\n"
        "3. items: A list of main items purchased (up to 4-5 items).\n"
        "4. note: A crisp, formatted summary note suitable for a transaction description. Format as '<Merchant> - <Item 1>, <Item 2>' (e.g. 'Circle K - Matcha Latte, Butter Coke' or 'Alfamidi - Indomie, Snack'). If merchant is unknown, just list items.\n"
        f"5. suggested_category: {categories_clause}\n"
        "6. payment_method: The payment method mentioned on the receipt (e.g. 'Tunai', 'Cash', 'BCA', 'Mandiri', 'BRI', 'QRIS', 'GoPay', 'ShopeePay', 'Debit', 'Credit Card'). If not found, return null.\n"
        f"7. suggested_wallet: {wallet_clause}\n"
        "8. discount_amount: Total discount, promotional savings, or voucher amount on the receipt if any (look for 'HEMAT', 'DISKON', 'PROMO', 'POTONGAN', 'SAVINGS'). Return as an integer number (in IDR), or 0 if none.\n"
        "9. date: The date of the transaction in YYYY-MM-DD format (or YYYY-MM-DDTHH:MM if time is clear). If not found, return null.\n\n"
        "Respond ONLY with a valid JSON object with keys: total_amount, merchant, items, note, suggested_category, payment_method, suggested_wallet, discount_amount, date."
    )

    request_payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data,
                        }
                    },
                    {
                        "text": prompt_text,
                    },
                ],
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        },
    }

    json_data = json.dumps(request_payload).encode("utf-8")
    last_error = None

    for candidate_model in models_to_try:
        url = f"{GEMINI_API_ENDPOINT.format(model=candidate_model)}?key={key}"
        req = urllib.request.Request(
            url,
            data=json_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)

            candidates = res_json.get("candidates", [])
            if not candidates:
                last_error = "No response generated by Gemini."
                continue

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                last_error = "Empty text response from Gemini."
                continue

            raw_text = parts[0]["text"].strip()
            # Clean potential markdown fences
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text)

            parsed = json.loads(raw_text)

            raw_amount = parsed.get("total_amount")
            total_amount = None
            if raw_amount is not None:
                try:
                    if isinstance(raw_amount, str):
                        clean_str = re.sub(r"[^\d.]", "", raw_amount.replace(",", "."))
                        total_amount = int(round(float(clean_str)))
                    elif isinstance(raw_amount, (int, float)):
                        total_amount = int(round(float(raw_amount)))
                except Exception:
                    total_amount = None

            merchant = (parsed.get("merchant") or "").strip()
            note = (parsed.get("note") or "").strip()
            suggested_category = (parsed.get("suggested_category") or "").strip() or None
            payment_method = (parsed.get("payment_method") or "").strip() or None
            suggested_wallet = (parsed.get("suggested_wallet") or "").strip() or None

            raw_discount = parsed.get("discount_amount")
            discount_amount = 0
            if raw_discount is not None:
                try:
                    if isinstance(raw_discount, str):
                        clean_d = re.sub(r"[^\d.]", "", raw_discount.replace(",", "."))
                        discount_amount = int(round(float(clean_d)))
                    elif isinstance(raw_discount, (int, float)):
                        discount_amount = int(round(float(raw_discount)))
                except Exception:
                    discount_amount = 0

            date = (parsed.get("date") or "").strip() or None

            # Fallback note if empty
            if not note:
                items = parsed.get("items") or []
                if isinstance(items, list) and items:
                    items_str = ", ".join(str(it) for it in items[:4])
                    note = f"{merchant} - {items_str}" if merchant else items_str
                elif merchant:
                    note = merchant

            return {
                "success": True,
                "total_amount": total_amount,
                "merchant": merchant,
                "note": note,
                "suggested_category": suggested_category,
                "payment_method": payment_method,
                "suggested_wallet": suggested_wallet,
                "discount_amount": discount_amount,
                "date": date,
                "error": None,
            }

        except urllib.error.HTTPError as err:
            err_msg = err.read().decode("utf-8", errors="ignore")
            logger.warning(f"Gemini API HTTPError {err.code} on model {candidate_model}: {err_msg}")
            if err.code == 429:
                last_error = "Daily AI scan quota reached (20/20 RPD). Resets at midnight PST."
                # Try next model candidate in case it has active quota
                continue
            elif err.code in (404, 500, 502, 503, 504):
                # Google server temporary overload or model unavailable, try next candidate model
                last_error = f"Google Gemini server temporarily busy ({err.code})."
                continue
            last_error = f"Gemini API error ({err.code}): {err.reason}"
            return {"success": False, "error": last_error}
        except urllib.error.URLError as err:
            logger.error(f"Gemini API URLError: {err.reason}")
            return {"success": False, "error": f"Network error connecting to Gemini: {err.reason}"}
        except json.JSONDecodeError as err:
            logger.error(f"Failed to parse JSON from Gemini: {err}")
            return {"success": False, "error": "Could not parse structured data from receipt."}
        except Exception as err:
            logger.error(f"Unexpected error in scan_receipt_with_gemini: {err}", exc_info=True)
            return {"success": False, "error": str(err)}

    return {"success": False, "error": last_error or "Could not scan receipt with Gemini."}
