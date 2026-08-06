# /// script
# requires-python = ">=3.11"
# dependencies = ["PyMuPDF>=1.26"]
# ///
# ─── How to run ───
# uv run scripts/pdf_to_hwpx.py input.pdf output.hwpx
"""Convert a PDF into a fidelity-first image-backed HWPX package."""

from __future__ import annotations

import re
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
    sections = "".join(
        '<odf:file-entry odf:media-type="application/xml" '
        + f'odf:full-path="Contents/section{index}.xml"/>'
        for index in range(page_count)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
<odf:file-entry odf:media-type="{MIME}" odf:full-path="/"/>
<odf:file-entry odf:media-type="application/xml" odf:full-path="version.xml"/>
<odf:file-entry odf:media-type="application/xml" odf:full-path="settings.xml"/>
<odf:file-entry odf:media-type="application/xml" odf:full-path="Contents/header.xml"/>
<odf:file-entry odf:media-type="text/xml" odf:full-path="Contents/content.hpf"/>
<odf:file-entry odf:media-type="application/xml" odf:full-path="Contents/masterpage0.xml"/>
{sections}{images}</odf:manifest>"""


def _content_xml(title: str, page_count: int) -> str:
    images = "".join(
        f'<opf:item id="page{index:03d}" href="BinData/page{index:03d}.png" '
        + 'media-type="image/png" isEmbeded="1"/>'
        for index in range(1, page_count + 1)
    )
    sections = "".join(
        f'<opf:item id="section{index}" href="Contents/section{index}.xml" '
        + 'media-type="application/xml"/>'
        for index in range(page_count)
    )
    section_refs = "".join(
        f'<opf:itemref idref="section{index}"/>' for index in range(page_count)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" version="2.0">
<opf:metadata><opf:title>{escape(title)}</opf:title>
<opf:language>ko</opf:language></opf:metadata>
<opf:manifest>
<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>
<opf:item id="settings" href="settings.xml" media-type="application/xml"/>
<opf:item id="masterpage0" href="Contents/masterpage0.xml" media-type="application/xml"/>
{sections}{images}</opf:manifest>
<opf:spine><opf:itemref idref="header"/>{section_refs}</opf:spine>
</opf:package>"""


def _header_xml(page_count: int) -> str:
    path = Path(__file__).parents[1] / "assets/hancom-header.xml"
    template = path.read_text(encoding="utf-8")
    return re.sub(r'secCnt="\d+"', f'secCnt="{page_count}"', template, count=1)


def _settings_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"
 xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">
<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/>
</ha:HWPApplicationSetting>"""


def _container_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container"
 xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"><ocf:rootfiles>
<ocf:rootfile full-path="Contents/content.hpf"
 media-type="application/hwpml-package+xml"/>
<ocf:rootfile full-path="Preview/PrvText.txt" media-type="text/plain"/>
</ocf:rootfiles></ocf:container>"""


def _container_rdf() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about="Contents/content.hpf"/>
</rdf:RDF>"""


def _masterpage_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<hm:masterPage xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page"
 xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"
 id="masterpage0" type="BOTH" pageNumber="0" pageDuplicate="0" pageFront="0">
<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP"
 linkListIDRef="0" linkListNextIDRef="0" textWidth="59528" textHeight="84188"
 hasTextRef="0" hasNumRef="0"><hp:p id="0" paraPrIDRef="0" styleIDRef="0"
 pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="0"><hp:t/></hp:run>
</hp:p></hp:subList></hm:masterPage>"""


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


def _section_xml(index: int) -> str:
    lineseg = (
        '<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" '
        + f'vertsize="{PAGE_HEIGHT}" textheight="{PAGE_HEIGHT}" baseline="{PAGE_HEIGHT}" '
        + f'spacing="0" horzpos="0" horzsize="{PAGE_WIDTH}" flags="393216"/>'
        + "</hp:linesegarray>"
    )
    paragraph = (
        f'<hp:p id="{2_000_000_000 + index}" paraPrIDRef="0" styleIDRef="0" '
        + 'pageBreak="0" columnBreak="0" merged="0">'
        + f'<hp:run charPrIDRef="0">{_page_settings_xml()}{_picture_xml(index)}'
        + f"<hp:t/></hp:run>{lineseg}</hp:p>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        + '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        + 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
        + 'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
        + paragraph
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
            ("settings.xml", _settings_xml()),
            ("META-INF/container.xml", _container_xml()),
            ("META-INF/container.rdf", _container_rdf()),
            ("META-INF/manifest.xml", _manifest_xml(len(pages))),
            ("Contents/content.hpf", _content_xml(source.stem, len(pages))),
            ("Contents/header.xml", _header_xml(len(pages))),
            ("Contents/masterpage0.xml", _masterpage_xml()),
            ("Preview/PrvText.txt", f"{source.stem}\n{len(pages)} pages\n"),
        ):
            archive.writestr(name, value, compress_type=zipfile.ZIP_DEFLATED)
        for index in range(len(pages)):
            archive.writestr(
                f"Contents/section{index}.xml",
                _section_xml(index + 1),
                compress_type=zipfile.ZIP_DEFLATED,
            )
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
