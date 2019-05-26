"""Various common utils shared by the bots."""
import re
from typing import Dict, Iterator, Optional, Set
import unicodedata

import mwparserfromhell
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


def initLimits(editsLimits: Dict[str, int],
               brfaNumber: int,
               onlySimulateEdits: bool,
               botTrial: bool = False,
               listLimit: Optional[int] = None) -> None:
    """Init module config, in particular limits for trySaving().

    `editsLimits` - for each limit type (any string), this gives a limit for
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
    _editsLimits = editsLimits.copy()
    _editsDone = editsLimits.copy()
    for limitType in editsLimits:
        _editsDone[limitType] = 0
    _listLimit = listLimit
    _brfaNumber = brfaNumber
    _onlySimulateEdits = onlySimulateEdits
    _botTrial = botTrial
    brfa = f'Wikipedia:Bots/Requests_for_approval/{_botName}_{_brfaNumber}'
    assert pywikibot.Page(pywikibot.Site(), brfa).exists(), \
        f'BRFA page "{brfa}" does not exist!'


def isLimitReached(limitType: str = 'default') -> bool:
    """Return whether we reached the given limit of edits.

    That is, whether the number of calls to trySaving() with this limitType
    is greater than or equal to the number that was given to initLimits().
    """
    if limitType not in _editsLimits or limitType not in _editsDone:
        raise Exception(f'Undefined limit type: "{limitType}"')
    return _editsDone[limitType] >= _editsLimits[limitType]


def trySaving(page: pywikibot.Page,
              content: str,
              summary: str,
              overwrite: bool,
              limitType: str = 'default') -> bool:
    """Create or overwrite page with given content, checking bot limits.

    Summary is prepended with link to BRFA and appended with 'Report problems'.
    """
    global _editsDone  # pylint: disable=global-statement
    if limitType not in _editsLimits or limitType not in _editsDone:
        raise Exception(f'Undefined limit type: "{limitType}"')
    if _editsDone[limitType] >= _editsLimits[limitType]:
        return False
    _editsDone[limitType] += 1
    if _onlySimulateEdits:
        return False
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


def tryPurging(page: pywikibot.Page) -> bool:
    """Purge page cache at Wikipedia, unless _onlySimulateEdits."""
    if _onlySimulateEdits:
        return False
    return page.purge()


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
            total=_listLimit,
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
    assert template.exists()
    return template.embeddedin(
        filter_redirects=False,  # Omit redirects
        namespaces=0,            # Mainspace only
        total=_listLimit,       # Limit total number of pages outputed
        content=content)         # Whether to immediately fetch content
    # Another way to get pages including a template is the following wrapper:
    #   from pywikibot import pagegenerators as pg
    #   gen = pg.ReferringPageGenerator(template, onlyTemplateInclusion=True)


def getRedirectsToPage(
        pageTitle: str, namespaces: int = 0,
        total: Optional[int] = None, content: bool = False) \
        -> Iterator[pywikibot.Page]:
    """Yield all pages that are redirects to `page`.

    Note that page.backlinks(filterRedirects=True) should not be used!
    It also returns pages that include a link to `page` and happend to
    be redirects to a different, unrelated page (e.g. every redirect
    from a Bluebook abbrev includes a [[Bluebook]] link).
        for r in page.backlinks(followRedirects=False, filterRedirects=True,
                                namespaces=0, total=100, content=True):
    Note also we disregard double redirects: these are few and
    eventually resolved by dedicated bots.
    """
    gen = Site()._generator(  # pylint: disable=protected-access
        pywikibot.data.api.PageGenerator,
        type_arg="redirects",
        titles=pageTitle,
        grdprop="pageid|title|fragment",
        namespaces=namespaces,
        total=total,
        g_content=content)
    # Workaround bug: https://phabricator.wikimedia.org/T224246
    for page in gen:
        if page.namespace().id == namespaces:
            yield page


def getInfoboxJournals(page: pywikibot.Page) \
        -> Iterator[Dict[str, str]]:
    """Yield all {{infobox journal}}s used in `page`.

    Each as a dict from param to value.
    Parameters are stripped and normalized to lowercase.
    Values are stripped and '<!--.*--->' comments are removed.
    """
    # We could use the pywikibot interface mwparserfromhell instead, but it may
    # fall-back to regex, reorder parameters, and mwpfh is better documented.
    #   p = pywikibot.textlib.extract_templates_and_params(page.text)
    #   text = pywikibot.textlib.glue_template_and_params(p)
    p = mwparserfromhell.parse(unicodedata.normalize('NFC', page.text))

    # Iterate over {{infobox journal}} template instances on `page`.
    # We ignore synonims of [[Template:Infobox journals]], see:
    # https://en.wikipedia.org/w/index.php?title=Special:WhatLinksHere/Template:Infobox_journal&hidetrans=1&hidelinks=1
    # except for the other capitalization 'Infobox Journal'.
    # Note 'Infobox journal' is equivalent to 'infobox journal' to mediawiki
    # and hence mwpfh normalizes it (to capitalize the fisrt letter).
    for t in p.filter_templates():
        if t.name.matches('infobox journal') or \
           t.name.matches('Infobox Journal'):
            infobox = {}
            for param in t.params:
                paramName = str(param.name).lower().strip()
                infobox[paramName] = re.sub(r'<!--.*-->', '',
                                            str(param.value)).strip()
            yield infobox
