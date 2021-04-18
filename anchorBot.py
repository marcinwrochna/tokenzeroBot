#!/usr/bin/env python3
"""A bot foradding anchors to redirects to a given list page."""
import logging
import re
import sys
from typing import List, Tuple

import pywikibot
import pywikibot.data.api
from pywikibot import Site

from utils import initLimits, getRedirectsToPage, trySaving


def main() -> None:
    """Execute the bot."""
    logging.basicConfig(level=logging.WARNING)
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} "Title of List Page"')
        return
    listTitle = sys.argv[1]

    # Initialize pywikibot.
    assert Site().code == 'en'
    initLimits(
        editsLimits={'default': 2000},
        brfaNumber=6,
        onlySimulateEdits=False,
        botTrial=False
    )

    listPage = pywikibot.Page(Site(), listTitle)
    if not listPage.exists():
        raise Exception(f'Page [[{listTitle}]] does not exist.')
    print(f'List: [[{listTitle}]]')
    # for rTitle, anchor in parseList(listPage.text):
    #     fixRedirectAnchor(rTitle, anchor, listTitle)
    exceptions = [
        'List of Hindawi academic journals',
        'Hindawi academic journal',
        'List of MDPI academic journals',
        'List of MDPI journals',
        'List of Dove Medical Press academic journals',
        'List of Dove Press academic journals',
        'List of Medknow Publications academic journals',
        'List of Nature Research journals']
    for rPage in getRedirectsToPage(listTitle, namespaces=0, content=True):
        rTitle = rPage.title()
        if rTitle not in exceptions:
            fixRedirectAnchor(rTitle, getPredictedAnchor(rTitle), listTitle)


def parseList(page: str) -> List[Tuple[str, str]]:
    """Parse given wikicode of a List page."""
    result: List[Tuple[str, str]] = []
    currentSection = ''
    for part in page.split('==='):  # Sometimes should be ==
        part = part.strip()
        if len(part) == 1:
            currentSection = part
            continue
        if not currentSection:
            continue

        for line in re.findall(r"^\*''(.*)''$", part, re.MULTILINE):
            m = re.search(r'^\[\[([^\|]+)(\|.*)?\]\]$', line)
            if m:
                result.append((m.group(1), currentSection))
            else:
                if '[' not in line:
                    result.append((line, currentSection))
                else:
                    print('WARNING: unexpected "[" in: ' + repr(line))
    return result


def fixRedirectAnchor(rTitle: str, anchor: str, target: str) -> bool:
    """Add an anchor to given redirect page."""
    rPage = pywikibot.Page(Site(), rTitle)
    addJournal = False
    if rPage.exists() and not rPage.isRedirectPage():
        addJournal = True
        if 'journal' in rTitle.lower():
            print(f'Skip: [[{rTitle}]] already exists, '
                  'title already has "journal".', flush=True)
            return False
        for cat in rPage.categories():
            if 'journal' in cat.title().lower():
                print(f'Skip: [[{rTitle}]] already exists, '
                      'has category containing "journal".', flush=True)
                return False
    if addJournal:
        rPage = pywikibot.Page(Site(), rTitle + ' (journal)')
    if not rPage.exists() or not rPage.isRedirectPage():
        print(f'Not exists/not a redirect: [[{rPage.title()}]]', flush=True)
        return False
    # Page.title() actually contains anchor, if redirect had one.
    actualTarget = rPage.getRedirectTarget().title().split('#', 1)
    if actualTarget[0] != target:
        print(f'Not a redirect to this list: '
              f'[[{rPage.title()}]] -> [[{actualTarget[0]}]]', flush=True)
        return False
    if len(actualTarget) > 1:
        if actualTarget[1] != anchor:
            print(f'WARNING: Anchor mismatch: '
                  f'[[{rPage.title()}]] -> [[{actualTarget[0]}]].'
                  f'Is "{actualTarget[1]}" should be "{anchor}".')
            return False
        else:
            return True
    predictedAnchor = getPredictedAnchor(rTitle)
    if predictedAnchor != anchor:
        print(f'WARNING: Anchor mismatch: '
              f'[[{rPage.title()}]] -> [[{actualTarget[0]}]].'
              f'Predicted "{predictedAnchor}" should be "{anchor}".')
        return False

    rText = rPage.text
    rNewText = re.sub(r'''(
                              \#\s*REDIRECT\s*\[\[
                              [^\]\#]+             # title
                          )
                          (\#[^\]]*)?              # anchor
                          \]\]''',
                      '\\1#' + anchor + ']]',
                      rText, count=1, flags=re.VERBOSE)
    if rText == rNewText:
        print(f'Nothing to do on: [[{rPage.title()}]]')
        return True
    print(f'===CHANGING [[{rPage.title()}]] FROM==================')
    print(rText)
    print('==========TO===========')
    print(rNewText + '\n\n', flush=True)
    trySaving(rPage, rNewText,
              'Add anchor to redirect, as it points to a long list.',
              overwrite=True)
    return True


def getPredictedAnchor(title: str) -> str:
    """Return predicted anchor for given title, usually first letter."""
    title = title.lower()
    if title.startswith('npj '):
        return 'npj series'
    title = re.sub(r'^(the|a|an|der|die|das|den|dem|le|la|les|el|il)\s+', '',
                   title)
    return title[0].upper()


if __name__ == "__main__":
    main()
