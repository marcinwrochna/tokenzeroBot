#!/usr/bin/env python3
"""A bot for Wikipedia, creating redirects between 'and'/'&' variants."""
from __future__ import absolute_import
import logging
from itertools import chain
from typing import Set

import pycld2  # Compact Language Detection
import pywikibot
import pywikibot.data.api
from pywikibot import Site

import utils
from utils import getCategoryAsSet, getPagesWithTemplate, trySaving


def main() -> None:
    """Run the bot."""
    logging.basicConfig(level=logging.WARNING)
    # Initialize pywikibot.
    assert Site().code == 'en'
    utils.initLimits(
        editsLimits={'default': 3000},
        brfaNumber=6,
        onlySimulateEdits=True,
        botTrial=False
    )

    # Let 'foreign' be the set of page titles in a language-category
    # other than English, or in the multilingual category.
    foreign: Set[str] = set()
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
            getPagesWithTemplate('Infobox Magazine')):
        makeAmpersandRedirects(page.title(), foreign)


def makeAmpersandRedirects(
        pageTitle: str, foreign: Set[str],
        andToAmpersand: bool = True, ampersandToAnd: bool = True) -> bool:
    """If pageTitle contains 'and'/'&', try creating redirect from '&'/'and'.

    `foreign` is a set of foreign-language titles to avoid.
    Return whether any edits made.
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
            return False
        isReliable, _, details = \
            pycld2.detect(pageTitle, isPlainText=True)
        if not isReliable or details[0][0] != 'ENGLISH':
            print('Skipping (lang detect): ', pageTitle)
            print(isReliable, str(details))
            return False
    if not rTitle:
        return False
    # Try creating a redirect from rTitle to pageTitle.
    rPage = pywikibot.Page(Site(), rTitle)
    # Skip if the page already exists.
    if rPage.exists():
        print('Skipping (already exists): ', rTitle)
        return False
    # Create the redirect.
    print(f'Creating redirect from [[{rTitle}]] to [[{pageTitle}]]')
    rNewContent = f'#REDIRECT [[{pageTitle}]]\n{{{{R from modification}}}}\n'
    summary = 'Redirect between ampersand/and variant.'
    return trySaving(rPage, rNewContent, summary, overwrite=False)


if __name__ == "__main__":
    main()
