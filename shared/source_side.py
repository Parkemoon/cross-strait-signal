"""Which side of the strait a news source speaks from, and which publication
a section feed belongs to. Pure functions on the `sources` columns — shared
by the LinkedIn selector (shared/linkedin_selector.py), the visits coverage
endpoint (api/routes/visits.py) and anything else that pairs Taiwan-side
and PRC-side coverage of one story.

Sides: TW = place 'TW' with bias green … blue (place is required because
Zaobao and BBC Chinese are also `centrist`); PRC = bias state_official /
state_nationalist / china_centrist, which deliberately admits RTHK and
Ming Pao (HK) as Beijing-side voices. Everything else (international
outlets, unlabelled rows) is neither side.

"Outlet" collapses section feeds to the publication (UDN + UDN Breaking =
one outlet), mirroring the feed's PUBLICATION_NAMES in SourceBadge.jsx.
"""
from __future__ import annotations

TW_SIDE_BIASES = {'green', 'green_leaning', 'centrist', 'blue_leaning', 'blue'}
PRC_SIDE_BIASES = {'state_official', 'state_nationalist', 'china_centrist'}

# Section feeds → publication. Anything not listed is its own outlet.
_SECTION_PREFIXES = (
    ('LTN ', 'Liberty Times'),
    ('CNA ', 'CNA'),
    ('UDN', 'United Daily News'),
    ('CT ', 'China Times'),
    ('Ming Pao', 'Ming Pao'),
)


def outlet_of(source_name: str | None) -> str:
    name = (source_name or '').strip()
    for prefix, pub in _SECTION_PREFIXES:
        if name.startswith(prefix):
            return pub
    return name


def side_of(place: str | None, bias: str | None) -> str | None:
    """'TW', 'PRC' or None (international / unlabelled)."""
    if bias in PRC_SIDE_BIASES:
        return 'PRC'
    if place == 'TW' and bias in TW_SIDE_BIASES:
        return 'TW'
    return None
