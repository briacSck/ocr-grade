"""Mistral OCR backend (sole concrete OCRBackend implementation).

Will call the official `mistralai` SDK (`client.ocr.process(...)`) with the
masked page image inline as a base64 data URI, parse the response into an
OCRResult, retry on 429/5xx via tenacity, and price each call from
settings.mistral_price_per_page.
"""

# TODO(prompt6): implement MistralOCRBackend.
