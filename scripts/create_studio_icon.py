"""Generate the original vector-derived spool icon; no external artwork."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
icon = QIcon()
for size in (16, 24, 32, 48, 64, 128, 256):
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 256, size / 256)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#162a25"))
    painter.drawRoundedRect(QRectF(0, 0, 256, 256), 48, 48)
    painter.setBrush(QColor("#17c77b"))
    painter.drawEllipse(QRectF(34, 34, 188, 188))
    painter.setBrush(QColor("#162a25"))
    painter.drawEllipse(QRectF(78, 78, 100, 100))
    painter.setBrush(QColor("#e8fff2"))
    painter.drawEllipse(QRectF(108, 108, 40, 40))
    painter.setPen(QPen(QColor("#e8fff2"), 10, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap))
    painter.drawLine(196, 188, 227, 222)
    painter.end()
    icon.addPixmap(canvas)
target = Path(__file__).resolve().parents[1] / "src/ufm/ui/assets/ufm.ico"
target.parent.mkdir(parents=True, exist_ok=True)
if not icon.pixmap(256, 256).save(str(target), "ICO"):
    raise SystemExit("Unable to save ICO")
print(target)
