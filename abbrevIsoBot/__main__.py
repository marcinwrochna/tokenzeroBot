"""Wikipedia bot for handling journal abbrevs: redirects and infoboxes.

The bot scrapes {{infobox journal}}s, computes ISO 4 abbreviations of titles,
creates and fixes redirects and the `abbreviation` parameter.
"""
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, DefaultDict, Dict, Optional, Tuple
from enum import auto, Flag
from unidecode import unidecode

import Levenshtein
import pywikibot
import pywikibot.data.api
from pywikibot import Site

from abbrevIsoBot import reports, state, fill, abbrevUtils, databases
from utils import initLimits, printLimits, trySaving, tryPurging, \
    getRedirectsToPage, getPagesWithTemplate, getInfoboxJournals


STATE_FILE_NAME = 'abbrevIsoBot/abbrevBotState.json'
# Dicts from issn to abbrev in NLM/PubMed or MathSciNet database.
issnToAbbrev: Dict[str, Dict[str, str]] = {'nlm': {}, 'mathscinet': {}}

# Patchset to propose for Stitchpitch
patchset: Dict[str, Any] = {
    'patchtype': 'list',
    'slug': 'ISO-4 language interpretation fix',
    'patches': []
}


def main() -> None:
    """Execute the bot."""
    logging.basicConfig(level=logging.WARNING)
    state.loadOrInitState(STATE_FILE_NAME)
    # Initialize pywikibot.
    assert Site().code == 'en'
    initLimits(
        editsLimits={'default': 100},
        brfaNumber=2,
        onlySimulateEdits=False,
        botTrial=False,
        listLimit=None
    )
    printLimits()
    # Run the given command or print a help message.
    if len(sys.argv) < 2:
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
    elif sys.argv[1] == 'patchlist':
        doPatchlist(sys.argv[2])
    else:
        printHelp()
    state.saveState(STATE_FILE_NAME)


def printHelp() -> None:
    """Print a simple help message on available commands."""
    print("Use exactly one command of: scrape, fixpages, report, test, fill")


def doTest() -> None:
    """Test a bot edit (in userspace sandbox), e.g. to check flags."""
    # print(state.dump())
    print(state.getAbbrev('Nature Reviews Clinical Oncology', 'eng'))
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
    issnToAbbrev['nlm'] = databases.parseNLMDict()
    issnToAbbrev['mathscinet'] = databases.parseMSNDict()
    print(f'Loaded databases nlm={len(issnToAbbrev["nlm"])}'
          f' msn={len(issnToAbbrev["mathscinet"])}')
    articles = getPagesWithTemplate('Infobox journal', content=True)
    # articles = [pywikibot.Page(Site(), 'Asiatic Society of Japan')]
    # articles = [pywikibot.Page(Site(), 'Annals of Mathematics')]
    # Yields ~8000 pages.
    # In case you'd want 'Category:Academic journals', you'd probably exclude
    # the subcategory 'Literary magazines' (in 'Humanities journals')
    # which includes all kinds of comic book magazines, for example.
    if True:
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
        checkDBAbbrevs(page.title(), infobox)
    # Iterate over pages that are redirects to `page`.
    for r in getRedirectsToPage(page.title(), namespaces=0,
                                total=100, content=True):
        print('R', end='', flush=True)
        pageData['redirects'][r.title()] = r.text
        # r.getRedirectTarget().title()
    state.savePageData(page.title(), pageData)
    state.saveTitleToAbbrev(abbrevUtils.stripTitle(page.title()))
    print('', flush=True)


def checkDBAbbrevs(pageTitle: str, infobox: Dict[str, str]) -> bool:
    """Check abbreviation from NLM/PubMed and MathSciNet databases."""
    issns = []
    if infobox.get('issn'):
        issns.append(infobox['issn'])
    if infobox.get('eissn'):
        issns.append(infobox['eissn'])
    iTitle = abbrevUtils.sanitizeField(infobox.get('title', ''))
    iAbbrev = abbrevUtils.sanitizeField(infobox.get('abbreviation', ''))
    for t in ['nlm', 'mathscinet']:
        for issn in issns:
            issn = issn.replace('–', '-')
            if issn in issnToAbbrev[t]:
                shouldHave = issnToAbbrev[t][issn]
                if infobox.get(t):
                    if infobox[t] != shouldHave:
                        reports.reportBadDBAbbrev(
                            pageTitle, iTitle,
                            iAbbrev,
                            infobox[t], shouldHave, issn, t)
                    return False
                else:
                    regexToCut = r'[^A-Za-z]'  # r'[ .:()\-]'
                    iAbbrevCut = re.sub(regexToCut, '', unidecode(iAbbrev))
                    shouldCut = re.sub(regexToCut, '', unidecode(shouldHave))
                    if iAbbrevCut != shouldCut:
                        reports.reportBadDBAbbrev(
                            pageTitle, iTitle,
                            iAbbrev,
                            '', shouldHave, issn, t)
                        return False
    return True


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
            try:
                exists = pywikibot.Page(Site(), rTitle).exists()
            except pywikibot.exceptions.InvalidTitle:
                exists = False
            if exists:
                print(f'--Skipping existing page [[{rTitle}]] '
                      f'(not a redirect to [[{title}]]).')
                if title == rTitle:
                    continue
                if title not in pywikibot.Page(Site(), rTitle).text:
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
            elif isReplaceableRedirect(rOldContent, title,
                                       rCats | RCatSet.ISO4):
                # Don't log nor edit redirects that would be replaceable
                # except they have ISO4 and we're not sure it should have.
                if not (rCats & RCatSet.ISO4):
                    continue
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
            elif not skip:
                print(f'--Skipping existing dubious redirect '
                      f'from [[{rTitle}]] to [[{title}]].\n'
                      f'RCatSet: {rCats}\n'
                      f'Original content:\n{rOldContent}\n----- ')
                reports.reportExistingOtherRedirect(title, rTitle, rOldContent)
    # Purge page cache to remove warnings about missing redirects.
    if nEditedPages > 0:
        tryPurging(page)

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
    for infoboxId, infobox in enumerate(pageData['infoboxes']):
        altName = abbrevUtils.stripTitle(title)
        iTitle = abbrevUtils.sanitizeField(infobox.get('title', ''))
        name = iTitle or altName
        # On Wikipedia, we used to remove subtitles/dependent titles.
        # It seems not to change that much and it seems not doig that is better.
        # name = re.sub(r'(.{6})[-:–(].*', r'\1', name)
        # altName = re.sub(r'(.{6})[-:–(].*', r'\1', altName)
        iAbbrev = abbrevUtils.sanitizeField(infobox.get('abbreviation', ''))
        iAbbrevDotless = iAbbrev.replace('.', '')
        if iAbbrev == '' or iAbbrev == 'no':
            print(f'--Abbrev param empty or "no", ignoring [[{title}]].')
            skip = True
            continue
        if ':' in iAbbrev[:5]:
            print(f'--Abbrev contains early colon, ignoring [[{title}]].')
            reports.reportTitleWithColon(
                title, iTitle, iAbbrev)
            skip = True
            continue
        hasISO4Redirect = \
            iAbbrev in pageData['redirects'] \
            and isValidISO4Redirect(pageData['redirects'][iAbbrev], title,
                                    RCatSet.ISO4, strict=False)
        # If the abbreviation matches the computed one,
        # there should be a dotted and a dotless redirect.
        cLang = 'all'  # abbrevUtils.getLanguage(infobox)
        cAbbrev = state.tryGetAbbrev(name, cLang)
        cAltAbbrev = state.tryGetAbbrev(altName, cLang)
        if cAbbrev is None or cAltAbbrev is None:
            skip = True
            continue
        if (not abbrevUtils.isSoftMatch(iAbbrev, cAbbrev)
                and not abbrevUtils.isSoftMatch(iAbbrev, cAltAbbrev)):
            print(f'--Abbreviations don\'t match, ignoring [[{title}]].')
            otherAbbrevs = list(state.getAllAbbrevs(name).values())
            otherAbbrevs = [a for a in otherAbbrevs
                            if abbrevUtils.isSoftMatch(iAbbrev, a)]
            if otherAbbrevs:
                reports.reportLanguageMismatch(
                    title, iTitle,
                    iAbbrev, cAbbrev, otherAbbrevs[0],
                    abbrevUtils.sanitizeField(infobox.get('language', '')),
                    abbrevUtils.sanitizeField(infobox.get('country', '')),
                    cLang, state.getMatchingPatterns(name), hasISO4Redirect)
                patch = makeLanguageMismatchPatch(
                    page, infoboxId, infobox.get('abbreviation'), cAbbrev,
                    state.getMatchingPatterns(name)
                )
                if patch is not None:
                    patchset['patches'].append(patch)
                    print(f'ADDED PATCH #{len(patchset["patches"])}!!!')
                    with open('patchset.json', 'wt') as f:
                        json.dump(patchset, f)
            else:
                reports.reportProperMismatch(
                    title, iTitle,
                    iAbbrev, cAbbrev, cLang,
                    state.getMatchingPatterns(name), hasISO4Redirect)
            continue
        if iAbbrevDotless == iAbbrev:
            print(f'--Abbreviation is trivial (has no dots), '
                  f'to avoid confusion we\'re ignoring [[{title}]].')
            skip = True
            reports.reportTrivialAbbrev(
                title, iTitle,
                iAbbrev, pageData['redirects'])
        else:
            result[iAbbrev] |= RCatSet.ISO4
            result[iAbbrevDotless] |= RCatSet.ISO4
    for infobox in pageData['infoboxes']:
        nlm: Optional[str] = abbrevUtils.sanitizeField(infobox.get('nlm', ''))
        if nlm and re.fullmatch(r'[\w\ \.,\(\)\[\]\:\'/\-]+', nlm):
            result[nlm] |= RCatSet.NLM
        if not nlm:
            if infobox.get('issn'):
                nlm = issnToAbbrev['nlm'].get(infobox['issn'])
            if not nlm and infobox.get('eissn'):
                nlm = issnToAbbrev['nlm'].get(infobox['eissn'])
            if nlm and nlm == infobox.get('abbreviation', '').replace('.', ''):
                result[nlm] |= RCatSet.NLM
        msn: Optional[str] = \
            abbrevUtils.sanitizeField(infobox.get('mathscinet', ''))
        if msn and re.fullmatch(r'[\w\ \.\(\)\:\'/\-]+', msn):
            result[msn] |= RCatSet.MSN
            result[msn.replace('.', '')] |= RCatSet.MSN
        if not msn:
            if infobox.get('issn'):
                msn = issnToAbbrev['mathscinet'].get(infobox['issn'])
            if not msn and infobox.get('eissn'):
                msn = issnToAbbrev['mathscinet'].get(infobox['eissn'])
            if msn and msn == iAbbrev:
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
    # Allow rcats we think should be there
    if rCats & RCatSet.ISO4:
        rContent = re.sub(r'{{R from ISO ?4( abbreviation)?}}', '', rContent)
    if rCats & RCatSet.NLM:
        rContent = re.sub(r'{{R from (NLM|MEDLINE)( abbreviation)?}}', '', rContent)
    if rCats & RCatSet.MSN:
        rContent = re.sub(r'{{R from MathSciNet( abbreviation)?}}', '', rContent)
    # Allow removing at most one other abbreviation or spelling rcat.
    # E.g. don't change pages having an {{R from move}}.
    #    rContent = re.sub(r'{{R from[a-zA-Z4\s]*}}', '', rContent, 1)
    rContent = re.sub(r'{{R from (ISO ?4|ISO 4 abbreviation'
                      r'|abb[a-z]*|shortening|initialism'
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


def datetimeFromPWB(t: pywikibot.Timestamp) -> datetime:
    """Convert pywikibot timestamp to UTC datetime."""
    # pywikibot subclasses and overrides t.isoformat() in a way
    # that is incompatible with datetime.fromisoformat.
    d = datetime.fromisoformat(datetime.isoformat(t))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def makeLanguageMismatchPatch(
        page: pywikibot.Page,
        infoboxId: int,
        infoboxAbbrev: str,
        computedAbbrev: str,
        matchingPatterns: str
) -> Optional[Dict[str, Any]]:
    """Make patchset for Stitchpitch: infobox param and redirects rcats."""
    from unicodedata import normalize
    import mwparserfromhell
    startTimeStamp = datetime.now(timezone.utc).isoformat()
    diff = datetimeFromPWB(Site().server_time()) - datetime.now(timezone.utc)
    if diff > timedelta(minutes=2) or -diff > timedelta(minutes=2):
        raise Exception('Local zone misconfigured or server timezone not UTC!')
    latestRevision = page.latest_revision
    mainEdit = {
        'patchtype': 'edit',  # implies 'nocreate': True
        'slug': f'{infoboxAbbrev} → {computedAbbrev}',
        'details': matchingPatterns,
        'title': page.title(),
        'summary': 'Fix ISO-4 abbreviation to use all language rules.',
        'minor': True,
        'basetimestamp': datetimeFromPWB(latestRevision.timestamp).isoformat(),
        'starttimestamp': startTimeStamp,
        'oldtext': latestRevision.text,
        'oldrevid': latestRevision.revid
    }
    if datetime.fromisoformat(mainEdit['basetimestamp']) > \
       datetime.fromisoformat(startTimeStamp) - timedelta(hours=5):
        print(f'Skipping patch for "{page.title()}":'
              f' edited a short while ago ago.')
        return None
    code = mwparserfromhell.parse(normalize('NFC', latestRevision.text))
    foundInfobox = None  # type: Optional[mwparserfromhell.Template]
    foundId = -1
    for t in code.filter_templates():
        if t.name.matches('infobox journal') or \
           t.name.matches('Infobox Journal'):
            foundId += 1
            if foundId == infoboxId:
                foundInfobox = t
                break
    if not foundInfobox:
        print(f'Skipping patch for "{page.title()}":'
              f' infobox #{infoboxId} not found.')
        return None
    foundAbbrev = str(foundInfobox.get('abbreviation').value)
    if foundAbbrev.strip() != infoboxAbbrev:
        print(f'Skipping patch for "{page.title()}":'
              f' infobox abbrev mismatch (comments?).')
        return None
    foundInfobox.get('abbreviation').value = \
        foundAbbrev.replace(infoboxAbbrev, computedAbbrev, 1)
    mainEdit['text'] = str(code)

    patches = [mainEdit]
    groupDetails = ''

    regex = r' *{{\s*(r|R) from ISO ?4( abbreviation)?\s*}} *\n?'
    abbrevRegex = r'{{\s*(r|R)(edirect)? (from )?(common )?ab[a-z]*\s*}}'
    for rPage in getRedirectsToPage(page.title(), namespaces=0,
                                    total=100, content=True):
        rTitle = rPage.title()
        rRevision = rPage.latest_revision
        cAbbrev = abbrevUtils.stripTitle(computedAbbrev.lower())
        if cAbbrev + ' ' in rTitle.lower() + ' ' or \
           cAbbrev.replace('.', '') + ' ' in rTitle.lower() + ' ':
            newtext = rRevision.text
            if re.search(regex, newtext):
                print(f'Skipping patch for existing page, already marked: {rTitle}')
                groupDetails += 'ok: ' + rTitle + '\n'
                continue
            if not isReplaceableRedirect(rRevision.text, page.title(),
                                         RCatSet.ISO4):
                print(f'Skipping patch for unreplaceable page: {rTitle}')
                groupDetails += 'unrepl: ' + rTitle + '\n'
                continue
            if re.search(abbrevRegex, newtext):
                newtext = re.sub(abbrevRegex, '{{R from ISO 4}}', newtext, 1)
            else:
                newtext += '\n{{R from ISO 4}}'
            markPatch = {
                'patchtype': 'edit',
                'slug': 'mark new?',
                'title': rTitle,
                'summary': 'Fix ISO-4 abbreviation to use all language rules.',
                'minor': True,
                'basetimestamp':
                    datetimeFromPWB(rRevision.timestamp).isoformat(),
                'starttimestamp': startTimeStamp,
                'oldtext': rRevision.text,
                'oldrevid': rRevision.revid,
                'text': newtext
            }
            patches.append(markPatch)
        elif re.search(regex, rRevision.text):
            unmarkPatch = {
                'patchtype': 'edit',
                'slug': 'unmark old',
                'title': rTitle,
                'summary': 'Fix ISO-4 abbreviation to use all language rules.',
                'minor': True,
                'basetimestamp':
                    datetimeFromPWB(rRevision.timestamp).isoformat(),
                'starttimestamp': startTimeStamp,
                'oldtext': rRevision.text,
                'oldrevid': rRevision.revid,
                'text': re.sub(regex, '{{R from abbreviation}}\n', rRevision.text)
            }
            if infoboxAbbrev.lower() in rTitle.lower() or \
               infoboxAbbrev.replace('.', '').lower() in rTitle.lower():
                patches.append(unmarkPatch)
            else:
                print(f'Skip patch unmark on unrecog ISO-4: {rTitle}')
                groupDetails += 'unrecog ISO-4: ' + rTitle + '\n'
        else:
            groupDetails += '??: ' + rTitle + '\n'
    shouldHave = [computedAbbrev]
    if computedAbbrev.replace('.', '') != computedAbbrev:
        shouldHave.append(computedAbbrev.replace('.', ''))

    for abbrev in shouldHave:
        rPage = pywikibot.Page(Site(), abbrev)
        if not rPage.exists():
            createPatch = {
                'patchtype': 'create',
                'slug': 'create',
                'title': rPage.title(),
                'summary': 'R from ISO-4 abbreviation of journal title.',
                'minor': True,
                'starttimestamp': startTimeStamp,
                'text': '#REDIRECT[[' + page.title() + ']]\n\n'
                           '{{R from ISO 4}}\n'
            }
            patches.append(createPatch)

    return {
        'patchtype': 'group',
        'slug': f'{infoboxAbbrev} → {computedAbbrev}',
        'details': groupDetails,
        'patches': patches
    }


def doPatchlist(filename: str) -> None:
    startTimeStamp = datetime.now(timezone.utc).isoformat()
    # Patchset to propose for Stitchpitch
    result: Dict[str, Any] = {
        'patchtype': 'list',
        'slug': 'ISO-4 redirect creation',
        'patches': []
    }
    with open(filename) as f:
        for line in f:
            title = re.search(r'\[\[([^\[\]]+)\]\]', line).group(1)
            page = pywikibot.Page(Site(), title)
            target = page.getRedirectTarget().title()
            name = re.sub(r'\s*(.{6})\s*[-:–(].*', r'\1', title)
            rTitle = state.tryGetAbbrev(name, 'all')
            if rTitle is None:
                continue
            patchgroup = {
                'patchtype': 'group',
                'slug': f'{title} – {rTitle}',
                'details': f'<pre>{target}</pre>\n\n' + state.getMatchingPatterns(name),
                'patches': []
            }
            print(patchgroup['slug'])
            src = [rTitle]
            rTitleDotless = rTitle.replace('.', '')
            if rTitleDotless != rTitle:
                src.append(rTitleDotless)
            for srcTitle in src:
                rPage = pywikibot.Page(Site(), srcTitle)
                if rPage.exists():
                    print(f"Already exists: [[{srcTitle}]].")
                    continue
                createPatch = {
                    'patchtype': 'create',
                    'slug': 'create',
                    'title': rPage.title(),
                    'summary': 'R from ISO-4 abbreviation of journal title (supervised).',
                    'minor': True,
                    'starttimestamp': startTimeStamp,
                    'text': '#REDIRECT[[' + target + ']]\n\n'
                            '{{R from ISO 4}}\n'
                }
                patchgroup['patches'].append(createPatch)
            result['patches'].append(patchgroup)
    with open('patchset.json', 'wt') as f:
        json.dump(result, f)


if __name__ == '__main__':
    main()
