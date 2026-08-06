# /// script
# requires-python = ">=3.11"
# dependencies = ["PyMuPDF>=1.26"]
# ///
# ─── How to run ───
# uv run scripts/pdf_to_hwpx.py input.pdf output.hwpx
"""Convert a PDF into a fidelity-first image-backed HWPX package."""

from __future__ import annotations

import sys
import zipfile
from html import escape
from pathlib import Path

import pymupdf

MIME = "application/hwp+zip"
PAGE_WIDTH = 59_528
PAGE_HEIGHT = 84_188
RENDER_DPI = 144
EXPECTED_ARGUMENT_COUNT = 3


class ConversionError(RuntimeError):
    """Raised when the input cannot produce a document."""

    @classmethod
    def empty_pdf(cls) -> ConversionError:
        """Create an error for a PDF without pages."""
        return cls("PDF has no pages")

    @classmethod
    def invalid_input(cls) -> ConversionError:
        """Create an error for a non-PDF input."""
        return cls("input must be a PDF")


def _version_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version"
 targetApplication="WORDPROCESSOR" major="5" minor="1" micro="0"
 buildNumber="0" os="1" xmlVersion="1.5"
 application="Exam Paper Builder" appVersion="1.0"/>"""


def _manifest_xml(page_count: int) -> str:
    images = "".join(
        '<odf:file-entry odf:media-type="image/png" '
        + f'odf:full-path="BinData/page{index:03d}.png"/>'
        for index in range(1, page_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
<odf:file-entry odf:media-type="{MIME}" odf:full-path="/"/>
<odf:file-entry odf:media-type="application/xml" odf:full-path="version.xml"/>
<odf:file-entry odf:media-type="application/xml" odf:full-path="Contents/header.xml"/>
<odf:file-entry odf:media-type="text/xml" odf:full-path="Contents/content.hpf"/>
<odf:file-entry odf:media-type="application/xml" odf:full-path="Contents/section0.xml"/>
{images}</odf:manifest>"""


def _content_xml(title: str, page_count: int) -> str:
    images = "".join(
        f'<opf:item id="page{index:03d}" href="BinData/page{index:03d}.png" '
        + 'media-type="image/png" isEmbeded="1"/>'
        for index in range(1, page_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" version="2.0">
<opf:metadata><opf:title>{escape(title)}</opf:title>
<opf:language>ko</opf:language></opf:metadata>
<opf:manifest>
<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>
<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>
{images}</opf:manifest>
<opf:spine><opf:itemref idref="section0" linear="yes"/></opf:spine>
</opf:package>"""


def _header_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"
 version="1.5" secCnt="1">
<hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>
<hh:refList>
<hh:fontfaces itemCnt="1"><hh:fontface lang="HANGUL" fontCnt="1">
<hh:font id="0" face="함초롬바탕" type="TTF"/>
</hh:fontface></hh:fontfaces>
<hh:charProperties itemCnt="1">
<hh:charPr id="0" height="1000" textColor="#000000" shadeColor="none"
 useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="0"/>
</hh:charProperties>
<hh:paraProperties itemCnt="1">
<hh:paraPr id="0" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="0"/>
</hh:paraProperties>
</hh:refList></hh:head>"""


def _page_settings_xml() -> str:
    return f"""<hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134"
 tabStop="8000" outlineShapeIDRef="0">
<hp:pagePr landscape="NARROWLY" width="{PAGE_WIDTH}" height="{PAGE_HEIGHT}"
 gutterType="LEFT_ONLY">
<hp:margin header="0" footer="0" gutter="0" left="0" right="0" top="0" bottom="0"/>
</hp:pagePr></hp:secPr>"""


def _picture_xml(index: int) -> str:
    image_id = f"page{index:03d}"
    shape_id = 1_700_000_000 + index
    return f"""<hp:pic id="{shape_id}" zOrder="{index}" numberingType="PICTURE"
 textWrap="IN_FRONT_OF_TEXT" textFlow="BOTH_SIDES" lock="0"
 dropcapstyle="None" href="" groupLevel="0" instid="{shape_id}" reverse="0">
<hp:offset x="0" y="0"/><hp:orgSz width="{PAGE_WIDTH}" height="{PAGE_HEIGHT}"/>
<hp:curSz width="{PAGE_WIDTH}" height="{PAGE_HEIGHT}"/>
<hp:flip horizontal="0" vertical="0"/>
<hp:rotationInfo angle="0" centerX="{PAGE_WIDTH // 2}"
 centerY="{PAGE_HEIGHT // 2}" rotateimage="1"/>
<hp:renderingInfo>
<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>
<hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>
<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>
</hp:renderingInfo>
<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="{PAGE_WIDTH}" y="0"/>
<hc:pt2 x="{PAGE_WIDTH}" y="{PAGE_HEIGHT}"/>
<hc:pt3 x="0" y="{PAGE_HEIGHT}"/></hp:imgRect>
<hp:imgClip left="0" right="{PAGE_WIDTH}" top="0" bottom="{PAGE_HEIGHT}"/>
<hp:inMargin left="0" right="0" top="0" bottom="0"/>
<hp:imgDim dimwidth="{PAGE_WIDTH}" dimheight="{PAGE_HEIGHT}"/>
<hc:img binaryItemIDRef="{image_id}" bright="0" contrast="0"
 effect="REAL_PIC" alpha="0"/><hp:effects/>
<hp:sz width="{PAGE_WIDTH}" widthRelTo="ABSOLUTE" height="{PAGE_HEIGHT}"
 heightRelTo="ABSOLUTE" protect="0"/>
<hp:pos treatAsChar="0" affectLSpacing="0" flowWithText="0" allowOverlap="1"
 holdAnchorAndSO="0" vertRelTo="PAGE" horzRelTo="PAGE" vertAlign="TOP"
 horzAlign="LEFT" vertOffset="0" horzOffset="0"/>
<hp:outMargin left="0" right="0" top="0" bottom="0"/>
<hp:shapeComment>PDF page {index}</hp:shapeComment></hp:pic>"""


def _section_xml(page_count: int) -> str:
    paragraphs: list[str] = []
    for index in range(1, page_count + 1):
        settings = _page_settings_xml() if index == 1 else ""
        page_break = "0" if index == 1 else "1"
        paragraphs.append(
            f'<hp:p id="{2_000_000_000 + index}" paraPrIDRef="0" styleIDRef="0" '
            + f'pageBreak="{page_break}" columnBreak="0" merged="0">'
            + f'<hp:run charPrIDRef="0">{settings}{_picture_xml(index)}<hp:t/></hp:run>'
            + "</hp:p>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        + '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        + 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
        + 'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
        + "".join(paragraphs)
        + "</hs:sec>"
    )


def _render_pages(source: Path) -> tuple[bytes, ...]:
    scale = RENDER_DPI / 72
    with pymupdf.open(source) as document:
        if document.page_count == 0:
            raise ConversionError.empty_pdf()
        return tuple(
            page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
            for page in document
        )


def build_hwpx(source: Path, output: Path) -> None:
    """Render every PDF page and package it as an A4 HWPX page."""
    if source.suffix.lower() != ".pdf":
        raise ConversionError.invalid_input()
    pages = _render_pages(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", MIME, compress_type=zipfile.ZIP_STORED)
        for name, value in (
            ("version.xml", _version_xml()),
            ("META-INF/manifest.xml", _manifest_xml(len(pages))),
            ("Contents/content.hpf", _content_xml(source.stem, len(pages))),
            ("Contents/header.xml", _header_xml()),
            ("Contents/section0.xml", _section_xml(len(pages))),
            ("Preview/PrvText.txt", f"{source.stem}\n{len(pages)} pages\n"),
        ):
            archive.writestr(name, value, compress_type=zipfile.ZIP_DEFLATED)
        for index, image in enumerate(pages, start=1):
            archive.writestr(
                f"BinData/page{index:03d}.png",
                image,
                compress_type=zipfile.ZIP_DEFLATED,
            )


def main() -> int:
    """Run the PDF-to-HWPX command."""
    if len(sys.argv) != EXPECTED_ARGUMENT_COUNT:
        _ = sys.stderr.write("usage: pdf_to_hwpx.py INPUT.pdf OUTPUT.hwpx\n")
        return 2
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    try:
        build_hwpx(source, output)
    except (pymupdf.FileDataError, FileNotFoundError, ConversionError) as error:
        _ = sys.stderr.write(f"{error}\n")
        return 1
    _ = sys.stdout.write(f"created {output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
