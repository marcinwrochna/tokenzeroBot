/**
 * @module tinfoboxUtil
 * Common util functions.
 * Usage: see User:Tokenzero/infoboxJournal.js for how to load a module.
 *  import * as util from '/w/index.php?title=User:Tokenzero/tinfoboxUtil.js&action=raw&ctype=text%2Fjavascript';
 *  (async function() {
 *      console.log(await util.getWikitext('Foo'));
 *  })();
 */

/**
 * Escape HTML special characters.
 *
 * @param {string} s
 * @returns {string}
 */
export function escapeHTML(s) {
    return $('<div>').text(s).html();
}

/**
 * Return whether s is false-y or pure-whitespace string.
 *
 * @param {string} s
 * @returns {boolean}
 */
export function isTrivialString(s) {
    return !s || !s.trim();
}

/**
 * Create an object from a list of entries.
 * Polyfills ECMAScript2019 Object.fromEntries() (not currently supported in Edge).
 *
 * @param {Iterable<[string, *]>} entries - Output of Object.entries(obj) or Map.entries().
 * @returns {object}
 */
export function objectFromEntries(entries) {
    const result = {};
    for (const [key, value] of entries)
        result[key] = value;
    return result;
}

/**
 * Return the wikitext of given [[pageTitle]].
 *
 * @param {string} pageTitle
 * @returns {Promise<string>}
 */
export async function getWikitext(pageTitle) {
    return $.ajax({
        url: mw.util.getUrl(pageTitle, { action: 'raw' }),
        data: 'text'
    });
}

/**
 * Return whether [[pageTitle]] exists.
 *
 * @param {string} pageTitle
 * @returns {Promise<boolean>}
 */
export async function pageExists(pageTitle) {
    const data = await (new mw.Api()).get({
        formatversion: 2,
        prop: 'info',
        titles: pageTitle
    });
    return !data.query.pages[0].missing;
}

/**
 * Return a list of subcategory titles. Not recursive.
 *
 * @param {string} categoryTitle
 * @returns {Promise<Array<string>>}
 */
export async function getSubcategories(categoryTitle) {
    const data = await (new mw.Api()).get({
        formatversion: 2,
        list: 'categorymembers',
        cmtitle: 'Category:' + categoryTitle,
        cmtype: 'subcat',
        cmlimit: 'max' // The default max is 500.
    });
    return data.query.categorymembers.map((c) => c.title);
}

/**
 * Parse and return all categories in given wikitext.
 * Category links are included (useful for testing, drafts).
 * Namespace prefix and sortkey is cut out.
 * So parseCategories('[[:Category:Foo|]]') returns ['Foo'].
 *
 * @param {string} wikitext
 * @returns {Array<string>}
 */
export function parseCategories(wikitext) {
    // In general, use mw.config.get('wgFormattedNamespaces')[14] to get localized name,
    // mw.config.get('wgNamespaceIds') to find aliases, check case-sensitivity settings,
    // see also HotCat for more on whitespace transformations.
    const result = [];
    const catRegex = /\[\[\s*:?\s*[Cc]ategory\s*:\s*([^|\]]+)(|[^\]]+)?\s*\]\]/g;
    wikitext = wikitext.replace(/<!--.*?-->/g, '').replace(/<nowiki>.*?<\/nowiki>/g, '');
    let match;
    while ((match = catRegex.exec(wikitext)) !== null)
        result.push(match[1]);
    return result;
}

/**
 * Check if category has a parent category matching some regex.
 * Filters intermediate ancestors to reduce number of api calls.
 *
 * @param {string} categoryTitle - category to start from
 * @param {RegExp} ancestorRegex - the final ancestor should test positively
 * @param {RegExp} interRegex - tested on all intermediate ancestors
 *  (including the final one, excluding the starting categoryTitle)
 * @param {number} maxDepth - depth 0 compares categoryTitle directly with ancestorRegex
 * @returns {Promise<boolean>}
 */
export async function isCategoryChildOf(categoryTitle, ancestorRegex, interRegex, maxDepth) {
    categoryTitle = categoryTitle.replace('Category:', '').replace(/_/g, ' ');
    console.log(maxDepth, categoryTitle);
    if (maxDepth === 0)
        return ancestorRegex.test(categoryTitle);
    if (ancestorRegex.test(categoryTitle))
        return true;
    const parents = await (new mw.Api()).getCategories('Category:' + categoryTitle);
    for (const parentData of parents) {
        const parent = parentData.title;
        if (interRegex.test(parent)) {
            if (await isCategoryChildOf(parent, ancestorRegex, interRegex, maxDepth - 1))
                return true;
        }
    }
    return false;
}

/**
 * Redirect browser to execute specified POST action.
 *
 * @param {string} url
 * @param {Map<string,string>} data
 */
export function redirectPost(url, data) {
    const form = $('<form>', {
        method: 'POST',
        action: url
    });
    for (const k of data.keys()) {
        form.append($('<input>', {
            type: 'hidden',
            name: k,
            value: data.get(k)
        }));
    }
    form.appendTo('body').submit();
}

/**
 * Redirect to diff-preview view with modified wikitext.
 *
 * @param {string} wikitext
 * @param {string} summary
 */
export async function redirectToPreviewDiff(wikitext, summary) {
    const r = await (new mw.Api()).get({
        prop: 'revisions',
        rvprop: 'timestamp',
        revids: mw.config.get('wgRevisionId')
    });
    const wgEdittime = r.query.pages[mw.config.get('wgArticleId')]
        .revisions[0].timestamp.replace(/[^0-9]/gi, '').slice(0, 12);
    const wgStarttime = new Date(window.performance.timing.requestStart)
        .toISOString().replace(/[^0-9]/gi, '').slice(0, 12);
    redirectPost(
        mw.util.getUrl(mw.config.get('wgPageName'), { action: 'edit' }),
        new Map([
            ['editRevId', mw.config.get('wgRevisionId')],
            ['baseRevId', mw.config.get('wgRevisionId')],
            ['wpSection', ''],
            ['wpStarttime', wgStarttime],
            ['wpEdittime', wgEdittime],
            ['parentRevId', mw.config.get('wgRevisionId')],
            ['format', 'text/x-wiki'],
            ['model', 'wikitext'],
            ['wpTextbox1', wikitext],
            ['wpSummary', summary],
            ['wpAutoSummary', 'd41d8cd98f00b204e9800998ecf8427e'], // this is md5('')
            ['wpDiff', 'Show changes'], // ['wpPreview', 'yes'],
            ['wpEditToken', mw.user.tokens.get('editToken')],
            ['mode', 'preview'],
            ['wpUltimateParam', 1] // A weird mediawiki safety check.
        ])
    );
}
