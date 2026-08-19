"""Render one resident producer licence per agent, and recover exact ground truth.

WHY GENERATED, AND WHY GROUND TRUTH IS RE-READ RATHER THAN ASSUMED
------------------------------------------------------------------
A real producer licence carries a real person's name and national producer
number. None of that belongs in a public demo.

Generating them removes that problem and buys the thing that makes the
extraction eval mean anything: the exact string printed on the page is known,
because this file printed it. But knowing what was *asked* for is not the same
as knowing what *landed* -- a layout engine wraps, truncates, and repositions.
So after rendering, each document is re-opened and read back through PyMuPDF,
and the ground truth records where each value actually appeared. That is the
same discipline the sibling project uses for its build charts, and it is the
difference between scoring against an intention and scoring against a document.

THE HAZARDS ARE DELIBERATE
--------------------------
A corpus of twelve identical clean licences would not test an extractor at all.
Three documents carry a rendering hazard and four carry a data hazard:

  - one prints its state in full where the rest abbreviate
  - one uses DD-MMM-YYYY where the rest use MM/DD/YYYY
  - one carries a low-contrast watermark across the NPN block
  - one NPN has a leading zero, which any reader that treats it as a number
    silently drops

The last is the most interesting, because the damaged value still looks like a
valid NPN. It is the shape of failure this eval exists to distinguish from a
clean refusal.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).parent))

from onboarding_data import AGENT_SEEDS, LINE_LABELS, AgentSeed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "corpus" / "onboarding"

STATE_NAMES = {
    "NC": "North Carolina",
    "SC": "South Carolina",
    "GA": "Georgia",
    "TN": "Tennessee",
    "VA": "Virginia",
    "FL": "Florida",
    "TX": "Texas",
    "OH": "Ohio",
}


def _draw_watermark(pdf: canvas.Canvas) -> None:
    """A low-contrast diagonal stamp across the middle of the page.

    Placed to cross the identification block rather than the header, because a
    watermark over decorative text is not a hazard and one over the NPN is.
    """
    pdf.saveState()
    pdf.setFillColor(colors.Color(0.62, 0.66, 0.72, alpha=0.30))
    pdf.setFont("Helvetica-Bold", 46)
    pdf.translate(2.1 * inch, 5.4 * inch)
    pdf.rotate(22)
    pdf.drawString(0, 0, "DUPLICATE COPY")
    pdf.restoreState()


def render(seed: AgentSeed) -> Path:
    """Render one licence and return its path."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{seed.agent_id}_license.pdf"
    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER

    state_full = STATE_NAMES.get(seed.resident_state, seed.resident_state)

    # --- Header -----------------------------------------------------------
    pdf.setFillColor(colors.Color(0.05, 0.09, 0.16))
    pdf.rect(0, height - 1.35 * inch, width, 1.35 * inch, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(0.9 * inch, height - 0.72 * inch, f"{state_full.upper()}")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(
        0.9 * inch, height - 0.98 * inch, "Department of Insurance"
    )
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(
        width - 0.9 * inch, height - 0.72 * inch, "RESIDENT PRODUCER LICENSE"
    )
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(
        width - 0.9 * inch,
        height - 0.95 * inch,
        "SPECIMEN - NOT A GENUINE LICENSE",
    )

    if seed.watermark_over_npn:
        _draw_watermark(pdf)

    pdf.setFillColor(colors.Color(0.05, 0.09, 0.16))

    def field(label: str, value: str, x: float, y: float, size: int = 12) -> None:
        pdf.setFont("Helvetica", 7.5)
        pdf.setFillColor(colors.Color(0.42, 0.47, 0.55))
        pdf.drawString(x, y, label.upper())
        pdf.setFont("Helvetica-Bold", size)
        pdf.setFillColor(colors.Color(0.05, 0.09, 0.16))
        pdf.drawString(x, y - 0.22 * inch, value)

    top = height - 2.05 * inch
    field("Licensee name", seed.license_full_name, 0.9 * inch, top, 14)

    # The identification block. `state_printed_as` is what goes on the page --
    # the seeds disagree on abbreviation deliberately, and normalising here
    # would hide the hazard from the extractor rather than testing it.
    row = top - 0.85 * inch
    field("National Producer Number", seed.npn, 0.9 * inch, row)
    field("License number", seed.license_number, 3.4 * inch, row)
    field("Resident state", seed.state_printed_as, 5.9 * inch, row)

    row -= 0.85 * inch
    field("License type", seed.license_type, 0.9 * inch, row, 11)
    field("Issue date", seed.issue_date, 3.4 * inch, row, 11)
    field("Expiration date", seed.expiration_date, 5.9 * inch, row, 11)

    # --- Lines of authority ----------------------------------------------
    row -= 0.95 * inch
    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColor(colors.Color(0.42, 0.47, 0.55))
    pdf.drawString(0.9 * inch, row, "LINES OF AUTHORITY")
    pdf.setFillColor(colors.Color(0.05, 0.09, 0.16))
    line_y = row - 0.28 * inch
    for line in seed.lines_of_authority:
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.drawString(1.05 * inch, line_y, f"•  {LINE_LABELS.get(line, line)}")
        line_y -= 0.26 * inch

    # --- Footer -----------------------------------------------------------
    pdf.setStrokeColor(colors.Color(0.82, 0.85, 0.89))
    pdf.line(0.9 * inch, 1.5 * inch, width - 0.9 * inch, 1.5 * inch)
    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColor(colors.Color(0.42, 0.47, 0.55))
    pdf.drawString(
        0.9 * inch,
        1.28 * inch,
        "This document is generated for software demonstration. The licensee, "
        "the numbers, and the issuing authority are fictional.",
    )
    pdf.drawString(
        0.9 * inch,
        1.12 * inch,
        "It is not a licence, not evidence of one, and confers no authority to "
        "transact insurance.",
    )

    pdf.showPage()
    pdf.save()
    return path


def _page_text(path: Path) -> str:
    """Read the rendered page back, so ground truth is what actually printed."""
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - the caller reports this
        raise SystemExit(
            "PyMuPDF is required to verify the rendered documents: pip install pymupdf"
        )
    with fitz.open(path) as document:
        return "\n".join(page.get_text() for page in document)


def main() -> int:
    """Render every licence and verify each value survived the render."""
    rendered: list[tuple[str, Path]] = []
    problems: list[str] = []

    for seed in AGENT_SEEDS:
        path = render(seed)
        text = _page_text(path)
        # Whitespace is collapsed before comparing: a PDF text layer breaks
        # lines wherever the layout did, and a value that printed correctly can
        # still arrive with a newline in the middle of it.
        flat = re.sub(r"\s+", " ", text)

        for label, value in (
            ("name", seed.license_full_name),
            ("npn", seed.npn),
            ("license_number", seed.license_number),
            ("state", seed.state_printed_as),
            ("issue", seed.issue_date),
            ("expiration", seed.expiration_date),
        ):
            if re.sub(r"\s+", " ", value) not in flat:
                problems.append(f"{seed.agent_id}: {label} {value!r} did not survive rendering")

        rendered.append((seed.agent_id, path))

    for agent_id, path in rendered:
        print(f"  {agent_id}  {path.name}  {path.stat().st_size:>6,} bytes")

    if problems:
        print("\nverification failed:")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print(f"\n{len(rendered)} licences rendered and verified against their text layer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
