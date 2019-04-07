"""Various common utils shared by the bots."""
from typing import Dict, Iterator, Optional, Set

import pywikibot
import pywikibot.data.api
from pywikibot import Site

# Configuration used in the module, see `initLimits()`.
_editsLimits: Dict[str, int] = {'default': 1}
_editsDone: Dict[str, int] = {'default': 0}
_botName = 'TokenzeroBot'
_brfaNumber = 0
_onlySimulateEdits = True
_botTrial = False
_listLimit: Optional[int] = None


def initLimits(editLimits: Dict[str, int],
               brfaNumber: int,
               onlySimulateEdits: bool,
               botTrial: bool = False,
               listLimit: Optional[int] = None) -> None:
    """Init module config, in particular limits for trySaving().

    `editLimits` - for each limit type (any string), this gives a limit for
        the number of pages modified with trySaving(limitType=...),
        in a single run of the script. The default limitType is 'default'.
    `brfaNumber` - used to prepend link to Bot Request For Approval.
    `onlySimulateEdits` - if true, no pages are ever saved by trySaving().
    `botTrial` - if true, we add the 'bot trial' tag to all edits.
    `listLimit` - max number of items returned by generators in this module.
    """
    # pylint: disable=global-statement
    global _editsLimits, _editsDone, _brfaNumber, _onlySimulateEdits, \
        _botTrial, _listLimit
    _editLimits = editLimits.copy()
    _editsDone = editLimits.copy()
    for limitType in editLimits:
        editLimits[limitType] = 0
    _listLimit = listLimit
    _brfaNumber = brfaNumber
    _onlySimulateEdits = onlySimulateEdits
    _botTrial = botTrial
    brfa = f'Wikipedia:Bots/Requests_for_approval/{_botName}_{_brfaNumber}'
    assert pywikibot.Page(pywikibot.Site(), brfa).exists(), \
        f'BRFA page "{brfa}" does not exist!'


def trySaving(page: pywikibot.Page,
              content: str,
              summary: str,
              overwrite: bool,
              limitType: str = 'default') -> bool:
    """Create or overwrite page with given content, checking bot limits.

    Summary is prepended with link to BRFA and appended with 'Report problems'.
    """
    global _editsDone  # pylint: disable=global-statement
    if _onlySimulateEdits:
        return False
    if limitType not in _editsLimits or limitType not in _editsDone:
        raise Exception(f'Undefined limit type: "{limitType}"')
    if _editsDone[limitType] >= _editsLimits[limitType]:
        return False
    _editsDone[limitType] += 1
    page.text = content
    summary = (f'[[Wikipedia:Bots/Requests_for_approval/'
               f'{_botName}_{_brfaNumber}|({_brfaNumber})]] '
               f'{summary} [[User talk:TokenzeroBot|Report problems]]')
    page.save(summary,
              minor=False,
              botflag=True,
              watch="nochange",
              createonly=False if overwrite else True,
              nocreate=True if overwrite else False,
              tags='bot trial' if _botTrial else None)
    return True


def getCategoryAsSet(name: str, recurse: bool = True, namespaces: int = 0) \
        -> Set[str]:
    """Get all titles of pages in given category as a set().

    ``name`` should not include 'Category:'.
    Be careful with `recurse`, you may accidentally get really deep into
    millions of pages.
    """
    print('Getting category:', name, flush=True)
    result = set()
    count = 0
    if not name.startswith('Category:'):
        name = 'Category:' + name
    cat = pywikibot.Category(Site(), name)
    for page in cat.articles(
            recurse=recurse,
            namespaces=namespaces,
            content=False):
        result.add(page.title())
        count = count + 1
    print('Got', str(count), 'pages.', flush=True)
    return result


def getPagesWithTemplate(name: str, content: bool = False) \
        -> Iterator[pywikibot.Page]:
    """Yield all mainspace, non-redirect pages transcluding given template.

    Note that while the first letter is normalized, others are not,
    so check synonyms (redirects to the template):
        https://en.wikipedia.org/w/index.php?title=Special:WhatLinksHere/Template:Infobox_journal&hidetrans=1&hidelinks=1
    """
    if not name.startswith('Template:'):
        name = 'Template:' + name
    ns = Site().namespaces['Template']
    template = pywikibot.Page(Site(), name, ns=ns)
    return template.embeddedin(
        filter_redirects=False,  # Omit redirects
        namespaces=0,            # Mainspace only
        total=_listLimit,       # Limit total number of pages outputed
        content=content)         # Whether to immediately fetch content
