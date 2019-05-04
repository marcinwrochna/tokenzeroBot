"""Wikipedia bot for handling journal abbrevs: redirects and infoboxes.

The bot scrapes {{infobox journal}}s, computes ISO 4 abbreviations of titles,
creates and fixes redirects and the `abbreviation` parameter.
"""
import logging
import re
import sys
from collections import defaultdict
from typing import Any, DefaultDict, Dict, Tuple
from enum import Flag, auto

import Levenshtein
import pywikibot
import pywikibot.data.api
from pywikibot import Site

from abbrevIsoBot import reports, state, fill, abbrevUtils, databases
from utils import initLimits, trySaving, \
    getRedirectsToPage, getPagesWithTemplate, getInfoboxJournals


STATE_FILE_NAME = 'abbrevIsoBot/abbrevBotState.json'


def main() -> None:
    """Execute the bot."""
    logging.basicConfig(level=logging.WARNING)
    state.loadOrInitState(STATE_FILE_NAME)
    # Initialize pywikibot.
    assert Site().code == 'en'
    initLimits(
        editsLimits={'default': 200},
        brfaNumber=2,
        onlySimulateEdits=True,
        botTrial=False,
        listLimit=None
    )
    # Run the given command or print a help message.
    if len(sys.argv) != 2:
        printHelp()
    elif sys.argv[1] == 'test':
        doTest()
    elif sys.argv[1] == 'scrape':
        doScrape()
    elif sys.argv[1] == 'fixpages':
        doScrape(fixPages=True, writeReport=False)
    elif sys.argv[1] == 'report':
        doScrape(fixPages=True, writeReport=True)
    elif sys.argv[1] == 'fill':
        fill.doFillAbbrevs()
    else:
        printHelp()
    state.saveState(STATE_FILE_NAME)


def printHelp() -> None:
    """Print a simple help message on available commands."""
    print("Use exactly one command of: scrape, fixpages, report, test, fill")


def doTest() -> None:
    """Test a bot edit (in userspace sandbox), e.g. to check flags."""
    # print(state.dump())
    databases.parseNLMDict('databaseNLM.txt')
    databases.parseMSNDict('databaseMathSciNet.csv')
    return
    page = pywikibot.Page(Site(), 'User:TokenzeroBot/sandbox')
    page.text = 'Testing bot.'
    page.save(
        'Testing bot',
        minor=False,
        botflag=True,
        watch="nochange",
        nocreate=True)


def doScrape(fixPages: bool = False, writeReport: bool = False) -> None:
    """Scrape all infobox journals, update `state` and fix redirects.

    Args:
        fixPages: Whether to actually fix any pages, or only scrape.
        writePages: Whether to write the reports.
    """
    articles = getPagesWithTemplate('Infobox journal', content=True)
    # articles = [pywikibot.Page(Site(), 'Annals of Mathematics')]
    # Yields ~7500 pages.
    # In case you'd want 'Category:Academic journals', you'd probably exclude
    # the subcategory 'Literary magazines' (in 'Humanities journals')
    # which includes all kinds of comic book magazines, for example.
    for i, page in enumerate(articles):
        print(f'--Scraping:\t{i}\t{page.title()}\t', end='', flush=True)
        scrapePage(page)
        if fixPages:
            fixPageRedirects(page)
    if writeReport:
        reports.doReport(Site(), printOnly=False)


def scrapePage(page: pywikibot.Page) -> None:
    """Scrape a page's infoboxes and redirects, save them in the `state`."""
    pageData: Any = {'infoboxes': [], 'redirects': {}}
    # Iterate over {{infobox journal}}s on `page`.
    for infobox in getInfoboxJournals(page):
        print('I', end='', flush=True)
        pageData['infoboxes'].append(infobox)
        if 'title' in infobox and infobox['title'] != '':
            state.saveTitleToAbbrev(infobox['title'])
    # Iterate over pages that are redirects to `page`.
    for r in getRedirectsToPage(page.title(), namespaces=0,
                                total=100, content=True):
        print('R', end='', flush=True)
        pageData['redirects'][r.title()] = r.text
        # r.getRedirectTarget().title()
    state.savePageData(page.title(), pageData)
    state.saveTitleToAbbrev(abbrevUtils.stripTitle(page.title()))
    print('', flush=True)


def fixPageRedirects(page: pywikibot.Page) -> int:
    """Fix redirects to given page."""
    title = page.title()
    pageData = state.getPageData(title)
    (requiredRedirects, skip) = getRequiredRedirects(page)
    nEditedPages = 0
    for rTitle, rCats in requiredRedirects.items():
        rNewContent = rcatSetToRedirectContent(title, rCats)
        # Attempt to create new redirect.
        if rTitle not in pageData['redirects']:
            if pywikibot.Page(Site(), rTitle).exists():
                print(f'--Skipping existing page [[{rTitle}]] '
                      f'(not a redirect to [[{title}]]).')
                reports.reportExistingOtherPage(title, rTitle)
            else:
                print(f'--Creating redirect '
                      f'from [[{rTitle}]] to [[{title}]]. '
                      f'Created content:\n{rNewContent}\n-----',
                      flush=True)
                nEditedPages += 1
                rPage = pywikibot.Page(Site(), rTitle)
                trySaving(rPage, rNewContent,
                          'Creating redirect from standard abbreviation. ',
                          overwrite=False)
        else:
            rOldContent = pageData['redirects'][rTitle]
            if isValidISO4Redirect(rOldContent, title, rCats):
                print(f'--Skipping existing valid redirect '
                      f'from [[{rTitle}]] to [[{title}]].')
            elif isReplaceableRedirect(rOldContent, title, rCats):
                print(f'--Replacing existing redirect '
                      f'from [[{rTitle}]] to [[{title}]].\n'
                      f'RCatSet: {rCats}\n'
                      f'Original content:\n{rOldContent}\n----- '
                      f'New content:\n{rNewContent}\n-----',
                      flush=True)
                nEditedPages += 1
                rPage = pywikibot.Page(Site(), rTitle)
                trySaving(rPage, rNewContent,
                          'Marking standard abbrev rcat. ',
                          overwrite=True)
            else:
                print(f'--Skipping existing dubious redirect '
                      f'from [[{rTitle}]] to [[{title}]].\n'
                      f'RCatSet: {rCats}\n'
                      f'Original content:\n{rOldContent}\n----- ')
                reports.reportExistingOtherRedirect(title, rTitle, rOldContent)
    # Purge page cache to remove warnings about missing redirects.
    if nEditedPages > 0:
        page.purge()

    # Report redirects that we wouldn't add, but exist and are marked as ISO-4.
    if requiredRedirects and not skip:
        expectedAbbrevs = \
            [r.replace('.', '') for r in requiredRedirects]
        potentialAbbrevs = []
        for rTitle, rContent in pageData['redirects'].items():
            if 'from former name' in rContent or '.' not in rTitle:
                cAbbrevEng = state.tryGetAbbrev(
                    abbrevUtils.stripTitle(rTitle), 'eng') or ''
                cAbbrevAll = state.tryGetAbbrev(
                    abbrevUtils.stripTitle(rTitle), 'all') or ''
                cAbbrevEng = cAbbrevEng.replace('.', '')
                cAbbrevAll = cAbbrevAll.replace('.', '')
                if 'from former name' in rContent:
                    if cAbbrevEng != rTitle.replace('.', ''):
                        expectedAbbrevs.append(cAbbrevEng)
                    if cAbbrevAll != rTitle.replace('.', ''):
                        expectedAbbrevs.append(cAbbrevAll)
                elif '.' not in rTitle:
                    if cAbbrevEng != rTitle.replace('.', ''):
                        potentialAbbrevs.append((cAbbrevEng, rTitle))
                    if cAbbrevAll != rTitle.replace('.', ''):
                        potentialAbbrevs.append((cAbbrevAll, rTitle))
        expectedAbbrevs = [a for a in expectedAbbrevs if a]
        potentialAbbrevs = [(a, t) for (a, t) in potentialAbbrevs if a]
        for rTitle, rContent in pageData['redirects'].items():
            if not re.search(r'R from ISO 4', rContent):
                continue
            # Ignore rTitle that contain a computed abbreviation as a
            # substring, assume that it's some valid variation on a subtitle.
            isExpected = False
            rTitleDotless = rTitle.replace('.', '')
            for computedAbbrev in expectedAbbrevs:
                if re.sub(r'\s*[:(].*', '', computedAbbrev) in rTitleDotless:
                    isExpected = True
                    break
            if not isExpected:
                # Find other titles in existing redirects
                # that would ISO-4 abbreviate to it
                potentials = [t for (a, t) in potentialAbbrevs
                              if abbrevUtils.isSoftMatch(rTitleDotless, a)]
                potentials = list(sorted(set(potentials)))
                # Find closest computed abbrev.
                bestAbbrev = ''
                bestDist = len(rTitle)
                for computedAbbrev in sorted(requiredRedirects):
                    dist = Levenshtein.distance(rTitle, computedAbbrev)
                    if dist < bestDist:
                        bestDist = dist
                        bestAbbrev = computedAbbrev
                # Skip if closest abbrev. is far (assume it's from a former
                # title, since there's a ton of cases like that).
                if bestDist <= 8:
                    reports.reportSuperfluousRedirect(
                        title, rTitle, rContent, bestAbbrev, potentials)
    return nEditedPages


class RCatSet(Flag):
    """Flag bitmap denoting a set of rcats (redirect-categories)."""

    #                   infobox-journal parameter, rcat templates {{R from _}}
    ISO4 = auto()     # abbreviation, ISO 4/ISO4/ISO 4 abbreviation
    NLM = auto()      # nlm, NLM/NLM abbreviation/MEDLINE/MEDLINE abbreviation
    MSN = auto()      # mathscinet, MathSciNet/MathSciNet abbreviation


def getRequiredRedirects(page: pywikibot.Page) \
        -> Tuple[Dict[str, RCatSet], bool]:
    """Compute ISO-4 redirects to `page` that we believe should exist.

    Returns `(req, skip)`, where:
        `req[redirectTitle] = redirectCategories`,
        `skip` indicates that we had to skip an infobox, so the result is most
        probably not exhaustive (so we won't report extra existing redirects).
    """
    title = page.title()
    pageData = state.getPageData(title)
    result: DefaultDict[str, RCatSet] = defaultdict(lambda: RCatSet(0))
    skip = False
    for infobox in pageData['infoboxes']:
        name = infobox.get('title', abbrevUtils.stripTitle(title))
        iAbbrev = infobox.get('abbreviation', '')
        iAbbrevDotless = iAbbrev.replace('.', '')
        if iAbbrev == '' or iAbbrev == 'no':
            print(f'--Abbrev param empty or "no", ignoring [[{title}]].')
            skip = True
            continue
        if ':' in iAbbrev[:5]:
            print(f'--Abbrev contains early colon, ignoring [[{title}]].')
            reports.reportTitleWithColon(
                title, infobox.get('title', ''), iAbbrev)
            skip = True
            continue
        # If a valid ISO 4 redirect already exists for dotted version,
        # there should be one for the dotless version too.
        hasISO4Redirect = False
        if iAbbrev in pageData['redirects'] \
                and isValidISO4Redirect(pageData['redirects'][iAbbrev], title,
                                        RCatSet.ISO4, strict=False)\
                and iAbbrevDotless != iAbbrev:
            # TODO return? result[iAbbrev] |= RCatSet('ISO4')
            #              result[iAbbrevDotless] |= RCatSet('ISO4')
            hasISO4Redirect = True
        # If the abbreviation matches the computed one,
        # there should be a dotted and a dotless redirect.
        cLang = abbrevUtils.getLanguage(infobox)
        cAbbrev = state.tryGetAbbrev(name, cLang)
        if cAbbrev is None:
            skip = True
            continue
        if not abbrevUtils.isSoftMatch(iAbbrev, cAbbrev):
            print(f'--Abbreviations don\'t match, ignoring [[{title}]].')
            otherAbbrevs = list(state.getAllAbbrevs(name).values())
            otherAbbrevs = [a for a in otherAbbrevs
                            if abbrevUtils.isSoftMatch(iAbbrev, a)]
            if otherAbbrevs:
                reports.reportLanguageMismatch(
                    title, infobox.get('title', ''),
                    iAbbrev, cAbbrev, otherAbbrevs[0],
                    infobox.get('language', ''), infobox.get('country', ''),
                    cLang, state.getMatchingPatterns(name), hasISO4Redirect)
            else:
                reports.reportProperMismatch(
                    title, infobox.get('title', ''),
                    iAbbrev, cAbbrev, cLang,
                    state.getMatchingPatterns(name), hasISO4Redirect)
            continue
        if iAbbrevDotless == iAbbrev:
            print(f'--Abbreviation is trivial (has no dots), '
                  f'to avoid confusion we\'re ignoring [[{title}]].')
            skip = True
            reports.reportTrivialAbbrev(
                title, infobox.get('title', ''),
                iAbbrev, pageData['redirects'])
        else:
            result[iAbbrev] |= RCatSet.ISO4
            result[iAbbrevDotless] |= RCatSet.ISO4
    for infobox in pageData['infoboxes']:
        nlm = infobox.get('nlm', '')
        if nlm and re.fullmatch(r'[\w\ \.,\(\)\[\]\:\'/\-]+', nlm):
            result[nlm] |= RCatSet.NLM
        msn = infobox.get('mathscinet', '')
        if msn and re.fullmatch(r'[\w\ \.\(\)\:\'/\-]+', msn):
            result[msn] |= RCatSet.MSN
            result[msn.replace('.', '')] |= RCatSet.MSN
    finalResult: Dict[str, RCatSet] = {}
    for rTitle, rCats in result.items():
        if rCats:
            finalResult[rTitle] = rCats
    return finalResult, skip


def rcatSetToRedirectContent(target: str, rCats: RCatSet) -> str:
    """Construct a redirect's contents (target and rcats)."""
    result = '#REDIRECT [[' + target + ']]'
    r = []
    if rCats & RCatSet.ISO4:
        r.append('{{R from ISO 4}}')
    if rCats & RCatSet.NLM:
        r.append('{{R from NLM}}')
    if rCats & RCatSet.MSN:
        r.append('{{R from MathSciNet}}')
    if len(r) == 1:
        result += '\n' + r[0]
    elif r:
        result += '\n\n{{Redirect shell |\n  ' + ('\n  '.join(r)) + '\n}}'
    return result


def isValidISO4Redirect(rContent: str, title: str,
                        rCats: RCatSet, strict: bool = True) -> bool:
    """Check if given redirect is a simple variation of what we would put.

    Args:
        rContent: Wikitext content of the redirect.
        title: Title of the target page.
        rCats: set of categories we should have.
        strict: if true, we reject if some other categories are here
    """
    # Ignore special characters variants.
    rContent = rContent.replace('&#38;', '&')
    rContent = rContent.replace('&#39;', '\'')
    rContent = rContent.replace('_', ' ')
    # Ignore double whitespace.
    rContent = re.sub(r'<br\s*/>', '\n', rContent)
    rContent = re.sub(r'((?<!\w)\s|\s(?![\s\w]))', '', rContent.strip())
    title = re.sub(r'((?<!\w)\s|\s(?![\s\w]))', '', title.strip())
    rContent = re.sub(r'#REDIRECT\s+\[\[', '#REDIRECT[[', rContent)
    # Ignore capitalization.
    rContent = rContent.replace('redirect', 'REDIRECT')
    rContent = rContent.replace('Redirect', 'REDIRECT')
    # Check rcats, ignore the ones we expect.
    existingRCats = RCatSet(0)
    rContent = re.sub(r'{{R(EDIRECT)? (un)?printworthy}}', '', rContent)
    rContent = re.sub(r'{{R(EDIRECT)? u?pw?}}', '', rContent)
    rContent = re.sub(r'{{R from move}}', '', rContent)
    rContent = re.sub(r'{{R to section}}', '', rContent)
    if re.search(r'{{R from (MEDLINE|NLM)( abbreviation)?}}', rContent):
        existingRCats |= RCatSet.NLM
    if re.search(r'{{R from MathSciNet( abbreviation)?}}', rContent):
        existingRCats |= RCatSet.MSN
    if re.search(r'{{R from ISO\s?4( abbreviation)?}}', rContent):
        existingRCats |= RCatSet.ISO4
    rContent = re.sub(
        r'{{R from (ISO4|ISO 4|Bluebook|bluebook|MEDLINE|NLM|MathSciNet)'
        r'( abbreviation)?}}',
        '',
        rContent)
    # Ignore redirects to specific sections.
    rContent = re.sub(r'#[^\[\]]*(?=\]\])', '', rContent)
    # Ignore variants which include the rcat shell.
    rContent = re.sub(r'{{REDIRECT (category )?shell\s*\|(1=)?\s*}}',
                      '', rContent)
    if rContent != '#REDIRECT[[' + title + ']]':
        return False
    if strict:
        if existingRCats != rCats:
            return False
    else:
        # If some bits set in rCats are not in existingRCats, fail:
        if rCats & ~existingRCats:  # pylint: disable=E1130 # (a pylint bug)
            return False
    return True


def isReplaceableRedirect(rContent: str, title: str, rCats: RCatSet) -> bool:
    """Check if the content of a given redirect can be automatically replaced.

    Examples of not replaceable content:
        redirects to specific article sections, to disambuigs,
        unexpected rcats or rcats with some parameters filled,
        rcat "from move".
    """
    # Normalize special characters.
    rContent = rContent.replace('&#38;', '&')
    rContent = rContent.replace('&#39;', '\'')
    rContent = rContent.replace('_', ' ')
    # Ignore double whitespace.
    rContent = re.sub(r'<br\s*/>', '\n', rContent)
    rContent = re.sub(r'((?<!\w)\s|\s(?![\s\w]))', '', rContent.strip())
    title = re.sub(r'((?<!\w)\s|\s(?![\s\w]))', '', title.strip())
    rContent = re.sub(r'#REDIRECT\s+\[\[', '#REDIRECT[[', rContent)
    # Normalize capitalization.
    rContent = rContent.replace('redirect', 'REDIRECT')
    rContent = rContent.replace('Redirect', 'REDIRECT')
    # Allow removing `(un)printworthy` rcats.
    rContent = re.sub(r'{{R(EDIRECT)? (un)?printworthy}}', '', rContent)
    rContent = re.sub(r'{{R(EDIRECT)? u?pw?}}', '', rContent)
    # Allow removing at most one other abbreviation or spelling rcat.
    # E.g. don't change pages having an {{R from move}}.
    #    rContent = re.sub(r'{{R from[a-zA-Z4\s]*}}', '', rContent, 1)
    rContent = re.sub(r'{{R from (ISO 4|abb[a-z]*|shortening|initialism'
                      r'|short name|alternat[a-z]* spelling'
                      r'|systematic abbreviation|other capitalisation'
                      r'|other spelling)}}',
                      '',
                      rContent,
                      1)
    # Allow removing a common bug (an rcat without '{{}}').
    rContent = re.sub(r'R from abbreviation', '', rContent, 1)
    # Allow removing/adding the rcat shell.
    rContent = re.sub(r'{{REDIRECT shell\s*[|](1=)?\s*}}', '', rContent)
    rContent = re.sub(r'{{REDIRECT category shell\s*[|](1=)?\s*}}', '',
                      rContent)
    return rContent == '#REDIRECT[[' + title + ']]'


if __name__ == '__main__':
    main()
