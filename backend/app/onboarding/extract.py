"""Vision extraction of licence fields, with provenance on every value.

WHY EVERY FIELD IS OPTIONAL
---------------------------
`LicenseExtraction` declares every field as `str | None`. That is not defensive
typing -- it is the schema encoding of the prompt's most important instruction.
A model with no legal way to say "I cannot read this" will produce a confident
value instead, and a confident wrong national producer number is the worst
output this component can generate: it looks valid, it passes a format check,
and it posts to a carrier system.

Making null representable is what allows the eval to measure the ratio the
decision actually rests on. Extraction at 92% accuracy is a review accelerator
if the missing 8% comes back as nulls, and actively dangerous if it comes back
as confident wrong values. The accuracy number alone cannot tell those apart.

WHY EXCERPTS ARE VERIFIED
-------------------------
Each returned field carries a short verbatim excerpt. After the call, every
excerpt is checked against the document's own text layer -- read independently
with PyMuPDF rather than trusting what the model reports. An excerpt that is not
in the document was composed rather than read, and the field carrying it is
downgraded to unreadable and counted. This is the same two-layer guarantee the
sibling project applies to citations: structural, then verified.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.prompts.extraction import (
    LICENSE_EXTRACTION_SYSTEM,
    LICENSE_EXTRACTION_USER,
)

# 150 DPI puts a Letter page at roughly 1650px on the long edge, which keeps
# 7.5pt label text legible without paying for resolution the model cannot use.
RENDER_DPI = 150

# An excerpt shorter than this matches almost anything and is not accepted as
# evidence that a value was read rather than composed.
EXCERPT_MATCH_MIN_LENGTH = 6

# Fields where a confident wrong value is materially worse than a null, because
# they are what a carrier submission is keyed on. Reported separately in the
# eval for that reason.
DANGER_FIELDS = ("npn", "license_number", "expiration_date")


class FieldEvidence(BaseModel):
    """Where on the page a value was read from."""

    field_name: str = Field(description="The field this excerpt supports.")
    excerpt: str = Field(
        description="Short verbatim text from the page, copied exactly."
    )


class LicenseExtraction(BaseModel):
    """Licence fields as printed. Every field may be null; see the module note."""

    full_name: str | None = Field(
        default=None, description="Licensee name exactly as printed."
    )
    npn: str | None = Field(
        default=None,
        description=(
            "National Producer Number exactly as printed, including any "
            "leading zero."
        ),
    )
    license_number: str | None = Field(default=None)
    resident_state: str | None = Field(
        default=None,
        description="Exactly as printed, whether abbreviated or written in full.",
    )
    license_type: str | None = Field(default=None)
    lines_of_authority: list[str] = Field(default_factory=list)
    issue_date: str | None = Field(
        default=None, description="Exactly as printed, in the document's own format."
    )
    expiration_date: str | None = Field(default=None)
    unreadable_fields: list[str] = Field(
        default_factory=list,
        description="Field names that could not be read directly off the page.",
    )
    field_evidence: list[FieldEvidence] = Field(default_factory=list)


@dataclass
class ExtractionResult:
    """One document's extraction, after verification."""

    document_id: str
    extraction: LicenseExtraction
    # Fields whose excerpt could not be found in the document's text layer, and
    # which were therefore set to None rather than reported.
    evidence_dropped: list[str] = dataclass_field(default_factory=list)
    latency_ms: int = 0
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        """Spend for this document, at Claude Opus 5 list rates."""
        return self.input_tokens * 5.0 / 1e6 + self.output_tokens * 25.0 / 1e6


def _normalize(text: str) -> str:
    """Collapse whitespace and unify quotes for excerpt comparison."""
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def page_png(pdf_path: Path, *, dpi: int = RENDER_DPI) -> bytes:
    """Rasterise page one of a licence."""
    import fitz  # PyMuPDF

    with fitz.open(pdf_path) as document:
        page = document[0]
        pixmap = page.get_pixmap(dpi=dpi)
        return pixmap.tobytes("png")


def document_text(pdf_path: Path) -> str:
    """The document's own text layer, read independently of the model.

    This is what excerpts are checked against. Trusting the model's report of
    what it saw would make the verification circular.
    """
    import fitz  # PyMuPDF

    with fitz.open(pdf_path) as document:
        return "\n".join(page.get_text() for page in document)


def verify(result: ExtractionResult, source_text: str) -> ExtractionResult:
    """Null any field whose excerpt is not in the document.

    A field whose supporting excerpt cannot be found was composed rather than
    read. It is set to None and named in `unreadable_fields`, which is the
    honest disposition -- the pipeline does not know the value, and saying so is
    exactly what the null branch exists for.
    """
    source = _normalize(source_text)
    evidence_by_field = {
        item.field_name: item.excerpt for item in result.extraction.field_evidence
    }

    for name in list(evidence_by_field):
        excerpt = _normalize(evidence_by_field[name])
        if len(excerpt) < EXCERPT_MATCH_MIN_LENGTH or excerpt not in source:
            if hasattr(result.extraction, name):
                setattr(result.extraction, name, None)
                if name not in result.extraction.unreadable_fields:
                    result.extraction.unreadable_fields.append(name)
                result.evidence_dropped.append(name)

    return result


def extract(client: Any, pdf_path: Path, *, model: str) -> ExtractionResult:
    """Read one licence and return its verified fields.

    Args:
        client: An `anthropic.Anthropic` instance.
        pdf_path: The licence to read.
        model: Model id.

    Returns:
        The extraction, with unverifiable fields nulled.
    """
    import time

    image = base64.standard_b64encode(page_png(pdf_path)).decode("ascii")

    started = time.perf_counter()
    response = client.messages.parse(
        model=model,
        max_tokens=8000,
        system=LICENSE_EXTRACTION_SYSTEM,
        # Transcription is a scoped task, not an open reasoning problem. Low
        # effort keeps twelve documents inside a sensible wall clock and a
        # sensible bill.
        output_config={"effort": "low"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image,
                        },
                    },
                    {"type": "text", "text": LICENSE_EXTRACTION_USER},
                ],
            }
        ],
        output_format=LicenseExtraction,
    )
    latency_ms = round((time.perf_counter() - started) * 1000)

    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(
            f"extraction returned no structured output for {pdf_path.name} "
            f"(stop_reason={response.stop_reason})"
        )

    result = ExtractionResult(
        document_id=pdf_path.stem,
        extraction=parsed,
        latency_ms=latency_ms,
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    return verify(result, document_text(pdf_path))
