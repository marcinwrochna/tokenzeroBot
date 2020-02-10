#!/usr/bin/env python3
"""A bot for Wikipedia, creating redirects between 'and'/'&' variants."""
from __future__ import absolute_import
import logging
from itertools import chain
from typing import Optional, Set
import re

import pycld2  # Compact Language Detection
import pywikibot
import pywikibot.data.api
from pywikibot import Site

import utils
from utils import getCategoryAsSet, getPagesWithTemplate, getRedirectsToPage, \
    trySaving


def main() -> None:
    """Run the bot."""
    logging.basicConfig(level=logging.WARNING)
    # Initialize pywikibot.
    assert Site().code == 'en'
    utils.initLimits(
        editsLimits={'default': 4000},
        brfaNumber=6,
        onlySimulateEdits=False,
        botTrial=False
    )

    EnglishWordList.init()

    journals: Set[str] = getCategoryAsSet('Academic journals by language')
    magazines: Set[str] = getCategoryAsSet('Magazines by language')

    # Let 'foreign' be the set of page titles in a language-category
    # other than English, or in the multilingual category.
    foreign: Set[str] = set()
    foreign = foreign | journals
    foreign = foreign | magazines
    foreign = foreign - getCategoryAsSet('English-language journals')
    foreign = foreign - getCategoryAsSet('English-language magazines')
    foreign = foreign | getCategoryAsSet('Multilingual journals')
    foreign = foreign | getCategoryAsSet('Multilingual magazines')

    for page in chain(
            journals,
            magazines,
            getPagesWithTemplate('Infobox journal'),
            getPagesWithTemplate('Infobox Journal'),
            getPagesWithTemplate('Infobox magazine'),
            getPagesWithTemplate('Infobox Magazine')):
        pageTitle = page if isinstance(page, str) else page.title()
        try:
            makeAmpersandRedirects(pageTitle, foreign)
            for rPage in getRedirectsToPage(pageTitle, namespaces=0):
                makeAmpersandRedirects(rPage.title(), foreign, pageTitle)
        except pywikibot.exceptions.TitleblacklistError:
            print('Skipping (title blacklist error): ', pageTitle)


def makeAmpersandRedirects(
        pageTitle: str,
        foreign: Set[str],
        targetPageTitle: Optional[str] = None,
        andToAmpersand: bool = True,
        ampersandToAnd: bool = True) -> bool:
    """If pageTitle contains 'and'/'&', try creating redirect from '&'/'and'.

    `foreign` is a set of foreign-language titles to avoid.
    Return whether any edits made.
    """
    if len(pageTitle) > 95:
        print('Skipping (length): ', pageTitle)
        return False
    if not targetPageTitle:
        targetPageTitle = pageTitle
    rTitle = ''
    if ' and ' in pageTitle and andToAmpersand:
        rTitle = pageTitle.replace(' and ', ' & ')
        rTitle = rTitle.replace(', & ', ' & ')
    if ' & ' in pageTitle and ampersandToAnd:
        rTitle = pageTitle.replace(' & ', ' and ')
        # Exclude possibly-foreign titles based on categories and
        # on language detection.
        if pageTitle in foreign:
            print('Skipping (lang category): ', pageTitle)
            return False
        if not EnglishWordList.check(pageTitle):
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
    print(f'Creating redirect from [[{rTitle}]] to [[{targetPageTitle}]]')
    rNewContent = (
        f'#REDIRECT [[{targetPageTitle}]]\n'
        f'{{{{R from modification}}}}\n'
    )
    summary = 'Redirect between ampersand/and variant.'
    return trySaving(rPage, rNewContent, summary, overwrite=False)


class EnglishWordList:
    """Static class for checking whether a title is English."""

    wordSet: Set[str] = set()

    @staticmethod
    def init() -> None:
        """Initialize word list from /usr/share/dict/words."""
        # The words list includes too many 1-3 letter words, so we exclude
        # these and give our own short list.
        for word in ['a', 'an', 'the', 'of', 'art', 'gun', 'for', 'new', 'acm',
                     'age', 'air', 'all', 'and', 'war', 'use', 'to', 'tax',
                     'sun', 'tax', 'sky', 'tap', 'sex', 'on', 'or', 'owl',
                     'pop', 'oil', 'men', 'man', 'law', 'its', 'in', 'ibm',
                     'hiv/aids', 'dna', 'at', 'j', 'car', 'bioorganic',
                     'biomolecular']:
            EnglishWordList.wordSet.add(word)
        with open('/usr/share/dict/words') as f:
            for line in f:
                line = line.strip().casefold()
                # if len(line) > 2:
                if line not in ['co'] and len(line) > 3:
                    EnglishWordList.wordSet.add(line)
        for word in ['bianco', 'nero']:
            EnglishWordList.wordSet.remove(word)

    @staticmethod
    def check(title: str) -> bool:
        """Return whether each word in title is in dictionary."""
        for s in title.split():
            s = re.sub(r'[0-9(),&!\.\':\-\–\—’]', '', s).casefold()
            if s and s not in EnglishWordList.wordSet:
                print(f'Word "{s}" is not english."')
                return False
        return True


if __name__ == "__main__":
    main()
