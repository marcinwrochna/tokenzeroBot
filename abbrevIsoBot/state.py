"""A module for the state, shared between runs and with abbrevIsoBot.js."""

import json
from typing import Any, Dict, Optional

# `state` is a global variable maintained between runs.
# state = {
#     'pages': {
#         'Wiki Page Title': {
#             'infoboxes': [{'title': 'IJ Title',
#                            'issn': ...,
#                            'abbreviation': ...,
#                            ...},
#                           ...
#             ],
#             'redirects': {
#                 'Redirect Page Title': 'Redirect Page Wikitext Content',
#                 ...
#             },
#         },
#         ...
#     },
#     'abbrevs': {
#         'Wiki Page or Infobox Tile': {
#             'eng': 'abbrevISO-computed abbreviation
#                 using only eng,mul,lat,und LTWA rules',
#             'all': 'using all rules'
#         },
#         ...
#     }
__state = {}  # type: Dict[str, Dict[str, Any]]
_stateFileName = ''


def loadOrInitState(stateFileName: str) -> None:
    """Load `state` from `STATE_FILE_NAME` or create a new one."""
    global __state  # pylint: disable=global-statement
    global _stateFileName  # pylint: disable=global-statement
    _stateFileName = stateFileName
    print(f"BBB Loading from {stateFileName}")
    opened = False
    try:
        with open(stateFileName, 'rt') as f:
            opened = True
            __state = json.load(f)
    except IOError:
        # If there's an error after opening, when reading, we don't catch the
        # exception but fail instead, so the state file is not overwritten.
        if opened:
            raise
        else:
            print('Initiating empty bot state.')
            __state = {'pages': {}, 'abbrevs': {}}


def saveState(stateFileName: str) -> None:
    """Save `state` to `STATE_FILE_NAME`."""
    print(f"BBB Saving to {stateFileName}")
    with open(stateFileName, 'wt') as f:
        json.dump(__state, f)


def dump() -> str:
    """Return formatted JSON of the state."""
    return json.dumps(__state, indent="\t")


def saveTitleToAbbrev(title: str, language: Optional[str] = None) -> None:
    """Save `title` for computing its abbrev later with exampleScript.js."""
    if title not in __state['abbrevs']:
        __state['abbrevs'][title] = {
            'all': None,
            'eng': None,
            'matchingPatterns': None
        }
    if language is not None:
        if language not in __state['abbrevs'][title]:
            __state['abbrevs'][title][language] = None


class NotComputedYetError(LookupError):
    """Raised when abbreviations for a title have not been computed yet."""

    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.message = (f'No computed abbreviation stored for "{title}", '
                        f'please rerun "exampleScript.js {_stateFileName}".')


def hasAbbrev(title: str, language: Optional[str] = None) -> bool:
    """Return whetever the abbrev for given title is saved and computed."""
    if title not in __state['abbrevs']:
        return False
    elif language is None:
        return bool(__state['abbrevs'][title])
    elif language not in __state['abbrevs'][title]:
        return False
    else:
        return bool(__state['abbrevs'][title][language])


def getAbbrev(title: str, language: str) -> str:
    """Return abbreviation for given (page or infobox) title.

    `language` should be 'all' or comma-separated list of ISO 639-2 codes,
    e.g. 'eng' for English. Multilingual 'mul' is always appended anyway.
    """
    if (title not in __state['abbrevs']
            or not __state['abbrevs'][title]
            or language not in __state['abbrevs'][title]
            or not __state['abbrevs'][title][language]):
        raise NotComputedYetError(title)
    return __state['abbrevs'][title][language]


def tryGetAbbrev(title: str, language: str) -> Optional[str]:
    """Return abbreviation if computed, otherwise store for later computing."""
    result = None
    try:
        result = getAbbrev(title, language)
    except NotComputedYetError as err:
        print(err.message)
        saveTitleToAbbrev(title, language)
    return result


def getAllAbbrevs(title: str) -> Dict[str, str]:
    """Return dict from language to abbrev, for a given title to abbreviate."""
    if title not in __state['abbrevs'] or not __state['abbrevs'][title]:
        raise NotComputedYetError(title)
    result = __state['abbrevs'][title].copy()
    result.pop('matchingPatterns')
    return result


def getMatchingPatterns(title: str) -> str:
    """Return matching LTWA patterns for given title to abbreviate."""
    if (title not in __state['abbrevs']
            or not __state['abbrevs'][title]
            or 'matchingPatterns' not in __state['abbrevs'][title]):
        raise NotComputedYetError(title)
    return __state['abbrevs'][title]['matchingPatterns']


def savePageData(pageTitle: str, pageData: Dict[str, Any]) -> None:
    """Save a scraped page's data.

    `pageData` is of the following form:
        {'infoboxes': [
                {'title': .., 'abbreviation': .., 'issn': .., ...},
                ...
            ],
         'redirects': {
                redirectTitle: redirectContent,
                ...
            }
        }
    """
    __state['pages'][pageTitle] = pageData


def getPageData(pageTitle: str) -> Dict[str, Any]:
    """Return latest saved page data (in a scrape run of the script)."""
    return __state['pages'][pageTitle]


def getPagesDict() -> Dict[str, Dict[str, Any]]:
    """Return dictionary from pageTitle to pageData."""
    return __state['pages']
