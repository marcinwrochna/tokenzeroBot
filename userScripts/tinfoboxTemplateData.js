/**
 * @module tinfoboxTemplateData
 * Classes wrapping TemplateData.
 * Usage: see User:Tokenzero/infoboxJournal.js for how to load a module.
 *  import { TemplateData, TemplateDataParam } from '/w/index.php?title=User:Tokenzero/tinfoboxTemplateData.js&action=raw&ctype=text%2Fjavascript';
 *  (async function() {
 *      templateData = await m.TemplateData.fetch('Template:Infobox journal');
 *      console.log(templateData.param('title').deprecated);
 *      wikicode = templateData.build({title: 'Foo'});
 *      console.log(wikicode);
 *  })();
 * For documentation of TemplateData in general (not this wrapper module):
 * - https://www.mediawiki.org/wiki/Extension:TemplateData
 * - https://www.mediawiki.org/wiki/Help:TemplateData
 * - example JSON: https://en.wikipedia.org/w/api.php?action=templatedata&titles=Template:Infobox%20journal&format=jsonfm&formatversion=2&lang=en
 */

/** Configuration of a template parameter, see {@link TemplateData}. */
export class TemplateDataParam {
    /** @param {string} key */
    constructor(key) {
        /** @type {string} - The canonical name of the parameter. */
        this.key = key;
        /** @type {string} - A short human label like "Former name". */
        this.label = '';
        /** @type {string} */
        this.description = '';
        /**
         * @type {string}
         * One of: unknown/number/boolean/string (any text)/line (short label text)/
         *  date (in ISO format e.g. "2014-05-09" or "2014-05-09T16:01:12Z") /
         *  content (wikitext) / unbalanced-wikitext /
         *  wiki-page-name / wiki-file-name (without File:) /
         *  wiki-template-name / wiki-user-name (without User:)
         */
        this.type = 'unknown';
        /** @type {string} - Default value assumed if none is given. */
        this.default = null;
        /** @type {string} - Initially suggested value, often like '{{subst:CURRENTYEAR}}'. */
        this.autovalue = null;
        /** @type {string} */
        this.example = null;
        /** @type {boolean} */
        this.required = false;
        /** @type {boolean} */
        this.suggested = false;
        /**
         * @type {boolean}
         * Suggested, but not added as empty by default; situational.
         * This is tinfobox-specific. At most one of suggested/weaklySuggested should be true.
         */
        this.weaklySuggested = false;
        /** @type {(boolean|string)} - May be an instruction of what to use in place of it. */
        this.deprecated = false;
        /** @type {Array<string>} - Other names for the parameter. */
        this.aliases = [];
    }

    /**
     * Serialize to simple json object, called by JSON.stringify.
     *
     * @returns {object}
     */
    toJSON() {
        return {
            key: this.key,
            label: this.label,
            description: this.description,
            default: this.default,
            autovalue: this.autovalue,
            example: this.example,
            required: this.required,
            suggested: this.suggested,
            weaklySuggested: this.weaklySuggested,
            deprecated: this.deprecated,
            aliases: this.aliases
        };
    }

    /**
     * Deserialize from simple object returned by JSON.parse or MW API.
     * We assume mediawiki API json formatversion=2 with the lang param set.
     *
     * @param {object} jsonObject
     * @param {string} [key] - canonical key to identify the param, if not already in jsonObject.
     * @returns {TemplateDataParam}
     */
    static fromJSON(jsonObject, key) {
        console.assert(!jsonObject.inherits); // Inherits should be handled by API.
        const canonicalKey = jsonObject.key || key;
        const result = Object.assign(new TemplateDataParam(canonicalKey), jsonObject);
        result.aliases = result.aliases || [];
        return result;
    }
}

/**
 * Configuration of a template.
 * See https://www.mediawiki.org/wiki/Help:TemplateData#Description_and_parameters
 *  or https://www.mediawiki.org/wiki/Extension:TemplateData
 */
export class TemplateData {
    /** @param {object} jsonObject - from mediawiki API json formatversion=2 with lang= set. */
    constructor(jsonObject) {
        /** @type {string} */
        this.title = jsonObject.title; // Added by API.
        /** @type {boolean} */
        this.notemplatedata = jsonObject.notemplatedata; // Added by API.
        /** @type {string} */
        this.description = jsonObject.description;
        /**
         * @type {string}
         * 'inline', 'block', or a string like '\n{{_\n|_______________ = _\n}}\n'.
         */
        this.format = jsonObject.format;
        /**
         * @type {Object<string, Object<string,(string|Array<string>|Array<Array<string>>)>>}
         * Maps names of consumers to maps from consumer-parameters to our-parameters.
         */
        this.maps = jsonObject.maps;
        /**
         * @type {Array<{label: string, params: Array<string>}>}
         * Sets (groups) of parameters. A parameter may be in multiple sets.
         * Labels are short, 20-ish characters.
         */
        this.sets = jsonObject.sets;
        /** @type {Map<string, TemplateDataParam>} */
        this.params = new Map();
        for (const [k, v] of Object.entries(jsonObject.params))
            this.params.set(k, TemplateDataParam.fromJSON(v, k));
        /** @type {!Array<string>} */
        this.paramOrder = jsonObject.paramOrder;
        // Should always be filled by API but apparently it's not.
        if (!this.paramOrder || !this.paramOrder.length)
            this.paramOrder = Object.keys(jsonObject.params);

        /** @private {Map<string, string>} - map from alias key to canonical key. */
        this.canonicalMap_ = new Map();
        for (const [canonicalKey, param] of this.params.entries()) {
            for (const aliasKey of param.aliases) {
                console.assert(!this.canonicalMap_.get(aliasKey));
                this.canonicalMap_.set(aliasKey, canonicalKey);
            }
        }
    }

    /**
     * Serialize to simple json object, called by JSON.stringify.
     *
     * @returns {object}
     */
    toJSON() {
        // Convert Map to Object (avoid importing polyfills just for three lines).
        const jsonParams = {};
        for (const [key, value] of this.params.entries())
            jsonParams[key] = value;
        return {
            title: this.title,
            notemplatedata: this.notemplatedata,
            description: this.description,
            format: this.format,
            maps: this.maps,
            sets: this.sets,
            params: jsonParams,
            paramOrder: this.paramOrder
        };
    }

    /**
     * Deserialize from simple object returned by JSON.parse or MW API.
     * We assume mediawiki API json formatversion=2 with the lang param set.
     *
     * @param {object} jsonObject
     * @returns {TemplateData}
     */
    static fromJSON(jsonObject) {
        return new TemplateData(jsonObject);
    }

    /**
     * Fetch given template's TemplateData via API.
     *
     * @param {string} name
     * @returns {Promise<TemplateData>}
     */
    static async fetch(name) {
        if (!name.startsWith('Template'))
            name = 'Template:' + name;
        const r = await (new mw.Api()).get({
            action: 'templatedata',
            titles: name,
            redirects: true,
            lang: mw.config.get('wgUserLanguage'),
            formatversion: 2
        });
        return new TemplateData(Object.values(r.pages)[0]);
    }

    /**
     * Map an alias key to the canonical parameter name.
     *
     * @param {string|number} key
     * @returns {string}
     */
    toCanonicalKey(key) {
        return this.canonicalMap_.get(key.toString().trim()) || key.toString().trim();
    }

    /**
     * Give TemplateDataParam for given canonical key or return default.
     *
     * @param {string} canonicalKey
     * @returns {TemplateDataParam}
     */
    param(canonicalKey) {
        // Don't save default param, because we check and report when a param has no TemplateData.
        // Freeze to avoid mistaken attempts to make a new param starting from default values.
        if (!this.params.has(canonicalKey))
            return Object.freeze(new TemplateDataParam(canonicalKey));
        return this.params.get(canonicalKey);
    }

    /** Reorder the keys of a Map according to this.paramOrder.
     * Keys not in this.paramOrder are then appended lexicographically.
     *
     * @param {Map<string, T>} map
     * @returns {Map<string, T>}
     * @template T
     */
    reorder(map) {
        const result = new Map();
        // First add keys in paramOrder.
        for (const key of this.paramOrder) {
            if (map.has(key))
                result.set(key, map.get(key));
        }
        // Then take remaining keys, sort, and add.
        const toBeSorted = [];
        for (const [key, value] of map.entries()) {
            if (!this.paramOrder.includes(key))
                toBeSorted.push([key, value]);
        }
        for (const [key, value] of toBeSorted.sort())
            result.set(key, value);

        return result;
    }

    /**
     * Format given key-value map as wikicode of the template.
     *
     * @param {Map<string, [(number|string), string]>} map - from canonicalKey to final key, value.
     * @param {string=} templateName - alias template name to use (defaults to this.title).
     * @param {boolean=} doReorder - whether to apply this.reorder(map); defaults to true.
     * @returns {string} wikicode, currently from '{{' to '}}' inclusive, no final endline.
     */
    build(map, templateName, doReorder) {
        // TODO Use this.format; make it easy to handle pre and post newlines.
        // As in https://gerrit.wikimedia.org/r/plugins/gitiles/mediawiki/extensions/TemplateWizard/+/master/resources/ext.TemplateWizard.TemplateFormatter.js
        if (doReorder == null)
            doReorder = true;
        if (doReorder)
            map = this.reorder(map);
        if (!templateName)
            templateName = this.title;
        let result = '{{' + templateName.trim() + '\n';
        for (let [_canonicalKey, [key, value]] of map.entries()) {
            if (typeof key === 'string') {
                key = key.trim();
            } else if (typeof key === 'number') {
                key = key.toString();
            } else {
                console.log(`Error: unexpected key type "${typeof key}"`);
                continue;
            }
            if (typeof value === 'string')
                value = value.trim();
            else if (!value)
                value = '';
            result += '| ' + key.padEnd(14) + '= ' + value + '\n';
        }
        result += '}}';
        return result;
    }
}
