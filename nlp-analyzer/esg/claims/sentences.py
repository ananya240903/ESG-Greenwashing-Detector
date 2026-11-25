"""Split chunk text into candidate sentences for the claim classifier.

Chunk text from the PDF parser has one paragraph per line, mixed with BRSR question
headings ("EI-6. Please provide details of ...:"), table captions and fragments
("Over 3,80,000"). Each line is split into sentences, and lines or sentences that
cannot be a claim are dropped. Offsets index into the original chunk text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_WORDS = 6
MAX_WORDS = 120  # longer "sentences" are run-on table text, not prose

# Abbreviations that end in a period but do not end a sentence.
_ABBREVIATIONS = {
    "e.g", "i.e", "viz", "etc", "vs", "no", "nos", "sr", "mr", "mrs", "ms", "dr", "prof",
    "ltd", "pvt", "co", "inc", "corp", "govt", "dept", "approx", "fy", "rs", "inr", "st",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "fig", "ref", "sec", "para", "cl", "u.s", "u.k",
}

# A sentence ends at . ! or ? (optionally followed by a closing quote or bracket),
# followed by whitespace and something that can start a sentence.
_BOUNDARY = re.compile(r"""[.!?]["'”’)\]]*\s+(?=["'“‘(\[]?[A-Z0-9])""")

# BRSR question and index lines: "EI-6.", "LI- 2.", "IV-22.", "II.", "17.", "a)", "(b)"
_QUESTION_PREFIX = re.compile(r"^\s*(?:(?:EI|LI|[IVX]{1,5})\s*-\s*\d+\.?|[IVX]{1,5}\.|\d{1,2}[.)]|\(?[a-z]\))\s")
_BULLET = re.compile(r"^\s*[•▪●◦‣\-–—*]\s*")

# The nine NGRBC principle statements are printed in every BRSR ("Businesses should respect
# and make efforts to protect and restore the environment"). They are the template, not a
# claim by the company.
_TEMPLATE = re.compile(r"^(?:PRINCIPLE\s+\d+\s*[:.\-–]?\s*)?Businesses should\b", re.IGNORECASE)

# Questions and instructions from the BRSR form itself, which companies often reprint
# without their "EI-6." numbers ("Describe the processes in place to safely reclaim ...",
# "Percentage of R&D and capex investments in specific technologies ...").
_FORM_TEXT = re.compile(
    r"^(?:Describe|Details of|Percentage of|Number of|Name of|List\b|Provide\b|Please\b|Whether\b|"
    r"Does the entity|Do you|Has the entity|Have you|Is there|Are there|If yes|If not|"
    r"This section is aimed|While the essential indicators|Disclosure Questions)",
    re.IGNORECASE)


@dataclass(frozen=True)
class Sentence:
    text: str
    start: int  # character offsets into the chunk text
    end: int


def _ends_with_abbreviation(text: str) -> bool:
    match = re.search(r"([A-Za-z.]+)\.$", text)
    if not match:
        return False
    word = match.group(1).lower()
    return word in _ABBREVIATIONS or len(word) == 1  # initials: "A. K. Sharma"


def _split_line(line: str, offset: int) -> list[Sentence]:
    out, start = [], 0
    for match in _BOUNDARY.finditer(line):
        candidate = line[start:match.start() + 1]
        if _ends_with_abbreviation(candidate.rstrip("\"'”’)]")):
            continue
        out.append((start, match.end()))
        start = match.end()
    out.append((start, len(line)))
    sentences = []
    for s, e in out:
        piece = line[s:e]
        lead = len(piece) - len(piece.lstrip())
        piece = piece.strip()
        if piece:
            sentences.append(Sentence(piece, offset + s + lead, offset + s + lead + len(piece)))
    return sentences


def _is_candidate(text: str) -> bool:
    words = text.split()
    if not MIN_WORDS <= len(words) <= MAX_WORDS:
        return False
    if text.endswith((":", "?")):
        return False  # a question or a lead-in to a table
    if _TEMPLATE.match(text):
        return False  # BRSR principle statement
    if _FORM_TEXT.match(text):
        return False  # a question or instruction from the BRSR form
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 0.5 * len(text.replace(" ", "")):
        return False  # mostly numbers: a table row that leaked into prose
    if sum(c.isupper() for c in letters) > 0.6 * len(letters):
        return False  # SHOUTED HEADING
    return True


def split_sentences(text: str) -> list[Sentence]:
    """Candidate claim sentences in `text`, with offsets into it."""
    sentences, offset = [], 0
    for line in text.split("\n"):
        line_offset = offset
        offset += len(line) + 1
        if _QUESTION_PREFIX.match(line):
            continue
        bullet = _BULLET.match(line)
        skip = bullet.end() if bullet else 0
        for sentence in _split_line(line[skip:], line_offset + skip):
            if _is_candidate(sentence.text):
                sentences.append(sentence)
    return sentences
