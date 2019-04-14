"""The bot action that fills some autimatizable abbrevs, see doFillAbbrev()."""
import re
from typing import Optional

import mwparserfromhell
import pywikibot
from pywikibot import Site

from abbrevIsoBot import state
from abbrevIsoBot import abbrevUtils
from utils import trySaving, getInfoboxJournals


def doFillAbbrevs(scrapeLimit: Optional[int] = None) -> None:
    """Fill empty abbreviations in some automatizable cases.

    Currently the cases are:
    * abbreviation is equal to title, possibly without articles (a/the)
    """
    catName = 'Category:Infobox journals with missing ISO 4 abbreviations'
    cat = pywikibot.Category(Site(), catName)
    articles = cat.articles(namespaces=0, total=scrapeLimit, content=True)
    for n, page in enumerate(articles):
        print(f'--Scraping:\t{n}:\t[[{page.title()}]]', flush=True)
        for i, infobox in enumerate(getInfoboxJournals(page)):
            if infobox.get('abbreviation', '') != '':
                print('--Skipping infobox that actually has non-empty abbrev')
                continue
            title = abbrevUtils.stripTitle(page.title())
            if 'title' in infobox and infobox['title'] != title:
                print('--Skipping infobox with different title than article',
                      infobox['title'])
                continue
            cLang = abbrevUtils.getLanguage(infobox)
            cAbbrev = state.tryGetAbbrev(title, cLang)
            if cAbbrev is None:
                continue
            # If abbreviation is equal to title, up to "a/the" articles:
            if cAbbrev == re.sub(r'(The|the|A|a)\s+', '', title):
                print('--Filling "{}" with abbrev "{}"'.format(title, cAbbrev))
                trySaving(page, fillAbbreviation(page.text, i, cAbbrev),
                          'Filling trivial ISO-4 abbreviation. ',
                          overwrite=True)


def fillAbbreviation(pageText: str, whichInfobox: int, abbrev: str) -> str:
    """Return pageText with changed abbreviation in specified infobox."""
    p = mwparserfromhell.parse(pageText)
    i = 0
    for t in p.filter_templates():
        if t.name.matches('infobox journal') or \
           t.name.matches('Infobox Journal'):
            if i == whichInfobox:
                if t.has_param('title') and t.get('title')[0] == ' ':
                    abbrev = ' ' + abbrev
                t.add('abbreviation', abbrev, preserve_spacing=True)
            i = i + 1
    return str(p)
