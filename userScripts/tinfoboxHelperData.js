/**
 * @module tinfoboxHelperData
 * Helper structures for infoboxJournal.js, storing info about parameter choices, messages, etc.
 */
import * as util from './tinfoboxUtil.js';
import { TemplateData, TemplateDataParam } from './tinfoboxTemplateData.js';

/** Structure for parameter values and choices. */
export class ParamChoice {
    /**
     * @param {object} templateData
     */
    constructor(templateData) {
        /**
         * @constant
         * @type {TemplateDataParam}
         * Note this is also included in TemplateChoice.templateData (possibly as a deep copy).
         */
        this.templateData = templateData;
        /** @type {?string} */
        this.originalKey = null;
        /** @type {?string} */
        this.originalValue = null;
        /** @type {?string} */
        this.proposedValue = null;
        /** @type {boolean} */
        this.preferOriginal = true;
        /** @type {Array<{type: string, message: string}>} */
        this.messages = [];
    }

    /**
     * Serialize to simple object to be passed do JSON.stringify.
     *
     * @returns {object}
     */
    toJSON() {
        return {
            templateData: this.templateData, // Recursively toJSON'ed by JSON.stringify.
            originalKey: this.originalKey,
            originalValue: this.originalValue,
            proposedValue: this.proposedValue,
            preferOriginal: this.preferOriginal,
            messages: this.messages
        };
    }

    /**
     * Deserialize from simple object returned by JSON.parse.
     *
     * @param {object} jsonObject
     * @returns {ParamChoice}
     */
    static fromJSON(jsonObject) {
        const templateData = TemplateDataParam.fromJSON(jsonObject.templateData);
        delete jsonObject.templateData;
        return Object.assign(new ParamChoice(templateData), jsonObject);
    }

    /**
     * Return whether proposed value is empty or equal to original, default or autovalue.
     *
     * @returns {boolean}
     */
    isProposedValueTrivial() {
        return (
            (!this.proposedValue) ||
            (this.proposedValue === this.originalValue) ||
            (this.proposedValue === this.templateData.default) ||
            (this.proposedValue === this.templateData.autovalue) ||
            (!this.proposedValue && !this.templateData.autovalue)
        );
    }
}


/** Data to preserve after redirecting: ParamChoice-s and messages. */
export class TemplateChoice {
    /** @param {TemplateData} templateData */
    constructor(templateData) {
        /**
         * @constant
         * @type {TemplateData}
         * Note that templateData for params are also included in ParamChoices,
         * possibly as a deep copy.
         */
        this.templateData = templateData;
        /** @type {Map<string, ParamChoice>} from canonicalKey to its ParamChoice. */
        this.paramChoices = new Map();
        /** @type {Array<{type: string, message: string}>} messages about this template instance. */
        this.messages = [];
    }

    /**
     * Get or create ParamChoice for given canonicalKey.
     *
     * @param {string} canonicalKey
     * @returns {ParamChoice}
     */
    param(canonicalKey) {
        if (!this.paramChoices.has(canonicalKey)) {
            const paramChoice = new ParamChoice(this.templateData.param(canonicalKey));
            this.paramChoices.set(canonicalKey, paramChoice);
        }
        return this.paramChoices.get(canonicalKey);
    }


    /**
     * Serialize to object to be passed do JSON.stringify.
     *
     * @returns {object}
     */
    toJSON() {
        // JSON.stringify will recursively call .toJSON() in each entry.
        return {
            templateData: this.templateData,
            paramChoices: util.objectFromEntries(this.paramChoices.entries()),
            messages: this.messages
        };
    }

    /**
     * Deserialize from object returned by JSON.parse.
     *
     * @param {object} jsonObject
     * @returns {TemplateChoice}
     */
    static fromJSON(jsonObject) {
        const templateData = TemplateData.fromJSON(jsonObject.templateData);
        const result = new TemplateChoice(templateData);
        result.paramChoices = new Map(Object.entries(jsonObject.paramChoices).map(
            ([key, value]) => [key, ParamChoice.fromJSON(value)]
        ));
        result.messages = jsonObject.messages;
        return result;
    }

    /**
     * Build table listing parameters with their choices and messages.
     *
     * @returns {JQuery<HTMLElement>|''}
     */
    buildParamTable() {
        const changedList = [];
        const proposedList = [];
        const otherList = [];
        const choices = this.templateData.reorder(this.paramChoices).entries();
        for (const [canonicalKey, pc] of choices) {
            if (pc.proposedValue === pc.originalValue && !pc.messages.length) {
                if (pc.proposedValue && pc.proposedValue.replace(/<!--[^>]*-->/g, '')) {
                    console.log(
                        `Param ${canonicalKey} guessed correctly as "${pc.proposedValue}".`);
                }
                continue;
            }
            if (pc.originalValue === pc.proposedValue)
                pc.preferOriginal = true;

            const row = $('<tr>');
            row.append($(`<td>${pc.originalKey || canonicalKey}=</td>`));
            if (typeof pc.originalValue === 'string')
                row.append($(`<td>${util.escapeHTML(pc.originalValue)}</td>`));
            else
                row.append($('<td>(absent)</td>').addClass('absent'));
            if (pc.preferOriginal)
                row.children().last().addClass('selected');
            if (typeof pc.proposedValue === 'string')
                row.append($(`<td>${util.escapeHTML(pc.proposedValue)}</td>`));
            else if (!pc.preferOriginal)
                row.append($('<td>(deleted)</td>').addClass('absent'));
            else
                row.append($('<td></td>').addClass('absent'));
            if (!pc.preferOriginal)
                row.children().last().addClass('selected');
            if (!pc.isProposedValueTrivial())
                row.children().last().addClass('nontrivial');
            row.append($('<td>').append(HelperData.buildMessagesWidget(pc.messages)));

            if (!pc.preferOriginal)
                changedList.push(row);
            else if (!pc.isProposedValueTrivial() ||
                     (pc.templateData.suggested && pc.originalValue === null))
                proposedList.push(row);
            else if (pc.messages.length)
                otherList.push(row);
            // Else: we prefer original, proposed value is trivial and not suggested as addition,
            // and there are no messages, so we just don't show the param.
        }
        let rows = [];
        rows.push($(`<tr>
            <th></th><th>current value</th><th>automatic</th><th></th>
        </tr>`));
        if (changedList.length) {
            rows.push($('<tr><th colspan="3">Changed params</th></tr>'));
            rows = rows.concat(changedList);
        } else {
            rows.push($('<tr><td colspan="3">No parameters were changed.</td></tr>'));
        }
        if (proposedList.length) {
            rows.push($('<tr><th colspan="3">Proposed changes</th></tr>'));
            rows = rows.concat(proposedList);
        }
        if (otherList.length) {
            rows.push($('<tr><th colspan="3">Other warnings</th></tr>'));
            rows = rows.concat(otherList);
        }
        // if (changedList.length || proposedList.length || otherList.length)
        return $('<table>').append(rows);
        // else return '';
    }
}

/**
 * Data to pass after redirect, including TemplateChoice-s.
 */
export class HelperData {
    /** Constructor. */
    constructor() {
        /** @type {Array<TemplateChoice>} */
        this.templateChoices = [];
        /** @type {Array<{type: string, message: string}>} global messages. */
        this.messages = [];
    }

    /**
     * Serialize to JSON string.
     *
     * @returns {string}
     */
    toJSONString() {
        return JSON.stringify({
            templateChoices: this.templateChoices,
            messages: this.messages
        });
    }

    /**
     * Deserialize from JSON string to new HelperData object.
     *
     * @param {string} json
     * @returns {HelperData}
     */
    static fromJSONString(json) {
        const result = Object.assign(new HelperData(), JSON.parse(json));
        result.templateChoices = result.templateChoices.map(
            (x) => TemplateChoice.fromJSON(x)
        );
        return result;
    }

    /**
     * Create jQuery object showing a list of messages.
     *
     * @param {Array<{type: string, message: string}>} messages
     * @returns {JQuery|''}
     */
    static buildMessagesWidget(messages) {
        if (!messages || !messages.length)
            return '';
        const result = $('<ul></ul>');
        for (const m of messages) {
            const entry = $('<li>');
            entry.text(m.message);
            entry.prepend(`<b>${m.type}</b>: `);
            result.append(entry);
        }
        return result;
    }

    /**
     * Build a box describing helperData (prefilled parameters and such).
     *
     * @returns {JQuery<HTMLElement>}
     */
    buildWidget() {
        const widget = $(`
            <div class="ext-tinfobox-helper">
                <h2>infoboxJournal.js</h2>
            </div>
        `);
        let globalMessages = this.messages;
        if (this.templateChoices.length === 1)
            globalMessages = globalMessages.concat(this.templateChoices[0].messages);
        widget.append(HelperData.buildMessagesWidget(globalMessages));

        const many = (this.templateChoices.length > 1);
        for (const [tcIndex, tc] of this.templateChoices.entries()) {
            if (many) {
                widget.append($(`<h3>Template #${tcIndex + 1}</h3>`));
                widget.append(HelperData.buildMessagesWidget(tc.messages));
            }
            widget.append(tc.buildParamTable());
        }

        return widget;
    }
}
