from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


OUTPUT = Path("docs/MCI_Yacht_Technology_Summary_for_Howden_Re.docx")


def run(text: str, *, bold: bool = False, color: str | None = None, size: int | None = None) -> str:
    properties = []
    if bold:
        properties.append("<w:b/>")
    if color:
        properties.append(f'<w:color w:val="{color}"/>')
    if size:
        properties.extend((f'<w:sz w:val="{size}"/>', f'<w:szCs w:val="{size}"/>'))
    rpr = f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def paragraph(
    *runs: str,
    style: str | None = None,
    bullet: bool = False,
    before: int | None = None,
    after: int | None = None,
    keep_next: bool = False,
) -> str:
    props = []
    if style:
        props.append(f'<w:pStyle w:val="{style}"/>')
    if bullet:
        props.append('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
    if before is not None or after is not None:
        attrs = []
        if before is not None:
            attrs.append(f'w:before="{before}"')
        if after is not None:
            attrs.append(f'w:after="{after}"')
        props.append(f"<w:spacing {' '.join(attrs)}/>")
    if keep_next:
        props.append("<w:keepNext/>")
    ppr = f"<w:pPr>{''.join(props)}</w:pPr>" if props else ""
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


def build_document_xml() -> str:
    body = [
        paragraph(run("MCI", bold=True, color="1F4E79", size=20), style="Brand", after=50),
        paragraph(
            run("Technology supporting the Yacht portfolio", bold=True, color="17365D", size=34),
            style="Title",
            after=80,
            keep_next=True,
        ),
        paragraph(
            run("Summary for Howden Re", color="5B6573", size=21),
            style="Subtitle",
            after=300,
        ),
        paragraph(
            run(
                "MCI is developing an in-house marine risk intelligence and catastrophe-management "
                "application to support the underwriting and ongoing management of specialist yacht "
                "risks, initially focusing on yachts of 30 metres and above."
            ),
            after=180,
        ),
        paragraph(
            run(
                "The application is intended to supplement the information provided at submission with "
                "a more consistent, evidence-led view of the yacht, its operation and the surrounding "
                "exposures. It will bring together selected internal information and appropriately "
                "licensed or authoritative external data to support:"
            ),
            after=130,
        ),
        paragraph(
            run("Pre-bind risk assessment: ", bold=True, color="1F4E79"),
            run(
                "Consolidating yacht identity and characteristics, ownership and management relationships, "
                "historical movement and operating patterns, cruising areas, port and marina activity, "
                "weather and tropical-cyclone exposure, casualty information and relevant captain or crew credentials."
            ),
            bullet=True,
            after=110,
        ),
        paragraph(
            run("Risk and compliance screening: ", bold=True, color="1F4E79"),
            run(
                "Highlighting potential sanctions connections, material ownership or flag changes, "
                "operation in higher-risk territories, unusual movement patterns and gaps in available "
                "tracking data. Potential matches or concerns will be referred for human review rather "
                "than treated as automatic decisions."
            ),
            bullet=True,
            after=110,
        ),
        paragraph(
            run("Catastrophe and accumulation management: ", bold=True, color="1F4E79"),
            run(
                "Providing a portfolio view of the number and value of insured yachts concentrated within "
                "locations such as ports, marinas, shipyards, storm footprints or other defined risk areas. "
                "This is intended to improve visibility of peak exposures and enable faster identification "
                "of risks potentially affected by a developing or actual event."
            ),
            bullet=True,
            after=110,
        ),
        paragraph(
            run("Ongoing monitoring: ", bold=True, color="1F4E79"),
            run(
                "Subject to confirmation of the yachts and values on cover, monitoring material changes in "
                "location, weather exposure, listed areas, ownership, sanctions and reported casualties. "
                "Alerts will be prioritised and linked to the relevant risk and supporting evidence."
            ),
            bullet=True,
            after=110,
        ),
        paragraph(
            run("Underwriting governance: ", bold=True, color="1F4E79"),
            run(
                "Presenting an explainable summary with the source, age and coverage of the underlying "
                "information, together with any uncertainty or data gaps. Assessments, changes and "
                "underwriter actions will be retained to provide an auditable decision history."
            ),
            bullet=True,
            after=220,
        ),
        paragraph(
            run(
                "The application is designed as decision support for experienced underwriters; it will not "
                "automatically accept, decline, price or bind a risk, and it will not rely on an unexplained "
                "‘black-box’ score. Its purpose is to help improve the speed and consistency of risk selection, "
                "strengthen screening and portfolio oversight, and support earlier, better-informed responses "
                "to catastrophe and other material events."
            ),
            after=180,
        ),
        paragraph(
            run(
                "A working proof of concept has already demonstrated the core approach by comparing historical "
                "vessel movements with authoritative tropical-cyclone data and presenting the results through "
                "an explainable assessment and interactive mapping. The planned production capability will "
                "broaden this into global yacht intelligence, screening, monitoring and portfolio accumulation "
                "management using suitably validated data sources."
            ),
            after=0,
        ),
        (
            '<w:sectPr>'
            '<w:footerReference w:type="default" r:id="rId2"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" '
            'w:header="450" w:footer="450" w:gutter="0"/>'
            '</w:sectPr>'
        ),
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{''.join(body)}</w:body></w:document>"
    )


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos" w:eastAsia="Aptos" w:cs="Aptos"/><w:sz w:val="20"/><w:szCs w:val="20"/><w:color w:val="263442"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Brand"><w:name w:val="Brand"/><w:basedOn w:val="Normal"/><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="18" w:space="8" w:color="2E75B6"/></w:pBdr></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:qFormat/></w:style>
</w:styles>"""

NUMBERING = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="singleLevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="420"/></w:tabs><w:ind w:left="420" w:hanging="240"/></w:pPr><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/></w:rPr></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>"""

FOOTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="6" w:color="D9E2F3"/></w:pBdr><w:jc w:val="right"/></w:pPr><w:r><w:rPr><w:color w:val="7F8C9A"/><w:sz w:val="16"/></w:rPr><w:t>MCI | Yacht technology summary</w:t></w:r></w:p>
</w:ftr>"""

APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Microsoft Office Word</Application><AppVersion>16.0000</AppVersion></Properties>"""


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Technology supporting the Yacht portfolio</dc:title><dc:subject>Summary for Howden Re</dc:subject><dc:creator>MCI</dc:creator><cp:lastModifiedBy>MCI</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified></cp:coreProperties>"""

    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", APP)
        archive.writestr("word/document.xml", build_document_xml())
        archive.writestr("word/styles.xml", STYLES)
        archive.writestr("word/numbering.xml", NUMBERING)
        archive.writestr("word/footer1.xml", FOOTER)
        archive.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)

    print(OUTPUT.resolve())


if __name__ == "__main__":
    main()
