"""Build the final interleaved scan+transcript PDF.

Will hold `build_interleaved(exam, transcripts, out_path)`: alternates scan
pages with transcript pages rendered from cleaned markdown via
markdown-it-py + WeasyPrint, then a pikepdf compression/size-guard pass.

Note: WeasyPrint needs native Pango/GDK libraries at runtime (not yet
verified on all dev machines, see OPERATIONS.md). Deliberately no import of
weasyprint here yet so this stub doesn't fail to import where those native
libs are missing.
"""

# TODO(prompt8): implement build_interleaved() + size-guard compression/split.
