"""Write tiny PDFs for tests, with no extra dependency.

`text_pdf` places text lines at exact coordinates (so tests can build two columns or
text that sits off the page); `image_pdf` makes an image-only scan with no text layer.
"""

from __future__ import annotations

from pathlib import Path


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(path: Path, pages: list[list[tuple[float, float, str]]],
             width: int = 600, height: int = 800) -> Path:
    """Each page is a list of (x, y_from_top, text) at 11pt Helvetica."""
    objects: list[bytes] = []
    n_pages = len(pages)
    font_id = 3
    page_ids = [4 + 2 * i for i in range(n_pages)]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, lines in enumerate(pages):
        stream = "".join(
            f"BT /F1 11 Tf {x:.1f} {height - y:.1f} Td ({_escape(t)}) Tj ET\n"
            for x, y, t in lines).encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>"
            .encode())
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path


def image_pdf(path: Path, lines: list[str]) -> Path:
    """A one-page scan: text drawn into a bitmap, saved as a PDF with no fonts."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=48)          # large enough for Tesseract to read
    for i, line in enumerate(lines):
        draw.text((100, 100 + 80 * i), line, fill="black", font=font)
    img.save(path, "PDF", resolution=150)
    return path
