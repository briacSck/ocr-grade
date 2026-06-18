"""OCR backend protocol and result type.

Will hold `OCRBackend(Protocol)` (name, transcribe(image_path, page_meta))
and `OCRResult` (markdown_text, blocks, raw_response, cost_usd, latency_ms).
Kept even though Mistral is the only backend, to make a future swap cheap.
"""

# TODO(prompt5): implement OCRBackend Protocol + OCRResult.
