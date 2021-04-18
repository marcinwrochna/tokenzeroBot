"""Common utility functions: getLanguage() and isSoftMatch()."""

import re
from typing import Dict


def getLanguage(infobox: Dict[str, str]) -> str:
    """Guess the language of an IJ's title.

    Returns 'eng' or 'all'. This affects which LTWA rules we use when
    selecting the abbrevISO computed abbreviation.
    We assume the title is English if the country is anglophone and the
    language parameter does not specify sth else. Note there are
    non-English titles with the language infobox parameter set to
    English, because they publish in English only.
    """
    englishCountries = ['United States', 'U.S.', 'U. S.', 'USA', 'U.S.A', 'US',
                        'United Kingdom', 'UK', 'England', 'UK & USA',
                        'New Zealand', 'Australia']
    lang = infobox.get('language', '')
    if not lang.strip() or lang.startswith('English'):
        if infobox.get('country', '') in englishCountries:
            return 'eng'
    return 'all'


def isSoftMatch(infoboxAbbrev: str, computedAbbrev: str) -> bool:
    """Check if abbrev can be considered correct comparing to computed one.

    For this we ignore capitalization, comments from the infobox abbreviation
    and ignore dependent titles from the computed abbreviation.
    Hence the matches are not necessarily exact, and you should prefer the
    infoboxAbbrev (which is human-edited) to the computedAbbrev.

    In the future we might want to be more strict about capitalization etc.
    """
    if infoboxAbbrev == computedAbbrev:
        return True
    infoboxAbbrev = infoboxAbbrev.lower()
    computedAbbrev = computedAbbrev.lower()
    shortInfoboxAbbrev = re.sub(r'\s*[\-\(:–,].*', '', infoboxAbbrev)
    shortComputedAbbrev = re.sub(r'\s*[\-\(:–,].*', '', computedAbbrev)
    if infoboxAbbrev == computedAbbrev or shortInfoboxAbbrev == shortComputedAbbrev:
        return True
    return False


def stripTitle(t: str) -> str:
    """Remove disambuig comments from wiki title (before computing abbrev)."""
    t = re.sub(r'\s*\(.*(ournal|agazine|eriodical|eview).*\)', '', t)
    return t

def sanitizeField(s: str) -> str:
    """Remove comments and some other markup, get first line if many."""
    s = re.sub(r'<ref>.*</ref>', '', s)
    s = re.sub(r'<!--.*-->', '', s)
    s = re.sub(r'<br\s*/?>.*', '', s)
    match = re.search(r'{{\s*lang\|\s*en\s*\|([^}]*)}}', s)
    if match:
        s = match.group(1)
    return s.strip()
