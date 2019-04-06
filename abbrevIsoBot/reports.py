# -*- coding: utf-8 -*-
"""Reports on potentially problematic articles or redirects.

Mismatch means the abbrv written in the infobox exists, but is not a soft match
for the automatically computed one (equal up to some cuts, see isSoftMatch()).
"""
import re
from typing import Any, Dict, List  # pylint: disable=unused-import
from unicodedata import normalize

import pywikibot

import state
import utils


# Each list contains tuples: [page title, infobox title, infobox abbrev, ..?].
__report = {
    # Titles containing colons early on, skipped for safety.
    'colon': [],
    # Trivial abbrevs (dotted abbreviations with no dots), skipped for safety.
    # Also in tuple: dict of all existing redirects (from rTitle to rContent).
    'nodots': [],
    # Pages that already exists and do not redirect to expected page.
    'existingpage': [],
    # Redirects that already exists with some unexpected rcats or parameters.
    # Also in tuple: redirect's content.
    'existingredirect': [],
    # Existing iso4 redirects that we would not add.
    # Also in tuple: redirect content, example of expected redirect title.
    'iso4redirect': [],
    # Mismatch between IJ abbrev parameter and abbrevIso computated abbrev.
    # Also in tuple: computed abbrev, deduced language, matchingPatterns.
    'mismatch': [],
    # Mismatch where changing the language would give a match.
    # Also in tuple: computed abbrev, other lang computed abbrev,
    #   infobox language, country, deduced language, matchingPatterns.
    'mismatchLang': []
}  # type: Dict[str, List[Any]]


def doReport(site: pywikibot.Site) -> None:
    """Build and save all reports."""
    # printReportOnInfoboxPerPageNumbers()
    mReport = getOverallStats()
    mReport += getShortMismatchReport()

    mLongReport = getOverallStats()
    mLongReport += getLongMismatchReport()
    mLongReport += getLanguageMismatchReport()

    oReport = ("The following is a list of journals or redirects that the bot"
               "skipped or considered unusual.\n\n")
    oReport += getColonInTitleReport()
    oReport += getTrivialAbbrevReport()
    oReport += getExistingRedirectReport()
    oReport += getExistingPageReport()
    oReport += getSuperfluousRedirectReport()

    page = pywikibot.Page(site, u"User:TokenzeroBot/ISO 4 unusual")
    page.text = oReport
    page.save(u'New report.', minor=False)
    print(oReport)

    page = pywikibot.Page(site, u"User:TokenzeroBot/ISO 4")
    page.text = mReport
    page.save(u'New report.', minor=False)
    print(mReport)

    page = pywikibot.Page(site, u"User:TokenzeroBot/ISO 4 mismatches")
    page.text = mLongReport
    page.save(u'New report.', minor=False)
    print(mLongReport)


def reportTitleWithColon(pageTitle: str,
                         infoboxTitle: str,
                         infoboxAbbrev: str) -> None:
    """Report infobox abbreviation that contains a colon.

    These may be tricky dependent titles or mishandled as interwiki links,
    so we just skip and report them.
    """
    __report['colon'].append([pageTitle, infoboxTitle, infoboxAbbrev])


def reportTrivialAbbrev(pageTitle: str,
                        infoboxTitle: str,
                        infoboxAbbrev: str,
                        allRedirects: List[str]) -> None:
    """Report abbrev that has not dots.

    (Nothing abbreviated except possibly for cutting short word).
    These are usually from journals that have just one or two words of
    a scientific term as their title (e.g. Nature),
    so creating a redirect could lead to confusion.
    """
    __report['nodots'].append([pageTitle, infoboxTitle, infoboxAbbrev,
                               allRedirects])


def reportExistingOtherPage(pageTitle: str,
                            infoboxTitle: str,
                            redirectTitle: str) -> None:
    """Report existing page that does not redirect to the page we came from.

    These are usually disambuigation pages.
    """
    __report['existingpage'].append([pageTitle, infoboxTitle, redirectTitle])


def reportExistingOtherRedirect(pageTitle: str,
                                infoboxTitle: str,
                                redirectTitle: str,
                                redirectContent: str) -> None:
    """Report unexpected redirect to the page we came from that already exists.

    Unexpected means with some unexpected rcats or parameters
    (like {{R from move}}).
    """
    __report['existingredirect'].append([pageTitle, infoboxTitle,
                                         redirectTitle, redirectContent])


def reportSuperfluousRedirect(pageTitle: str,
                              redirectTitle: str,
                              redirectContent: str,
                              exampleExpectedRedirectTitle: str) -> None:
    """Report existing redirects marked as ISO-4 that we would not add.

    `exampleExpectedRedirectTitle` is one of the required redirect titles.
    """
    __report['iso4redirect'].append([pageTitle, redirectTitle, redirectContent,
                                     exampleExpectedRedirectTitle])


def reportProperMismatch(pageTitle: str,
                         infoboxTitle: str,
                         infoboxAbbrev: str,
                         computedAbbrev: str,
                         computedLang: str,
                         matchingPatterns: str,
                         hasISO4Redirect: bool) -> None:
    """Report abbrev mismatch, where switching the language would not help."""
    __report['mismatch'].append([pageTitle, infoboxTitle,
                                 infoboxAbbrev, computedAbbrev,
                                 computedLang, matchingPatterns,
                                 hasISO4Redirect])


def reportLanguageMismatch(pageTitle: str,
                           infoboxTitle: str,
                           infoboxAbbrev: str,
                           computedAbbrev: str,
                           otherComputedAbbrev: str,
                           infoboxLanguage: str,
                           infoboxCountry: str,
                           computedLanguage: str,
                           matchingPatterns: str,
                           hasISO4Redirect: bool) -> None:
    """Report abbrev mismatch caused by language.

    That is, report mismatches that would not be a mismatch if we switched
    the guessed (computed) language.

    `computedLang` was computed based on `infoboxLanguage` and `infoboxCountry`
    `computedAbbrev` is the abbrev computed assuming `computedLanguage`
    `otherComputedAbbrev` is the abbrev computed assuming a different language
    (a soft match to `infoboxAbbrev`).
    `matchingPatterns` is the string that lists patterns that applied to the
    title when computing the abbreviation.
    """
    __report['mismatchLang'].append([pageTitle, infoboxTitle, infoboxAbbrev,
                                     computedAbbrev, otherComputedAbbrev,
                                     infoboxLanguage, infoboxCountry,
                                     computedLanguage, matchingPatterns,
                                     hasISO4Redirect])


def wikiEscape(s: str) -> str:
    """Escape wikitext (into wikitext that will show the raw code)."""
    return s.replace('<', '&lt;').replace('>', '&gt;') \
            .replace('{{', '{<nowiki />{').replace('}}', '}<nowiki />}') \
            .replace('[[', '[<nowiki />[').replace(']]', ']<nowiki />]') \
            .replace('|', '{{!}}')


def printReportOnInfoboxPerPageNumbers() -> None:
    """Print report on number of pages with i infoboxes, for each i."""
    print("==Number of infoboxes per page==")
    result: Dict[int, List[str]] = {}
    for title, page in state.getPagesDict().items():
        length = len(page['infoboxes'])
        if length not in result:
            result[length] = []
        result[length].append(title)
    for i in result:
        print("There are", len(result[i]), "pages with", i, "infoboxes.")
        if i == 0 or i >= 5:
            for title in result[i]:
                print("[[", title, "]]")


def getOverallStats() -> str:
    """Return wikitext with number of infobox-journals, mismatches, etc."""
    nTotal = 0  # In total.
    nIJsWithoutAbbrev = 0  # With no (human) abbreviation parameter.
    nIJsWithMissingAbbrev = 0  # With no computed abbreviation.
    nIJsWithExactMatch = 0  # With exact match.
    nIJsWithCompatMatch = 0  # With match up to e.g. removing parens.
    nIJsWithMismatch = 0  # With mismatch.
    for title, page in state.getPagesDict().items():
        for infobox in page['infoboxes']:
            t = re.sub(r'\s*\(.*(ournal|agazine|eriodical|eview)s?\)', '',
                       title)
            name = infobox.get('title', t)
            nTotal += 1
            if 'abbreviation' not in infobox or infobox['abbreviation'] == '':
                nIJsWithoutAbbrev += 1
            else:
                iabbrev = infobox['abbreviation']
                try:
                    cabbrev = state.getAbbrev(name, utils.getLanguage(infobox))
                except state.NotComputedYetError:
                    nIJsWithMissingAbbrev += 1
                    continue
                cabbrev = normalize('NFC', cabbrev).strip()
                if iabbrev == cabbrev:
                    nIJsWithExactMatch += 1
                elif utils.isSoftMatch(iabbrev, cabbrev):
                    nIJsWithCompatMatch += 1
                else:
                    nIJsWithMismatch += 1
    return ("Out of {} [[Template:Infobox journal|infobox journals]],\n"
            "{} have an empty ''abbreviation'' parameter,\n"
            "{} have the same as guessed by the bot,\n"
            "{} have something different.\n"
            "({} have no computed abbreviation)\n\n").format(
                nTotal,
                nIJsWithoutAbbrev,
                nIJsWithExactMatch + nIJsWithCompatMatch,
                nIJsWithMismatch,
                nIJsWithMissingAbbrev)


def getShortMismatchReport() -> str:
    """Get the shorter wiki report on mismatches.

    A costly template is used to display each mismatch,
    so we list fewer of them.
    """
    r = ("The first 50 mismatches:\n"
         "{| class='wikitable'\n|-\n"
         "!page title\n!infobox title\n"
         "!infobox abbrv\n!bot guess\n!validate\n!lang\n"
         "! scope='column' style='width: 400px;' | matching LTWA patterns\n")
    i = 0
    for wikititle, infotitle, iabbrev, cabbrev, clang, \
            matchingPatterns, hasISO4Redirect in sorted(__report['mismatch']):
        if hasISO4Redirect:
            continue
        i += 1
        if infotitle == wikititle:
            infotitle = ''
        if i <= 50:
            r += (f"|-\n{{{{ISO 4 mismatch"
                  f" |pagename={wikititle}"
                  f" |title={wikiEscape(infotitle)}"
                  f" |abbreviation={wikiEscape(iabbrev)}"
                  f" |bot-guess={wikiEscape(cabbrev)}"
                  f"}}}}\n"
                  f"|{(clang or '??')}\n"
                  f"|<pre style='white-space: pre'>{matchingPatterns}</pre>\n")
    r += "|}\n"
    return r


def getLongMismatchReport() -> str:
    """Get the longer wiki report on mismatches.

    This one is a simple table, so we can afford listing more.
    """
    r = ("== The first 200 mismatches ==\n"
         "{| class='wikitable'\n|-\n"
         "!page title\n!infobox title\n"
         "!infobox abbrv\n!bot guess\n!bot lang\n"
         "! scope='column' style='width: 400px;' "
         "| matching LTWA patterns\n")
    q = ("=== with existing redirect marked as ISO-4 ===\n"
         "We separately list mismatches when there already is a redirect "
         "categorized as ISO-4 (coming from the infobox abbrev), since it was "
         "probably edited by a human with more care, and because wrongly "
         "categorized redirects need to be fixed.\n"
         "{| class='wikitable'\n|-\n"
         "!page title\n!infobox title\n"
         "!infobox abbrv\n!bot guess\n!bot lang\n"
         "! scope='column' style='width: 400px;' "
         "| matching LTWA patterns\n")
    i = 0
    for wikititle, infotitle, iabbrev, cabbrev, clang, \
            matchingPatterns, hasISO4Redirect in sorted(__report['mismatch']):
        i += 1
        if infotitle == wikititle:
            infotitle = ''
        if infotitle:
            infotitle = '{{-r|' + wikiEscape(infotitle) + '}}'
        if i <= 200:
            s = (f"|-\n"
                 f"| [[{wikititle}]] "
                 f"|| {infotitle} "
                 f"|| {{{{-r|{wikiEscape(iabbrev)}}}}} "
                 f"|| {{{{-r|{wikiEscape(cabbrev)}}}}} "
                 f"|| {{{(clang or '??')} "
                 f"|| <pre style='white-space: pre'>"
                 f"{matchingPatterns}</pre>\n")
            if not hasISO4Redirect:
                r += s
            else:
                q += s
    return r + "|}\n\n" + q + "|}\n\n"


def getLanguageMismatchReport() -> str:
    """Get sub-report on mismatches that would match if lang would change."""
    r = ("== Wrong language rules? ==\n"
         "First 50 mismatches where just changing the language between 'eng'"
         " and 'all' would give a match (this affect which rules from the "
         "[[LTWA]] are used). This means that either the bot wrongly guessed "
         " the language to use (based on country and language infobox params),"
         " or that the editor applied non-English rules to an English title.\n"
         "{| class='wikitable'\n|-\n"
         "!page title\n!infobox title\n"
         "!infobox abbrv\n!bot guess\n!IJ lang\n!IJ country\n!bot lang\n"
         "! scope='column' style='width: 400px;' | matching LTWA patterns\n")
    q = ("=== with existing redirects marked as ISO-4 ===\n"
         "{| class='wikitable'\n|-\n"
         "!page title\n!infobox title\n"
         "!infobox abbrv\n!bot guess\n!IJ lang\n!IJ country\n!bot lang\n"
         "! scope='column' style='width: 400px;' | matching LTWA patterns\n")
    i = 0
    for wikititle, infotitle, iabbrev, cabbrev, _othercabbrev, \
            ilang, icountry, clang, matchingPatterns, hasISO4Redirect \
            in sorted(__report['mismatchLang']):
        i += 1
        if i > 50:
            break
        if infotitle == wikititle:
            infotitle = ''
        else:
            infotitle = '{{-r|' + wikiEscape(infotitle) + '}}'
        s = (f"|-\n| [[{wikititle}]]"
             f" || {infotitle}"
             f" || {{{{-r|{wikiEscape(iabbrev)}}}}}"
             f" || {{{{-r|{wikiEscape(cabbrev)}}}}}"
             f" || {wikiEscape(ilang)}"
             f" || {wikiEscape(icountry)}"
             f" || {(clang or '??')}"
             f" || <pre style='white-space: pre'>{matchingPatterns}</pre>\n")
        if not hasISO4Redirect:
            r += s
        else:
            q += s
    return r + "|}\n" + q + "|}\n"


def getColonInTitleReport() -> str:
    """Get sub-report on abbrevs containing colons.

    Colons may be impossible in wiki code because of inter-wiki syntax.
    """
    r = ("== Abbreviations containing colons ==\n"
         "(within first 4 characters; skipped by the bot for safety)\n"
         "{| class='wikitable'\n|-\n"
         "! page title !! infobox title !! infobox abbrv\n")
    for wikititle, infotitle, iabbrev in sorted(__report['colon']):
        if infotitle == wikititle or infotitle == '':
            infotitle = ''
        else:
            infotitle = "{{-r|" + wikiEscape(infotitle) + "}}"
        r += ("|-\n| [[" + wikititle + "]] || " + infotitle + " || "
              "{{-r|" + wikiEscape(iabbrev) + "}}\n")
    r += "|}\n\n"
    return r


def getTrivialAbbrevReport() -> str:
    """Get report on abbrevs without abbreviated words.

    These could create misleading redirects.
    """
    r = ("== Abbreviations without abbreviated words ==\n"
         "(skipped by the bot for safety)\n"
         "All the redirects marked as ISO-4 here may be wrong or confusing.\n"
         "{| class='wikitable'\n|-\n"
         "! page title !! infobox title !! infobox abbrv !! ISO-4 redirects\n")
    for wikititle, infotitle, iabbrev, redirects in sorted(__report['nodots']):
        if infotitle in (wikititle, iabbrev, ''):
            infotitle = ''
        else:
            infotitle = "{{-r|" + wikiEscape(infotitle) + "}}"
        s = []
        for rTitle, rContent in sorted(redirects.items()):
            if 'ISO' in rContent:
                s.append("{{-r|" + rTitle + "}}")
        if iabbrev not in redirects.keys() \
                and infotitle not in redirects.keys() and not s:
            continue
        ss = ", ".join(s)
        r += ("|-\n| [[" + wikititle + "]] || " + infotitle + " || "
              "{{-r|" + wikiEscape(iabbrev) + "}} || " + ss + "\n")
    r += "|}\n\n"
    return r


def getExistingRedirectReport() -> str:
    """Get sub-report on unexpected existing redirects.

    This includes unexpected rcats or parameters,
    which we don't want to overwrite.
    """
    r = ("== Unusual redirects ==\n"
         "Redirects (to the page we came from) that already exists "
         "with some unexpected rcats or parameters.\n"
         "{| class='wikitable'\n|-\n"
         "! page title !! infobox title !! infobox abbrv "
         "!! redirect content\n")
    for wikititle, infotitle, iabbrev, content \
            in sorted(__report['existingredirect']):
        if '#' in content[5:]:
            continue
        if infotitle == wikititle or infotitle == '':
            infotitle = ''
        else:
            infotitle = "{{-r|" + wikiEscape(infotitle) + "}}"
        r += (f"|-\n"
              f"| [[{wikititle}]] "
              f"|| {infotitle} "
              f"|| {{{{-r|{wikiEscape(iabbrev)}}}}} "
              f"|| <pre style='white-space: pre'>"
              f"<nowiki>{content}</nowiki></pre>\n")
    r += "|}\n\n"
    return r


def getExistingPageReport() -> str:
    """Get sub-report on pre-existing pages.

    These are non-redirect pages and redirects to unrelated pages,
    which we don't want to overwrite.
    """
    r = ("== Unusual redirect pages ==\nPages that already exist, "
         "redirecting to something unexpected or not a redirect at all "
         " (may be wrong or may need a [[WP:HAT|hatnote]]):\n"
         "{| class='wikitable'\n|-\n"
         "! page title !! infobox title !! r. from infobox abbrev\n")
    for wikititle, infotitle, iabbrev in sorted(__report['existingpage']):
        if infotitle == wikititle or infotitle == '':
            infotitle = ''
        else:
            infotitle = "{{-r|" + wikiEscape(infotitle) + "}}"
        r += ("|-\n| [[" + wikititle + "]] || " + infotitle + " || "
              "{{-r|" + wikiEscape(iabbrev) + "}} \n")
    r += "|}\n\n"
    return r


def getSuperfluousRedirectReport() -> str:
    """Get sub-report on ISO-4-categorized redirects that we would not add."""
    r = ("== Existing unexpected ISO-4 redirects ==\n"
         "Redirects marked as ISO-4 that the bot would not add. "
         "Very different ones are probably valid, like from former titles "
         "or other language, so we skip those from the report. "
         "Similar ones are probably a mistake. "
         "For ''PLoS'' vs ''PLOS'' I'd say both are valid.\n"
         "{| class='wikitable'\n|-\n"
         "! page title !! the redirect !! infobox abbreviation\n")
    for wikititle, rTitle, _rContent, \
            expectedRedirect in sorted(__report['iso4redirect']):
        r += (f"|-\n| [[{wikititle}]] || "
              f"{{{{-r|{rTitle}}}}} || "
              f"{wikiEscape(expectedRedirect)}\n")
        # f"||<pre style='white-space: pre'><nowiki>{content}</nowiki></pre>\n"
    r += "|}\n\n"
    return r
