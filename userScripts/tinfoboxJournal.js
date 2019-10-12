/**
 * @module tinfoboxJournal
 * The meat of the infoboxJournal.js user script.
 */
import * as util from './tinfoboxUtil.js';
import { TemplateData, TemplateDataParam } from './tinfoboxTemplateData.js';
import { TemplateChoice, HelperData } from './tinfoboxHelperData.js';

/** Called at the end of this module. */
function main() {
    if (mw.config.get('wgIsProbablyEditable')) {
        mw.util.addPortletLink(
            'p-cactions',
            '#',
            'Infobox journal',
            'ca-infobox-journal',
            'Add or normalize infobox-journals.'
        );
        $('#ca-infobox-journal').click(onClick);
    }

    /** If we have been redirected, session stores HelperData from which we make the widget. */
    if (sessionStorage.getItem('tinfoboxHelperData')) {
        const helperData = HelperData.fromJSONString(
            sessionStorage.getItem('tinfoboxHelperData')
        );
        sessionStorage.removeItem('tinfoboxHelperData');
        console.log(helperData);
        helperData.buildWidget().insertBefore($('#wikiDiff, .mw-editform')[0]);
    }
}

/**
 * Executed on portletLink click.
 *
 * @param {JQuery.ClickEvent} event
 */
async function onClick(event) {
    event.preventDefault();
    // let util = await import('./tinfoboxUtil.js');
    // let TinfoboxJournalModule = await import('./tinfoboxJournal.js');
    // let fixInfoboxJournals = TinfoboxJournalModule.fixInfoboxJournals;

    if (mw.config.get('wgAction') === 'edit' || mw.config.get('wgAction') === 'submit') {
        const wikitext = /** @type {string} */($('#wpTextbox1').val());
        const [newWikitext, summary, helperData] = await fixInfoboxJournals(wikitext);
        $('#wpTextbox1').val(newWikitext);
        if (!$('#wpSummary').val())
            $('#wpSummary').val(summary);
        helperData.buildWidget().insertBefore($('#wikiDiff, .mw-editform')[0]);
    } else {
        mw.notify('Standarizing infobox journals...', { type: 'info' });
        const wikitext = await util.getWikitext(mw.config.get('wgPageName'));
        const [newWikitext, summary, helperData] = await fixInfoboxJournals(wikitext);
        sessionStorage.setItem('tinfoboxHelperData', helperData.toJSONString());
        await util.redirectToPreviewDiff(newWikitext, summary);
    }
}

/**
 * Normalize or add infobox-journal templates.
 *
 * Reorders and reformats existing infoboxes, or adds a new pre-formatted;
 * also tries to pre-fill some values; removes redundant '{{italic title}}'.
 *
 * @param {string} wikitext
 * @returns {Promise<[string, string, HelperData]>} Modified wikitext, edit summary, HelperData.
 */
export async function fixInfoboxJournals(wikitext) {
    // Alternative names of {{infobox journal}}:
    const ijNames = ['infobox journal', 'infobox academic journal', 'journal',
        'journal infobox', 'infobox serial publication', 'infobox journal series'];
    // const _imNames = ['infobox magazine', 'infobox periodical', 'infobox publication',
    //  'infobox pulps'];
    const templateData = await getInfoboxJournalTemplateData();
    // Alternative names of {{italic title}}
    const italicNames = ['italic title', 'ital', 'italic', 'italic title infobox',
        'italics', 'italics title', 'italicstitle', 'italictitle', 'title italic',
        'italicised title', 'italicisedtitle', 'italicize title',
        'italicized title', 'italicizedtitle', 'italicizetitle'];
    let result = wikitext;
    let summary = 'with ([[User:Tokenzero/infoboxJournal|infoboxJournal.js]])';
    const helperData = new HelperData();
    const ijTemplates = [];
    const templates = window.extraJs.parseTemplates(wikitext, false); // Non-recursive.
    for (const t of templates) {
        const tName = t.name.trim().toLowerCase();
        if (ijNames.includes(tName)) {
            ijTemplates.push(t);
        } else if (italicNames.includes(tName)) {
            // Remove the 'italic' template together with whitespace/newline after it.
            const regex = new RegExp(mw.util.escapeRegExp(t.wikitext) + '\\ *\\n?');
            result = result.replace(regex, '');
        }
    }
    if (ijTemplates.length === 0) {
        summary = 'Adding infobox journal ' + summary;
        const index = result.match(/^( *({{.*}} *)*\n)*/m)[0].length;
        const ijt = new window.extraJs.Template('{{Infobox journal}}');
        ijt.setName('Infobox journal');
        const [infobox, templateChoice] =
            await rebuildInfoboxJournal(ijt, wikitext, templateData);
        helperData.templateChoices.push(templateChoice);
        result = result.slice(0, index) + infobox + '\n' + result.slice(index);
    } else {
        summary = 'Standardizing infobox journal ' + summary;
        for (const t of ijTemplates) {
            const [infobox, templateChoice] =
                await rebuildInfoboxJournal(t, wikitext, templateData);
            helperData.templateChoices.push(templateChoice);
            // Remove whitespace with at most one new line and always add one newline.
            const regex = new RegExp(mw.util.escapeRegExp(t.wikitext) + '\\ *\\n?');
            result = result.replace(regex, infobox + '\n');
        }
        if (ijTemplates.length > 1) {
            helperData.messages.push({
                type: 'warning',
                message: 'More than one infobox found, use at your own risk.'
            });
        }
    }
    return [result, summary, helperData];
}

/**
 * Rebuild wikicode for given infobox-journal Template.
 *
 * @param {ExtraJs.Template} ijt - Template object for current infobox
 * @param {string} wikitext - wikitext of whole page (used for prefilling params)
 * @param {TemplateData} templateData - the TemplateData object for infobox-journal.
 * @returns {Promise<[string, TemplateChoice]>} new wikicode for the infobox, from '{{' to '}}'
 */
async function rebuildInfoboxJournal(ijt, wikitext, templateData) {
    const templateChoice = new TemplateChoice(templateData);
    const weaklySuggested = ['bluebook', 'mathscinet', 'nlm',
        'peer-reviewed', 'image_size', 'alt']; // 'ISSNlabel'? 'caption'?

    // For 'suggested' parameters, propose their 'autovalue'.
    // (Don't suggest the 'default', which is the value assumed when none is given).
    // Suggest with empty string if no 'autovalue' given (instead of suggesting deletion).
    for (const param of templateData.params.values()) {
        if (param.suggested) {
            templateChoice.param(param.key).proposedValue = param.autovalue || '';
            // Prefer suggested value unless anything appears in ijt.parameters later.
            templateChoice.param(param.key).preferOriginal = false;
            // Only prefer weakly suggested value if introducing new template.
            if (weaklySuggested.includes(param.key) && ijt.parameters.length)
                templateChoice.param(param.key).preferOriginal = true;
        }
    }

    // Load original parameters.
    for (const p of ijt.parameters) {
        const canonicalKey = templateData.toCanonicalKey(p.name);
        // Report duplicate parameters.
        if (templateChoice.param(canonicalKey).originalKey) {
            templateChoice.param(canonicalKey).messages.push({
                type: 'warning',
                message: `Deleted duplicate of "${canonicalKey}" parameter:` +
                         ` "|${p.name}=${p.value}".`
            });
            continue;
        }

        templateChoice.param(canonicalKey).originalKey = p.name;
        templateChoice.param(canonicalKey).originalValue = p.value;
        templateChoice.param(canonicalKey).preferOriginal = true;

        // Report unexpected parameters.
        if (!templateData.params.has(canonicalKey)) {
            // Ignore and skip empty unnamed parameter, someone just wrote one '|' too many.
            if ((!canonicalKey || typeof canonicalKey === 'number') &&
                    util.isTrivialString(p.value))
                continue;
            templateChoice.param(canonicalKey).messages.push({
                type: 'notice',
                message: 'No TemplateData for this param.'
            });
        }
    }

    // Prefills overwrite autovalues, but mostly keep preferOriginal true.
    const notification = mw.notify('Querying categories (this might take a few seconds)...',
        { type: 'info', autoHideSeconds: 30 });
    await prefillParameters(templateChoice, wikitext);
    // Notify that time-consuming ajax requests are finished.
    notification.then((n) => n.close());
    if (mw.config.get('wgAction') === 'edit' || mw.config.get('wgAction') === 'submit')
        mw.notify('Done.', { type: 'info' });
    else
        mw.notify('Redirecting...', { type: 'info', autoHideSeconds: 10 });
    for (const p of templateChoice.paramChoices.values()) {
        if (p.proposedValue === p.templateData.default)
            p.proposedValue = '';
    }

    for (const p of ijt.parameters) {
        const canonicalKey = templateData.toCanonicalKey(p.name);
        // If original value was absent, empty, equal to the default, or the param is deprecated,
        // then always prefer the proposed value (prefill, autovalue or '' if only suggested),
        // even if proposed is null (which will delete the parameter).
        // TODO evaluate template substitutions in autovalue.
        if (util.isTrivialString(p.value) ||
                p.value.trim() === templateData.param(canonicalKey).default ||
                p.value.trim() === templateData.param(canonicalKey).autovalue ||
                templateData.param(canonicalKey).deprecated) {
            templateChoice.param(canonicalKey).preferOriginal = false;
            // Except if original value was not absent and proposed value is trivial.
            // E.g. empty params won't be replaced with default comments.
            if (p.value !== null && templateChoice.param(canonicalKey).isProposedValueTrivial())
                templateChoice.param(canonicalKey).preferOriginal = true;
        // Same if original value was a comment (other than autovalue), but notify.
        } else if (!p.value.replace(/<!--[^>]*-->/g, '').trim()) {
            templateChoice.param(canonicalKey).messages.push({
                type: 'notice',
                message: 'Replacing unexpected comment.'
            });
            templateChoice.param(canonicalKey).preferOriginal = false;
        }
        // Otherwise we prefer the original by default.
        // Some prefills might have been strong enough to immediately prefer themselves, though.
    }

    // Format the template wikicode.
    const finalMap = new Map();
    for (const [canonicalKey, paramChoice] of templateChoice.paramChoices.entries()) {
        const key = paramChoice.originalKey || canonicalKey; // Prefer preserving original key.
        const value = paramChoice.preferOriginal
            ? paramChoice.originalValue
            : paramChoice.proposedValue;
        if (value != null)
            finalMap.set(canonicalKey, [key, value]);
    }
    const result = templateData.build(finalMap, ijt.name.trim());
    return [result, templateChoice];
}

/**
 * Try to pre-fill some parameters e.g. based on categories.
 *
 * @param {TemplateChoice} data
 * @param {string} wikitext
 */
async function prefillParameters(data, wikitext) {
    // Title
    data.param('title').proposedValue = mw.config.get('wgTitle').replace(/\s+\(.+/, '');

    // Prefills based on categories.
    let categories = [];
    if (mw.config.get('wgAction') === 'view')
        categories = mw.config.get('wgCategories'); // Includes categories from templates.
    else
        categories = util.parseCategories(wikitext); // Does not include categories from templates.
    // Another option is  await (new mw.Api()).getCategories(mw.config.get('wgPageName'));
    // But this does not include current editor changes.

    let historyStart = '';
    let historyEnd = 'present';
    for (const category of categories) {
        // Language
        let match = category.match(/(.+)-language (journal|magazine)/);
        if (match) {
            let language = data.param('language').proposedValue;
            if (language)
                language += ', ' + match[1];
            else
                language = match[1];
            data.param('language').proposedValue = language;
        }
        // Frequency
        const frequencyMap = new Map([
            ['continuous', 'Continuous'],
            ['weekly', 'Weekly'],
            ['biweekly', 'Biweekly'],
            ['bi-weekly', 'Biweekly'],
            ['fortnightly', 'Fortnightly'],
            ['monthly', 'Monthly'],
            ['bimonthly', 'Bimonthly'],
            ['bi-monthly', 'Bimonthly'],
            ['semimonthly', 'Semimonthly'],
            ['semi-monthly', 'Semimonthly'],
            ['annual', 'Annually'],
            ['biannual', 'Biannually'],
            ['bi-annual', 'Biannually'],
            ['triannual', 'Triannually'],
            ['tri-annual', 'Triannually'],
            ['quarterly', 'Quarterly'],
            ['irregular', 'Irregular'],
            ['irregularly published', 'Irregular'],
            ['8 times per year', '8/year'],
            ['eight times annually', '8/year'],
            ['nine times annually', '9/year'],
            ['ten times annually', '10/year'],
            ['10 times per year', '10/year'],
            ['36 times per year', '36/year']
        ]);
        for (const [pattern, value] of frequencyMap) {
            const regex = new RegExp(
                '(\\s|^)' + mw.util.escapeRegExp(pattern) + '\\s(journals|magazines)',
                'i'
            );
            if (regex.test(category))
                data.param('frequency').proposedValue = value;
        }
        // Publisher
        match = category.match(/^(.+) academic journals$/);
        if (match) {
            const ancestor = /^Academic journals by publisher/;
            if (await util.isCategoryChildOf(category, ancestor, /journal/, 9)) {
                const newPublisher = '[[' + match[1] + ']]';
                let publisher = data.param('publisher').proposedValue;
                if (data.param('publisher').isProposedValueTrivial())
                    publisher = newPublisher;
                else
                    publisher += ', ' + newPublisher;
                data.param('publisher').proposedValue = publisher;
            }
        }
        // Discipline
        match = category.match(/^(.+) journals$/);
        if (match) {
            const ancestor = /^Academic journals by subject area/;
            if (await util.isCategoryChildOf(category, ancestor, /journal/, 9)) {
                let newDiscipline = match[1];
                if (await util.pageExists(newDiscipline))
                    newDiscipline = '[[' + newDiscipline + ']]';
                let discipline = data.param('discipline').proposedValue;
                if (data.param('discipline').isProposedValueTrivial())
                    discipline = newDiscipline;
                else
                    discipline += ', ' + newDiscipline;
                data.param('discipline').proposedValue = discipline;
            }
        }
        // History
        match = category.match(/^(Publications|Magazines) established in ([0-9]+)$/);
        if (match)
            historyStart = match[2];
        match = category.match(/^(Publications|Magazines) disestablished in ([0-9]+)$/);
        if (match)
            historyEnd = match[2];
        if (historyEnd === 'present' && /^Defunct journals/.test(category))
            historyEnd = '?';
        // Open access
        const ancestor = /^Open access journals/;
        if (category === 'Delayed open access journals')
            data.param('openaccess').proposedValue = '[[Delayed open access journal|Delayed]]';
        else if (category === 'Hybrid open access journals')
            data.param('openaccess').proposedValue = '[[Hybrid open access journal|Hybrid]]';
        else if (!data.param('openaccess').proposedValue &&
                 !category.includes('Commons') &&
                 category.endsWith('journals') &&
                 await util.isCategoryChildOf(category, ancestor, /journals/, 1))
            data.param('openaccess').proposedValue = 'Yes';
    }
    if (historyStart || historyEnd !== 'present')
        data.param('history').proposedValue = historyStart + '–' + historyEnd;
    // TODO avoid 'present' if in Category:Defunct journals‎/periodicals.

    // Prefills based on templates.
    const templates = window.extraJs.parseTemplates(wikitext, false); // Non-recursive.
    for (const template of templates) {
        // Website
        const tNames = ['companywebsite', 'homepage', 'mainwebsite', 'official', 'officialhomepage',
            'offficialwebsite', 'officialwebsite', 'officialwebpage', 'officialsite'];
        if (tNames.includes(template.name.toLowerCase().replace(/\s/g, ''))) {
            let url = template.getParam('1') ||
                      template.getParam('url') ||
                      template.getParam('URL');
            if (!url)
                continue; // TODO use wikidata "official website" Property (P856).
            url = url.value.trim();
            if (!/\/\//.test(url))
                url = 'http://' + url;
            data.param('website').proposedValue = url;
        }
        // ISSN, eISSN
        if (template.name.toLowerCase() === 'issn') {
            for (const param of template.parameters) {
                if (typeof param.name === 'number') {
                    if (!data.param('ISSN').proposedValue) {
                        data.param('ISSN').proposedValue = param.value;
                    } else if (data.param('ISSN').proposedValue !== param.value) {
                        data.param('ISSN').messages.push({
                            type: 'warning',
                            message: `Found another: ${param.value}`
                        });
                    }
                }
            }
        }
        if (template.name.toLowerCase() === 'eissn') {
            for (const param of template.parameters) {
                if (typeof param.name === 'number') {
                    if (!data.param('eISSN').proposedValue) {
                        data.param('eISSN').proposedValue = param.value;
                    } else if (data.param('eISSN').proposedValue !== param.value) {
                        data.param('eISSN').messages.push({
                            type: 'warning',
                            message: `Found another: ${param.value}.`
                        });
                    }
                }
            }
        }
    }

    // History dashes - always change to ndash.
    if (!util.isTrivialString(data.param('history').originalValue)) {
        let value = data.param('history').originalValue;
        value = value.replace(/\s*(-|—|‑|‒|–|&mdash;|&#45;|&#8212;|&#x2014;|to)\s*/g, '–');
        if (!data.param('history').isProposedValueTrivial() &&
                data.param('history').proposedValue !== value) {
            data.param('history').messages.push({
                type: 'notice',
                message: `Categories suggest "${data.param('history').proposedValue}" instead.`
            });
        }
        data.param('history').proposedValue = value;
        data.param('history').preferOriginal = false;
    }
}

/**
 * Get config of how the infobox should be rebuilt.
 *
 * @returns {Promise<TemplateData>}
 */
async function getInfoboxJournalTemplateData() {
    const templateData = await TemplateData.fetch('Template:Infobox journal');
    console.log('Fetched TemplateData:', templateData);

    templateData.paramOrder = [
        'title',
        'italic title', // Added
        'image', 'image_size', 'alt',
        'caption',
        'former_name',
        'abbreviation',
        'bluebook',
        'mathscinet',
        'nlm',
        'bypass-rcheck', // Added
        'discipline',
        'peer-reviewed',
        'language',
        'editor',
        'publisher',
        'country',
        'history',
        'frequency',
        'openaccess', 'license',
        'impact', 'impact-year',
        'ISSNlabel', 'ISSN', 'eISSN', 'CODEN', 'JSTOR', 'LCCN', 'OCLC',
        'ISSN2label', 'ISSN2', 'eISSN2', 'CODEN2', 'JSTOR2', 'LCCN2', 'OCLC2', // Added
        'ISSN3label', 'ISSN3', 'eISSN3', 'CODEN3', 'JSTOR3', 'LCCN3', 'OCLC3', // Added
        'ISSN4label', 'ISSN4', 'eISSN4', 'CODEN4', 'JSTOR4', 'LCCN4', 'OCLC4', // Added
        'ISSN5label', 'ISSN5', 'eISSN5', 'CODEN5', 'JSTOR5', 'LCCN5', 'OCLC5', // Added
        'ISSN6label', 'ISSN6', 'eISSN6', 'CODEN6', 'JSTOR6', 'LCCN6', 'OCLC6', // Added
        'ISSN7label', 'ISSN7', 'eISSN7', 'CODEN7', 'JSTOR7', 'LCCN7', 'OCLC7', // Added
        'ISSN8label', 'ISSN8', 'eISSN8', 'CODEN8', 'JSTOR8', 'LCCN8', 'OCLC8', // Added
        'ISSN9label', 'ISSN9', 'eISSN9', 'CODEN9', 'JSTOR9', 'LCCN9', 'OCLC9', // Added
        'website',
        'link1', 'link1-name',
        'link2', 'link2-name',
        'link3', 'link3-name', // Added
        'link4', 'link4-name', // Added
        'link5', 'link5-name', // Added
        'boxwidth' // Added
    ];

    const addSuggested = ['image_size', 'alt', 'abbreviation', 'bluebook', 'mathscinet', 'nlm',
        'peer-reviewed', 'ISSNlabel', 'link2', 'link2-name'];
    for (const paramName of addSuggested)
        templateData.param(paramName).suggested = true;

    /* eslint-disable no-multi-spaces, max-len */
    const defaultParameters = new Map([
        ['image',         '<!-- or |cover= -->'],
        ['former_name',   '<!-- or |former_names= -->'],
        ['abbreviation',  '<!-- ISO 4 abbreviation -->'],
        ['bluebook',      '<!-- For law journals only -->'],
        ['mathscinet',    '<!-- For the MathSciNet abbreviation IF different from ISO 4 abbreviation-->'],
        ['nlm',           '<!-- For the NLM abbreviation IF different from ISO 4 abbreviation-->'],
        ['discipline',    '<!-- or |subject= -->'],
        ['editor',        '<!-- or |editors= -->'],
        ['link2',         '<!-- up to |link5= -->'],
        ['link2-name',    '<!-- up to |link5-name= -->']
    ]);
    /* eslint-enable no-multi-spaces, max-len */
    for (const [key, value] of defaultParameters.entries())
        templateData.param(key).autovalue = value;

    // TODO move to actual TemplateData.
    templateData.params.set('RSS', new TemplateDataParam('RSS'));
    templateData.param('RSS').deprecated = true;
    templateData.params.set('atom', new TemplateDataParam('atom'));
    templateData.param('atom').deprecated = true;

    return templateData;
}

main();
