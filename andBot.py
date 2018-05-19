#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
A bot for Wikipedia, creating redirects between 'and'/'&' variants.
"""
from __future__ import unicode_literals
import logging
from itertools import chain
#import re
#import sys
#from unicodedata import normalize

import pycld2 # Compact Language Detection

import pywikibot
import pywikibot.data.api
#import mwparserfromhell


# Some basic config
scrapeLimit = 50000  # Max number of pages to scrape.
totalEditLimit = 9  # Max number of edits to make (in one run of the script).
onlySimulateEdits = False  # If true, only print what we would do, don't edit.

site = None # pywikibot's main object.

def main():
    global site
    logging.basicConfig(level=logging.WARNING)
    # Initialize pywikibot.
    site = pywikibot.Site('en')

    totalEditCount = 0
    # Let 'foreign' be the set of page titles in a language-category
    # other than english, or in the multilingual category.
    foreign = set()
    foreign = foreign | getCategoryAsSet('Academic journals by language')
    foreign = foreign | getCategoryAsSet('Magazines by language')
    foreign = foreign - getCategoryAsSet('English-language journals')
    foreign = foreign - getCategoryAsSet('English-language magazines')
    foreign = foreign | getCategoryAsSet('Multilingual journals')
    foreign = foreign | getCategoryAsSet('Multilingual magazines')

    for page in chain(
            getPagesWithTemplate('Infobox journal'),
            getPagesWithTemplate('Infobox Journal'),
            getPagesWithTemplate('Infobox magazine'),
            getPagesWithTemplate('Infobox Magazine')
    ):
        editCount = makeAmpersandRedirects(page.title(), foreign)
        totalEditCount = totalEditCount + editCount
        if totalEditCount >= totalEditLimit:
            break


def makeAmpersandRedirects(
        pageTitle, foreign, andToAmpersand=False, ampersandToAnd=True):
    """ If pageTitle contains 'and' or '&', create a redirect from '&' or 'and',
    respectively (unless the latter page already exists).

    `foreign` is a set of foreign-language titles to avoid.
    Return number of edits made.
    """
    rTitle = ''
    if ' and ' in pageTitle and andToAmpersand:
        rTitle = pageTitle.replace(' and ', ' & ')
    if ' & ' in pageTitle and ampersandToAnd:
        rTitle = pageTitle.replace(' & ', ' and ')
        # Exclude possibly-foreign titles based on categories and
        # on language detection.
        if pageTitle in foreign:
            print('Skipping (lang category): ', pageTitle)
            return 0
        isReliable, _, details = \
            pycld2.detect(pageTitle, isPlainText=True)
        if not isReliable or details[0][0] != 'ENGLISH':
            print('Skipping (lang detect): ', pageTitle)
            print(isReliable, str(details))
            return 0
    if not rTitle:
        return 0
    # Try creating a redirect from rTitle to pageTitle.
    rPage = pywikibot.Page(site, rTitle)
    # Skip if the page already exists.
    if rPage.exists():
        print('Skipping (already exists): ', rTitle)
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


def getCategoryAsSet(name, recurse=True, namespaces=0):
    """ Get all titles of pages in given category as a set().

    ``name`` should not include 'Category:'.
    Be careful with `recurse`, you may accidentally get really deep into
    millions of pages.
    """
    print('Getting category:', name, flush=True)
    result = set()
    count = 0
    if not name.startswith('Category:'):
        name = 'Category:' + name
    cat = pywikibot.Category(site, name)
    for page in cat.articles(
            recurse=recurse,
            namespaces=namespaces,
            content=False):
        result.add(page.title())
        count = count + 1
    print('Got', str(count), 'pages.', flush=True)
    return result


def getPagesWithTemplate(name, content=False):
    """ Return generator yielding mainspace, non-redirect pages transcluding
    given template.

    Note that while the first letter is normalized, others are not,
    so check synonyms (redirects to the template):
        https://en.wikipedia.org/w/index.php?title=Special:WhatLinksHere/Template:Infobox_journal&hidetrans=1&hidelinks=1
    """
    if not name.startswith('Template:'):
        name = 'Template:' + name
    ns = site.namespaces['Template']
    template = pywikibot.Page(site, name, ns=ns)
    return template.embeddedin(
        filter_redirects=False, # Omit redirects
        namespaces=0,           # Mainspace only
        total=scrapeLimit,      # Limit total number of pages outputed
        content=content)        # Whether to immediately fetch content


if __name__ == "__main__":
    main()
