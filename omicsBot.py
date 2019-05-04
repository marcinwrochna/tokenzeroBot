#!/usr/bin/env python3
"""A bot for handling predatory journal titles: adding redirects and hatnotes.

It expects an input file starting with a few configuration lines, then
a single line '---' and then titles, one per line (as in omicsLists/).
For example:
    target = Title of page to which created redirects will redirect to
    category = Category in which to place the redirects (without 'Category:')
    publisher = Title of page of the predatory publisher to mention in hatnotes
    ---
    Journal of Foos
    Journal of Bar: International Research
    ...
"""
import logging
import re
import sys
from typing import List, Optional, Tuple

import pywikibot
import pywikibot.data.api
from pywikibot import Site

from utils import initLimits, trySaving
from abbrevIsoBot import state

# We share the state (with computed ISO-4 abbrevs) with abbrevIsoBot.
STATE_FILE_NAME = 'abbrevIsoBot/abbrevBotState.json'


def main() -> None:
    """Execute the bot."""
    logging.basicConfig(level=logging.WARNING)
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} filename.txt')
        return
    filename = sys.argv[1]

    # Initialize pywikibot.
    assert Site().code == 'en'
    initLimits(
        editsLimits={'create': 300, 'talk': 300, 'fix': 300, 'hatnote': 0},
        brfaNumber=6,
        onlySimulateEdits=True,
        botTrial=False
    )

    state.loadOrInitState(STATE_FILE_NAME)

    configEnd: Optional[int] = None
    configLines: List[str] = []
    numLines = sum(1 for line in open(filename) if line.rstrip())
    with open(filename) as f:
        for i, title in enumerate(f):
            title = title.strip()
            if not title:
                continue

            if configEnd is None:
                print(f'Config line {i}/{numLines} \t [{filename}]')
                if title == '---':
                    configEnd = i
                    rTarget, rCat, publisher = parseConfigLines(configLines)
                else:
                    configLines.append(title)
            else:
                print(f'Title line {i - configEnd}/{numLines - configEnd} \t '
                      f'[{filename}]')
                doOmicsRedirects(title, rTarget, rCat)
                assert publisher
                doOmicsHatnotes(title, publisher)
            sys.stdout.flush()
    state.saveState(STATE_FILE_NAME)


def parseConfigLines(lines: List[str]) -> Tuple[str, str, Optional[str]]:
    """Parse the config part of the input file and check sanity."""
    rTarget: Optional[str] = None
    rCat: Optional[str] = None
    publisher = None
    for line in lines:
        key, value = line.split('=', 2)
        key = key.strip()
        value = value.strip()
        if key == 'target':
            rTarget = value
        elif key == 'category':
            rCat = value
        elif key == 'publisher':
            publisher = value
        else:
            raise Exception(f'Unrecognized configuration key "{key}".')
    if not rTarget:
        raise Exception(f'No target configured!')
    if not rCat:
        raise Exception(f'No category configured!')
    targetPage = pywikibot.Page(Site(), rTarget)
    if (not targetPage.exists()
            or targetPage.isRedirectPage()
            or targetPage.isCategoryRedirect()
            or targetPage.isDisambig()):
        raise Exception(f'Target [[{rTarget}]] does not exists '
                        f'or is a redirect.')
    catPage = pywikibot.Page(Site(), 'Category:' + rCat)
    if (not catPage.exists()
            or not catPage.is_categorypage()
            or catPage.isCategoryRedirect()):
        raise Exception(f'[[Category:{rCat}]] does not exist '
                        f'or is not category or is redirect.')
    if publisher:
        pubPage = pywikibot.Page(Site(), publisher)
        if not pubPage.exists():
            raise Exception(f'Publisher page [[{publisher}]] does not exist.')
    print(f'Redirect target = [[{rTarget}]]')
    print(f'Redirect cat = [[Category:{rCat}]]')
    print(f'Redirect publisher = [[{publisher}]]')
    return rTarget, rCat, publisher


def doOmicsRedirects(title: str, rTarget: str, rCat: str) -> None:
    """Create redirects for given OMICS journal."""
    # If [[title]] exists, add '(journal)', unless its a redirect
    # (either one we did, maybe to be fixed, or an unexpected one we'll skip).
    addJournal = False
    if '(journal)' in title:
        title = title.replace('(journal)', '').strip()
        addJournal = True
    if '(' in title:
        print(f'Skip: [[{title}]] has unexpected disambuig.')
    page = pywikibot.Page(Site(), title)
    if page.exists() and not page.isRedirectPage():
        addJournal = True
        if 'journal' in title.lower():
            print(f'Skip: [[{title}]] already exists, '
                  'title already has "journal".')
            return
        for cat in page.categories():
            if 'journal' in cat.title().lower():
                print(f'Skip: [[{title}]] already exists, '
                      'has category containing "journal".')
                return

    # List of redirect pages to create, together with their type.
    rTitles = set([(title, 'plain')])

    # Handle 'and' vs '&' variant.
    if ' and ' in title:
        rTitles.add((title.replace(' and ', ' & '), 'and'))
    elif ' & ' in title and 'Acta' not in title:
        rTitles.add((title.replace(' & ', ' and '), 'and'))

    # Handle variant without 'The' at the beginning.
    if title.startswith('The '):
        rTitle = title.replace('The ', '')
        rTitles.add((rTitle, 'the'))
        if ' and ' in rTitle:
            rTitles.add((rTitle.replace(' and ', ' & '), 'theand'))
        elif ' & ' in rTitle and 'Acta' not in rTitle:
            rTitles.add((rTitle.replace(' & ', ' and '), 'theand'))

    # Handle ISO-4 abbreviated variants.
    state.saveTitleToAbbrev(title)
    try:
        cLang = 'all' if ('acta' in title.lower()) else 'eng'
        cAbbrev = state.getAbbrev(title, cLang)
    except state.NotComputedYetError as err:
        print(err.message)
        return
    if cAbbrev != title:
        rTitles.add((cAbbrev, 'iso4'))
        rTitles.add((cAbbrev.replace('.', ''), 'iso4'))

    # Skip if any of the redirect variants exists and is unfixable.
    for (rTitle, rType) in rTitles:
        if addJournal and rType != 'iso4':
            rTitle = rTitle + ' (journal)'

        r = createOmicsRedirect(rTitle, rType, rTarget, rCat, tryOnly=True)
        if r == 'unfixable':
            print(f'Skip: [[{title}]] unfixable.')
            return

    # Create the redirects.
    for (rTitle, rType) in rTitles:
        if addJournal and rType != 'iso4':
            rTitle = rTitle + ' (journal)'
        createOmicsRedirect(rTitle, rType, rTarget, rCat, tryOnly=False)


def doOmicsHatnotes(title: str, publisher: str) -> None:
    """Create hatnotes for given OMICS journal."""
    # Create hatnotes for misleading (predatory) titles.
    suffixes = [': Open Access',
                '-Open Access',
                ': An Indian Journal',
                ': Current Research',
                ': Advances and Applications',
                ': Development and Therapy',
                ': Evidence and Research',
                ': Research and Reviews',
                ': Research and Reports',
                ': Targets and Therapy']
    aTitle = ''
    for s in suffixes:
        if title.endswith(s):
            aTitle = title[:-len(s)].strip()
    if aTitle:
        aPage = pywikibot.Page(Site(), aTitle)
        if aPage.exists():
            isJournal = False
            for cat in aPage.categories():
                if 'journal' in cat.title().lower():
                    isJournal = True
                    break
            if isJournal:
                if not aPage.isRedirectPage():
                    addOmicsHatnote(aTitle, title, publisher)
            else:
                aTitle = aTitle + ' (journal)'
                aPage = pywikibot.Page(Site(), aTitle)
                if aPage.exists() and not aPage.isRedirectPage():
                    addOmicsHatnote(aTitle, title, publisher)


def addOmicsHatnote(aTitle: str, title: str, publisher: str) -> None:
    """Add hatnote to [[aTitle]] about confusion risk with OMICS [[title]]."""
    page = pywikibot.Page(Site(), aTitle)
    if '{{Confused|' in page.text or '{{confused|' in page.text:
        print(f'Skip: {{{{confused}}}} hatnote already on [[{aTitle}]]')
        return
    print(f'Adding hatnote to [[{aTitle}]]')
    hatnote = (f'{{{{Confused|text=[[{title}]],'
               f' published by the [[{publisher}]]}}}}\n')
    trySaving(page, hatnote + page.text, overwrite=True, limitType='hatnote',
              summary='Add hatnote to predatory journal clone.')


def createOmicsRedirect(title: str, rType: str,
                        target: str, category: str, tryOnly: bool) -> str:
    """Attempt to create or fix redirect from [[title]] to [[target]].

    We return 'create' if non-existing, 'done' if basically equal to what we
    would add, 'fix' if exists but looks fixable, 'unfixable' otherwise.
    Also create talk page with {{WPJournals}} when non-existing.
    """
    rText = '#REDIRECT[[' + target + ']]\n'
    rCat = '[[Category:' + category + ']]\n' if category else ''
    rIsoCat = '{{R from ISO 4}}\n'
    rSortTitle = title
    if rSortTitle.startswith('The ') and '(' not in title:
        rSortTitle = rSortTitle.replace('The ', '') + ', The'
    if ' & ' in rSortTitle:
        rSortTitle = rSortTitle.replace(' & ', ' and ')
    if rSortTitle != title:
        rSort = '{{DEFAULTSORT:' + rSortTitle + '}}\n'

    rNewContent = rText
    if rSortTitle != title:
        rNewContent += rSort
    if rType == 'plain':
        rNewContent += rCat
    if rType == 'iso4':
        rNewContent += '{{R from ISO 4}}\n'

    rPage = pywikibot.Page(Site(), title)
    rTalkPage = rPage.toggleTalkPage()
    if not rPage.exists():
        if not tryOnly:
            print(f'Creating redirect from: [[{title}]].')
            trySaving(rPage, rNewContent,
                      'Create redirect from predatory publisher\'s journal.',
                      overwrite=False, limitType='create')
            if rType == 'plain' and not rTalkPage.exists():
                content = '{{WPJournals|class=redirect}}'
                trySaving(rTalkPage, content,
                          'Mark new redirect into {{WPJournals}}.',
                          overwrite=False, limitType='talk')
        return 'create'
    # If rPage exists, check if we would add basically the same.
    text = rPage.text
    textStripped = re.sub(r'\s', '', text, re.M).strip()
    rNewStripped = re.sub(r'\s', '', rNewContent, re.M).strip()
    if textStripped == rNewStripped:
        if not tryOnly:
            if rTalkPage.exists():
                print(f'Done: [[{title}]].')
            elif rType == 'plain':
                print(f'Done, but creating talk page: [[{title}]].')
                content = '{{WPJournals|class=redirect}}'
                trySaving(rTalkPage, content,
                          'Mark redirect into {{WPJournals}}.',
                          overwrite=False, limitType='talk')
        return 'done'
    # If rPage exists but not the same, check if it is a fixable case.
    if rCat:
        text = text.replace(rCat.strip(), '')
    text = text.replace(rIsoCat.strip(), '')
    text = re.sub(r'\{\{DEFAULTSORT:[^\}]*\}\}', '', text)
    textStripped = re.sub(r'\s', '', text, re.M).strip()
    rTextStripped = re.sub(r'\s', '', rText, re.M).strip()
    if textStripped != rTextStripped:
        print(f'Not fixable: [[{title}]]  (type={rType}).')
        print('---IS-------------')
        print(rPage.text)
        print('---SHOULD BE------')
        print(rNewContent)
        print('==================')
        return 'unfixable'
    # If it is fixable, fix it.
    if not tryOnly:
        print(f'Fixing redirect from: [[{title}]] (type={rType}).')
        print('---WAS------------')
        print(rPage.text)
        print('---WILL BE--------')
        print(rNewContent)
        print('==================')
        trySaving(rPage, rNewContent,
                  'Fix redirect from predatory publisher\'s journal.',
                  overwrite=True, limitType='fix')
        if rType == 'plain' and not rTalkPage.exists():
            content = '{{WPJournals|class=redirect}}'
            trySaving(rTalkPage, content,
                      'Fix redirect from predatory publisher\'s journal.',
                      overwrite=False, limitType='talk')
    return 'fix'


if __name__ == "__main__":
    main()
