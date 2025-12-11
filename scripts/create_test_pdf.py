from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
import textwrap
import argparse


# 👇 ŚCIEŻKA DO FONTU Z WINDOWS (sprawdza się w większości instalacji)
# Możesz zmienić np. na "C:\\Windows\\Fonts\\calibri.ttf" jeśli wolisz.
DEFAULT_FONT_PATH = r"C:\Windows\Fonts\arial.ttf"
FONT_NAME = "PolishFont"


def register_font(font_path: str = DEFAULT_FONT_PATH, font_name: str = FONT_NAME):
    """Zarejestruj font TrueType do obsługi polskich znaków."""
    pdfmetrics.registerFont(TTFont(font_name, font_path))


def create_pdf(text: str, out_path: Path):
    register_font()  # rejestrujemy font raz

    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4

    # używamy naszego unicode-fontu
    c.setFont(FONT_NAME, 10)

    y = height - 50
    line_height = 14

    for paragraph in text.split("\n"):
        # wrap long lines
        wrapped = textwrap.wrap(paragraph, width=100)
        if not wrapped:
            y -= line_height
            if y < 50:
                c.showPage()
                c.setFont(FONT_NAME, 10)
                y = height - 50
            continue

        for line in wrapped:
            c.drawString(50, y, line)
            y -= line_height
            if y < 50:
                c.showPage()
                c.setFont(FONT_NAME, 10)
                y = height - 50

    c.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("text_file", type=str, help="Path to TXT file with SIWZ content")
    parser.add_argument("out_pdf", type=str, help="Where to save PDF")
    args = parser.parse_args()

    text = Path(args.text_file).read_text(encoding="utf-8")
    create_pdf(text, Path(args.out_pdf))

    print(f"Created PDF at {args.out_pdf}")


if __name__ == "__main__":
    main()
