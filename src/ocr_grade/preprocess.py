"""Rasterize PDF pages to images and clean them up.

Will hold `rasterize(exam_file, dpi) -> list[PageImage]` (via pdf2image) and
`clean(image) -> image` (deskew/denoise/contrast, each toggleable via
settings.preprocess_steps), writing artifacts to cache_dir/<exam_sha>/.

Note: pdf2image requires the Poppler binaries on PATH; not yet verified on
all dev machines (see OPERATIONS.md). Deliberately no import of pdf2image
here yet so this stub doesn't fail to import where Poppler is missing.
"""

# TODO(prompt3): implement rasterize() and clean().
