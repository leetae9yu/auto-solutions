from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pymupdf

SCRIPT = Path(__file__).parents[1] / "scripts/pdf_to_docx.py"


def test_builds_word_compatible_docx_from_multipage_pdf(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.docx"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 5 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 5 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode())
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    trailer = "".join(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n",
            f"startxref\n{xref}\n%%EOF\n",
        ),
    )
    pdf.extend(trailer.encode())
    _ = source.write_bytes(pdf)

    # When
    result = subprocess.run(
        ["uv", "run", str(SCRIPT), str(source), str(output)],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then
    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "[Content_Types].xml" in names
        assert "word/document.xml" in names
        images = sorted(name for name in names if name.startswith("word/media/image"))
        assert images == ["word/media/image1.png"]
        document = archive.read("word/document.xml")
        _ = ET.fromstring(document)
        assert document.count(b'w:type="page"') == 1

    roundtrip_dir = tmp_path / "roundtrip"
    roundtrip_dir.mkdir()
    opened = subprocess.run(
        [
            "/usr/bin/libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(roundtrip_dir),
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert opened.returncode == 0, opened.stderr
    with pymupdf.open(roundtrip_dir / "output.pdf") as roundtrip:
        assert roundtrip.page_count == 2


def test_rejects_non_pdf_input(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source.txt"
    _ = source.write_text("not a pdf", encoding="utf-8")

    # When
    result = subprocess.run(
        ["uv", "run", str(SCRIPT), str(source), str(tmp_path / "output.docx")],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then
    assert result.returncode != 0
