"""
Glossary entry data model.

A GlossaryEntry defines a controlled engineering term with its canonical
definition, aliases, and usage guidance. This supports consistent
terminology across all artifacts.
"""

from __future__ import annotations

from pydantic import Field

from .common import ArtifactBase, ArtifactType


class GlossaryEntry(ArtifactBase):
    """
    Controlled terminology entry for propulsion control engineering.
    """
    artifact_type: ArtifactType = Field(
        default=ArtifactType.GLOSSARY_ENTRY,
        description="Must be 'glossary_entry'"
    )
    term: str = Field(
        description="The canonical term being defined"
    )
    canonical_definition: str = Field(
        description="The authoritative definition of this term within APLH context"
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Acceptable alternative names or abbreviations for this term"
    )
    disallowed_or_ambiguous_usages: list[str] = Field(
        default_factory=list,
        description="Terms or usages that are explicitly disallowed or flagged as ambiguous"
    )
    source_refs: list[str] = Field(
        default_factory=list,
        description="Source references for the definition"
    )
    owner_domain: str = Field(
        default="",
        description="Engineering domain responsible for this term"
    )
