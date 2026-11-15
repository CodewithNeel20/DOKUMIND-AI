
import pymupdf
from pathlib import Path

backend_folder = Path(__file__).resolve().parent
project_folder = backend_folder.parent

input_files = list(
    project_folder.rglob("wordpress-pdf-invoice-plugin-sample.pdf")
)

if not input_files:
    raise FileNotFoundError(
        "Original invoice PDF not found. "
        "Copy it into the backend folder and try again."
    )

input_file = input_files[0]
output_file = backend_folder / "scanned_test.pdf"

source = pymupdf.open(str(input_file))
scanned = pymupdf.open()

for page in source:
    pix = page.get_pixmap(dpi=200)

    new_page = scanned.new_page(
        width=page.rect.width,
        height=page.rect.height
    )

    new_page.insert_image(new_page.rect, pixmap=pix)

scanned.save(str(output_file))

scanned.close()
source.close()

print("Scanned test PDF created successfully!")
print(f"Original PDF: {input_file}")
print(f"Scanned PDF: {output_file}")
