from typing import TypedDict, Set, Dict

"""
CONCEPT_SETS is now the SINGLE source of truth.

- dict keys: canonical heads (theory-driven)
- dict values:
    - allowed_variants: forms that may be normalised to this head
    - false_positives: forms that must never be normalised to this head, even if
      they are close in spelling or embedding space.

For FastText, normalisation is restricted to orthographic- and boundary-level variation characteristic
of early modern print and OCR, including the collapse of whitespace between function words
and lexical heads (eg `ofjustice`). These forms are treated as recoverable tokenisation
artefacts rather than distinct lexical items. Semantic distinctions between canonical
concepts are preserved through explicit constraints, positive and negative, on allowable mappings.

Since dropping FastText, most of the forms are discoverable from the keys. Eventually this will be
a mere seed table and new terms will come from interactive search, and new false positives from user input.

"""
class CanonicalRule(TypedDict):
    forms: Set[str]
    expected: Set[str]
    false_positives: Set[str]

CanonicalRules = Dict[str, CanonicalRule]

