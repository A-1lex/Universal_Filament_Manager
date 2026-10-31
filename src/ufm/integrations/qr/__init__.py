"""Pure QR label rendering; a scan proposes identity, never a mount or debit."""

import re
from html import escape
from io import BytesIO

import segno

from ufm.domain.value_objects import EntityId


def spool_label_text(spool_id: EntityId) -> str:
    if not isinstance(spool_id, EntityId):
        raise ValueError("qr.identity_invalid")
    try:
        canonical = EntityId.parse(str(spool_id))
    except (TypeError, ValueError):
        raise ValueError("qr.identity_invalid") from None
    return f"UFM:SPOOL:{canonical}"


def parse_spool_label(text: str) -> EntityId:
    if type(text) is not str or len(text) != 46 or not text.startswith("UFM:SPOOL:"):
        raise ValueError("qr.label_invalid")
    try:
        return EntityId.parse(text[10:])
    except (TypeError, ValueError):
        raise ValueError("qr.label_invalid") from None


def spool_label_svg(spool_id: EntityId, *, scale: int = 4) -> bytes:
    """Return a standard QR SVG with four-module quiet zone, no file writes."""
    if type(scale) is not int or not 1 <= scale <= 100:
        raise ValueError("qr.scale_invalid")
    code = segno.make_qr(spool_label_text(spool_id), error="M")
    stream = BytesIO()
    code.save(stream, kind="svg", scale=scale, border=4, dark="black", light="white")
    return stream.getvalue()


def spool_label_card_svg(
    spool_id: EntityId,
    *,
    name: str,
    material: str,
    color: str | None,
    color_label: str,
    remaining_label: str,
) -> bytes:
    """Render a self-contained 80×45 mm QR label with human-readable facts."""
    if not isinstance(spool_id, EntityId):
        raise ValueError("qr.identity_invalid")
    values = (name, material, color_label, remaining_label)
    if any(type(value) is not str or len(value) > 200 for value in values):
        raise ValueError("qr.label_value_invalid")
    if color is not None and type(color) is not str:
        raise ValueError("qr.label_value_invalid")
    if color is not None and (type(color) is not str or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
        color = None

    code = segno.make_qr(spool_label_text(spool_id), error="M")
    matrix = code.matrix
    border = 4
    modules = len(matrix) + border * 2
    module = 390 / modules
    paths = []
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                px = (x + border) * module
                py = (y + border) * module
                paths.append(f"M{px:.2f},{py:.2f}h{module:.2f}v{module:.2f}h-{module:.2f}z")

    def safe(value: str) -> str:
        return "".join(char for char in value if char in "\t\n\r" or ord(char) >= 0x20)

    def line(value: str, y: int, size: int = 27) -> str:
        shortened = value if len(value) <= 30 else value[:27] + "…"
        return f'<text x="24" y="{y}" font-size="{size}">{escape(safe(shortened))}</text>'

    swatch = ""
    if color is not None:
        swatch = f'<rect x="24" y="258" width="42" height="42" rx="8" fill="{color}" stroke="#64748b" stroke-width="2"/>'
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="45mm" viewBox="0 0 800 450">'
        '<rect width="800" height="450" rx="24" fill="white" stroke="#cbd5e1" stroke-width="4"/>'
        '<g fill="#0f172a" font-family="Arial,sans-serif">'
        f'<text x="24" y="66" font-size="32" font-weight="700">{escape(safe(name[:36]))}</text>'
        f'{line(material, 122)}'
        f'{line(color_label, 178, 23)}'
        f'{line(remaining_label, 234, 23)}'
        f'{swatch}</g>'
        f'<g transform="translate(390 30)" fill="#000" shape-rendering="crispEdges"><path d="{"".join(paths)}"/></g>'
        f'<text x="24" y="410" font-family="Arial,sans-serif" font-size="18" fill="#64748b">UFM · {escape(str(spool_id))}</text>'
        '</svg>'
    )
    return svg.encode("utf-8")
