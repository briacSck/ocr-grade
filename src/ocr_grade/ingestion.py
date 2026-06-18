"""Discover and validate input exam PDFs.

Will hold `discover(input_dir) -> list[ExamFile]`: records path, page_count,
sha256, detected course, and validation status (corrupt PDFs, DPI too low,
pages exceeding Mistral OCR size/page limits).
"""

# TODO(prompt3): implement ExamFile + discover().
