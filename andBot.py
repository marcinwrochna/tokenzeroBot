#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
A bot for Wikipedia, creating redirects between 'and'/'&' variants.
"""
from __future__ import unicode_literals
import logging
#import re
#import sys
#from unicodedata import normalize

import pywikibot
import pywikibot.data.api
#import mwparserfromhell


# Some basic config
scrapeLimit = 50000  # Max number of pages to scrape.
totalEditLimit = 1  # Max number of edits to make (in one run of the script).
onlySimulateEdits = True  # If true, only print what we would do, don't edit.

site = None # pywikibot's main object.

def main():
    global site
    logging.basicConfig(level=logging.WARNING)
    # Initialize pywikibot.
    site = pywikibot.Site('en')

    totalEditCount = 0
    foreign = set()
    cat = pywikibot.Category(site, 'Category:Academic journals by language')
    for page in cat.articles(recurse=True, namespaces=0, total=scrapeLimit, content=False):
         foreign.add(page.title())
    cat = pywikibot.Category(site, 'Category:English-language journals')
    for page in cat.articles(recurse=False, namespaces=0, total=scrapeLimit, content=False):
         foreign.discard(page.title())
    cat = pywikibot.Category(site, 'Category:Multilingual journals')
    for page in cat.articles(recurse=False, namespaces=0, total=scrapeLimit, content=False):
        foreign.add(page.title())

    for t in foreign:
        if ' & ' in t:
            print('Skipped foreign title: ' + t)
    for page in getPagesWithInfoboxJournals(scrapeLimit):
        if page.title() not in foreign:
    #cat = pywikibot.Category(site, 'Category:French-language journals')
    #for page in cat.articles(recurse=False, namespaces=0, total=scrapeLimit, content=False):
            editCount = makeAmpersandRedirects(page.title())
            totalEditCount = totalEditCount + editCount
            if totalEditCount >= totalEditLimit:
                break


def makeAmpersandRedirects(pageTitle):
    """ If pageTitle contains 'and' or '&', create a redirect from '&' or 'and',
    respectively (unless the latter page already exists).

    Return number of edits made.
    """
    rTitle = ''
    if ' and ' in pageTitle:
        rTitle = pageTitle.replace(' and ', ' & ')
    elif ' & ' in pageTitle:
        rTitle = pageTitle.replace(' & ', ' and ')
    if not rTitle:
        return 0
    # Try creating a redirect from rTitle to page.title().
    rPage = pywikibot.Page(site, rTitle)
    # Skip if rTitle already exists.
    if rPage.exists():
        print('[['+ rTitle + ']] already exists.')
        return 0
    # Create the redirect.
    print('Creating redirect from [['+ rTitle + ']] to [['+ pageTitle +']].')
    rNewContent = '#REDIRECT [[' + pageTitle + ']]\n'
    rNewContent += '{{R from modification}}\n'
    if not onlySimulateEdits:
        rPage.text = rNewContent
        rPage.save(
            u'Redirect between ampersand/and variant. '
            + u'Report bugs and suggestions '
            + u' to [[User talk:TokenzeroBot]]',
            minor=False,
            botflag=True,
            watch="nochange",
            createonly=True)
        return 1
    return 0


def getPagesWithInfoboxJournals(limit):
    """ Get generator yielding all Pages that include an {{infobox journal}}.
    """
    ns = site.namespaces['Template']  # 10
    template = pywikibot.Page(site, 'Template:Infobox journal', ns=ns)
    return template.embeddedin(
        filter_redirects=False,  # Omit redirects
        namespaces=0,  # Mainspace only
        total=limit,   # Limit total number of pages outputed
        content=False) # Do not immediately fetch content


if __name__ == "__main__":
    main()
