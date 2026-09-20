"""Decoders and generic parsers (ADR-019, ADR-027 §2).

``decode`` turns raw Bronze bytes into a ``DecodedDocument`` per the manifest's
``contract.decode``; the generic parsers turn a decoded document into ``SourceRecord`` values
in the source's vocabulary. Both are platform code: a target contributes a parser only when the
generic one for its modality is insufficient, and even then it receives the decoded document.
"""

from energy_platform.parse.decode import DecodeError, SoapFault, decode
from energy_platform.parse.generic import (
    ParseError,
    generic_parser,
    parser_ref,
    required_source_fields,
)

__all__ = [
    "DecodeError",
    "ParseError",
    "SoapFault",
    "decode",
    "generic_parser",
    "parser_ref",
    "required_source_fields",
]
