"""Content-addressed local cache for OCR results.

Will hold a cache keyed by sha256(image_bytes) + backend.name + model name +
serialized params, storing OCRResult as JSON, plus a `get_or_call(backend,
image_path, meta)` helper.
"""

# TODO(prompt5): implement cache + get_or_call().
