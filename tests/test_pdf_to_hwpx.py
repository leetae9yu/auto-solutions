from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/pdf_to_hwpx.py"


def test_builds_valid_image_backed_hwpx_from_multipage_pdf(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.hwpx"
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
        ["uv", "run", "--with", "pymupdf", str(SCRIPT), str(source), str(output)],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then
    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert names[0] == "mimetype"
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/hwp+zip"
        assert [name for name in names if name.startswith("BinData/page")] == [
            "BinData/page001.png",
            "BinData/page002.png",
        ]
        for name in (
            "version.xml",
            "META-INF/manifest.xml",
            "Contents/content.hpf",
            "Contents/header.xml",
            "Contents/section0.xml",
        ):
            _ = ET.fromstring(archive.read(name))
        section = archive.read("Contents/section0.xml").decode("utf-8")
        assert section.count('pageBreak="1"') == 1
        content = archive.read("Contents/content.hpf").decode("utf-8")
        assert 'href="BinData/page001.png"' in content
        assert 'href="BinData/page002.png"' in content


def test_rejects_non_pdf_input(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source.txt"
    _ = source.write_text("not a pdf", encoding="utf-8")

    # When
    result = subprocess.run(
        ["uv", "run", "--with", "pymupdf", str(SCRIPT), str(source), str(tmp_path / "output.hwpx")],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then
    assert result.returncode != 0
