#!/usr/bin/env python3
"""For all ISO-4 abbrevs, create redirects from popular variations.

That is, for each redirect in [[Category:Redirects from ISO 4 abbreviations]],
if it does not redirect to a category (as for many less notable titles),
we create redirects from variants obtained by replacing e.g.:
    - and with ampersand &
    - dots with nothing
    - 'Am.' with 'Amer.'
(see `getVariantRedirects`) for a full list.
"""
from __future__ import absolute_import
import logging
from typing import List

import pywikibot
import pywikibot.data.api
from pywikibot import Site

import utils


def main() -> None:
    """Run the bot."""
    logging.basicConfig(level=logging.WARNING)
    # Initialize pywikibot.
    assert Site().code == 'en'
    utils.initLimits(
        editsLimits={'default': 3000},
        brfaNumber=6,
        onlySimulateEdits=False,
        botTrial=False
    )

    redirects = utils.getCategoryAsSet('Redirects from ISO 4 abbreviations',
                                       recurse=False)
    redirects = set(r for r in redirects if '.' in r)
    for i, rTitle in enumerate(redirects):
        print(f'Doing {i}/{len(redirects)}: {rTitle}', flush=True)
        variants = getVariantRedirects(rTitle)
        if len(variants) <= 2:
            print('Skip: no variants')
            continue
        print(f'Variants: {len(variants) - 2}')
        rPage = pywikibot.Page(Site(), rTitle)
        if not rPage.isRedirectPage():
            print('Skip: not a redirect')
            continue
        if ':' in rTitle[:5]:
            print('Skip: colon in title.')
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
                    ('Contributions', 'Contrib.'),
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
    rPage = pywikibot.Page(Site(), vTitle)
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
    summary = 'Redirect from variant abbreviation.'
    return utils.trySaving(rPage, rNewContent, summary, overwrite=False)


if __name__ == "__main__":
    main()
