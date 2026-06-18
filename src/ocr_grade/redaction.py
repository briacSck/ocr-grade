"""Local identity masking before any image is sent to Mistral.

Will hold `mask(page_image, settings) -> MaskedPage`: header bounding-box
masking, a cheap header-only OCR pass behind a `HeaderOCR` interface, regex
matching on extracted text, and a local-only identity sidecar.
"""

# TODO(prompt4): implement mask() + HeaderOCR + identity sidecar.
