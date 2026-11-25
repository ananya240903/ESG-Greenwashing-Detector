"""Regulation tagging: which BRSR topics a claim is about.

Four of the topics are attributes of SEBI's BRSR Core (2023), the subset of BRSR disclosures
that listed companies must have independently assured: GHG footprint, water footprint, energy
footprint, and embracing circularity (waste). A claim on one of those is a claim about a
number the company has to get assured, which makes it worth checking first. The others map
to the BRSR principle that asks about them.

Tagging is by keyword, so every tag can be explained by the word that triggered it. It is
not evaluated against labels; the gold set does not record topics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    brsr_core: str | None   # the BRSR Core attribute, if this topic is one
    principle: int          # the BRSR principle that asks about it
    pattern: re.Pattern


def _words(*alternatives: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(alternatives) + r")", re.IGNORECASE)


TOPICS = [
    Topic("ghg", "GHG emissions", "GHG footprint", 6, _words(
        r"ghg", r"greenhouse", r"carbon", r"co2", r"co₂", r"tco2", r"scope\s*[123]\b", r"net[\s-]?zero",
        r"decarboni[sz]", r"climate change", r"emission")),
    Topic("water", "Water", "Water footprint", 6, _words(
        r"water", r"waste\s*water", r"effluent", r"zero liquid discharge", r"zld\b", r"rainwater",
        r"groundwater", r"kilo\s*lit", r"kl\b", r"desalinat")),
    Topic("energy", "Energy", "Energy footprint", 6, _words(
        r"energy", r"renewable", r"solar", r"wind\b", r"electricity", r"power (?:consumption|generation)",
        r"fuel", r"efficien")),
    Topic("waste", "Waste and circularity", "Embracing circularity", 6, _words(
        r"waste\b", r"wastes\b", r"recycl", r"circular", r"reuse", r"re-use", r"landfill", r"hazardous",
        r"e-waste", r"plastic", r"epr\b", r"packaging", r"by-product")),
    Topic("biodiversity", "Biodiversity and land", None, 6, _words(
        r"biodiversity", r"forest", r"trees?\b", r"plantation", r"afforest", r"saplings?", r"ecolog",
        r"wildlife", r"mangrove", r"carbon sink", r"habitat")),
    Topic("air", "Air pollution", None, 6, _words(
        r"air quality", r"air emission", r"air pollut", r"sox\b", r"nox\b", r"particulate", r"pm\s?(?:2\.5|10)",
        r"dust", r"stack emission")),
    Topic("sourcing", "Sustainable sourcing and value chain", None, 2, _words(
        r"sustainabl[ey] sourc", r"responsibl[ey] sourc", r"suppliers?\b", r"value chain", r"procure",
        r"sourcing")),
]
BY_KEY = {t.key: t for t in TOPICS}


def tag(sentence: str) -> list[str]:
    """Topic keys for a claim, in TOPICS order; empty when none applies."""
    return [t.key for t in TOPICS if t.pattern.search(sentence)]


def brsr_core(keys: list[str]) -> list[str]:
    return [BY_KEY[k].brsr_core for k in keys if BY_KEY[k].brsr_core]
