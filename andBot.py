#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""A bot for Wikipedia, creating redirects between 'and'/'&' variants."""
from __future__ import unicode_literals
import logging
from itertools import chain
from typing import List, Set, Iterator

import pycld2  # Compact Language Detection

import pywikibot
import pywikibot.data.api

# Some basic config
SCRAPE_LIMIT = 100000  # Max number of pages to scrape.
# Max number of edits to make (in one run of the script).
EDITS_LIMITS = {'default': 3000}
EDITS_DONE = {'default': 0}
ONLY_SIMULATE_EDITS = False  # If true, only print what we'd do, don't edit.
BOT_TRIAL = False  # If true, we add the 'bot trial' tag to all edits.

site = None  # pywikibot's main object.


def main() -> None:
    """Run the bot."""
    global site  # pylint: disable=global-statement
    logging.basicConfig(level=logging.WARNING)
    # Initialize pywikibot.
    site = pywikibot.Site('en')

    # Let 'foreign' be the set of page titles in a language-category
    # other than english, or in the multilingual category.
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
    rPage = pywikibot.Page(site, rTitle)
    # Skip if the page already exists.
    if rPage.exists():
        print('Skipping (already exists): ', rTitle)
        return False
    # Create the redirect.
    print(f'Creating redirect from [[{rTitle}]] to [[{pageTitle}]]')
    rNewContent = '#REDIRECT [[' + pageTitle + ']]\n'
    rNewContent += '{{R from modification}}\n'
    summary = u'Redirect between ampersand/and variant.'
    return save(rPage, rNewContent, summary, overwrite=False)


def doVariants() -> None:
    """For all ISO-4 abbrevs, create redirects from popular variations."""
    redirects = getCategoryAsSet('Redirects from ISO 4 abbreviations',
                                 recurse=False)
    redirects = set(r for r in redirects if '.' in r)
    for i, rTitle in enumerate(redirects):
        print(f'Doing {i}/{len(redirects)}: {rTitle}', flush=True)
        variants = getVariantRedirects(rTitle)
        if len(variants) <= 2:
            print('Skip: no variants')
            continue
        print(f'Variants: {len(variants) - 2}')
        rPage = pywikibot.Page(site, rTitle)
        if not rPage.isRedirectPage():
            print('Skip: not a redirect')
            continue
        targetArticle = rPage.getRedirectTarget().title()
        if 'Category:' in targetArticle:
            print('Skip: redirect to a category')
            continue
        for variant in variants:
            if variant != rTitle and variant != rTitle.replace('.', ''):
                makeVariantRedirect(variant, targetArticle)


def getVariantRedirects(rTitle: str) -> List[str]:
    """Get list of variant abbreviations similar to rTitle.

    Similar means obtained by replacing an ISO-4 abbreviation with a
    popular non-ISO-4 alternative hardcoded here, or by removing dots.
    In particular both rTitle and rTitle.replace('.', '') will be returned.
    """
    variantTitles = [rTitle]
    replacements = [('Adm.', 'Admin.'),
                    ('Animal', 'Anim.'),
                    ('Am.', 'Amer.'),
                    ('Atmospheric', 'Atmos.'),
                    ('Br.', 'Brit.'),
                    ('Calif.', 'Cal.'),
                    ('Commun.', 'Comm.'),
                    ('Entomol.', 'Ent.'),
                    ('Investig.', 'Invest.'),
                    ('Lond.', 'London'),
                    ('Philos.', 'Phil.'),
                    ('Political', 'Polit.'),
                    ('Radiat.', 'Rad.'),
                    ('Royal', 'Roy.'),
                    ('Royal', 'R.'),
                    ('Special', 'Spec.')]
    for replIso, replVariant in replacements:
        newVariantTitles = variantTitles
        for vTitle in variantTitles:
            if replIso in vTitle:
                newVariantTitles.append(vTitle.replace(replIso, replVariant))
        variantTitles = newVariantTitles
    dotless = [v.replace('.', '') for v in variantTitles]
    variantTitles.extend(dotless)
    return variantTitles


def makeVariantRedirect(vTitle: str, targetArticle: str) -> bool:
    """Try creating a redirect from vTitle to targetArticle."""
    rPage = pywikibot.Page(site, vTitle)
    # Skip if the page already exists.
    if rPage.exists():
        print('Skipping variant (already exists): ', vTitle)
        return False
    # Create the redirect.
    print(f'Creating redirect from [[{vTitle}]] to [[{targetArticle}]]')

    # Check number of results in Google search: only possible for <100 request.
    # sleepTime = 15
    # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    #            'AppleWebKit/537.36 (KHTML, like Gecko) '
    #            'Chrome/60.0.3112.113 Safari/537.36'}
    # url = 'https://www.google.com/search?'
    # url += urllib.parse.urlencode({'q': '"' + vTitle + '"'})
    # while True:
    #     try:
    #         sleep(sleepTime)
    #         req = urllib.request.Request(url, headers=headers)
    #         with urllib.request.urlopen(req) as response:
    #             html = str(response.read())
    #             if 'No results found' in html:
    #                 print('No Results')
    #                 return False
    #             regex = r'([0-9]+),?\s*([0-9]+),?\s*([0-9]*)\s*results'
    #             m = re.search(regex, html)
    #             if not m:
    #                 print('no Results')
    #                 return False
    #             res = m.group(1) + m.group(2) + m.group(3)
    #             print('Results=', res)
    #             if int(res) < 5:
    #                 return False
    #             break
    #     except urllib.error.URLError as err:
    #         print('Exception: ', sys.exc_info()[0], '\n', err.reason)
    #         sleepTime *= 2
    #         print('sleep=', sleepTime, flush=True)

    rNewContent = '#REDIRECT [[' + targetArticle + ']]\n'
    rNewContent += '{{R from abbreviation}}\n'
    summary = u'Redirect from variant abbreviation.'
    return save(rPage, rNewContent, summary, overwrite=False)


def getCategoryAsSet(name: str, recurse: bool = True, namespaces: int = 0) \
        -> Set[str]:
    """Get all titles of pages in given category as a set().

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


def getPagesWithTemplate(name: str, content: bool = False) \
        -> Iterator[pywikibot.Page]:
    """Yield all mainspace, non-redirect pages transcluding given template.

    Note that while the first letter is normalized, others are not,
    so check synonyms (redirects to the template):
        https://en.wikipedia.org/w/index.php?title=Special:WhatLinksHere/Template:Infobox_journal&hidetrans=1&hidelinks=1
    """
    assert site
    if not name.startswith('Template:'):
        name = 'Template:' + name
    ns = site.namespaces['Template']
    template = pywikibot.Page(site, name, ns=ns)
    return template.embeddedin(
        filter_redirects=False,  # Omit redirects
        namespaces=0,            # Mainspace only
        total=SCRAPE_LIMIT,       # Limit total number of pages outputed
        content=content)         # Whether to immediately fetch content


def save(page: pywikibot.Page,
         content: str,
         summary: str,
         overwrite: bool,
         limitType: str = 'default') -> bool:
    """Create or overwrite page with given content, checking bot limits."""
    global EDITS_DONE
    if ONLY_SIMULATE_EDITS:
        return False
    if limitType not in EDITS_LIMITS or limitType not in EDITS_DONE:
        raise Exception(f'Undefined limit type: "{limitType}"')
    if EDITS_DONE[limitType] >= EDITS_LIMITS[limitType]:
        return False
    EDITS_DONE[limitType] += 1
    page.text = content
    summary = (f'[[Wikipedia:Bots/Requests_for_approval/TokenzeroBot_6|(6)]] '
               f'{summary} [[User talk:TokenzeroBot|Report problems]]')
    page.save(summary,
              minor=False,
              botflag=True,
              watch="nochange",
              createonly=False if overwrite else True,
              nocreate=True if overwrite else False,
              tags='bot trial' if BOT_TRIAL else None)
    return True


if __name__ == "__main__":
    main()
