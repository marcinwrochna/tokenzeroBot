/**
 * infoboxJournal.js
 * One-click adds or normalizes existing infobox-journal templates.
 */
// <nowiki>
(async function($) {
    'use strict';
    // Only enable in Main and Draft namespaces, and on User:*sandbox* pages.
    if (!['', 'Draft', 'User'].includes(mw.config.get('wgCanonicalNamespace')))
        return;
    if (mw.config.get('wgCanonicalNamespace') === 'User' &&
        !mw.config.get('wgTitle').includes('andbox'))
        return;

    /**
     * Get full URL to script/stylesheet/etc. (to raw file).
     *
     * @param {string} pageName
     * @param {object} [params]
     * @returns {string}
     */
    function getRawUrl(pageName, params) {
        params = params || {};
        params.action = 'raw';
        params.ctype = params.ctype || pageName.includes('.css') ? 'text/css' : 'text/javascript';
        if (pageName.startsWith('User:Tokenzero/'))
            return 'http://localhost:8000/' + pageName.slice('User:Tokenzero/'.length) + '?' + $.param(params);
        return mw.util.getUrl(pageName, params);
    }

    /**
     * Asynchronously load a javascript ES6 module from [[pageName]].
     * The script is loaded as a new <script type="module"> element,
     * so there's no way to access its scope.
     * This returns a Promise resolved after the script is loaded and executed.
     * In contrast, mw.loader.load and $.getScript do not support ES6 modules.
     *
     * @param {string} pageName
     * @returns {Promise}
     */
    async function loadModule(pageName) {
        return new Promise(function(resolve, reject) {
            const script = document.createElement('script');
            script.type = 'module';
            script.onload = function() { resolve(script); };
            script.onerror = function() { reject(script); };
            // src must be set _after_ everything else.
            script.src = pageName;
            document.head.appendChild(script);
        });
    }

    // Load ResourceLoader modules.
    await mw.loader.using(['mediawiki.util', 'mediawiki.api',
        'oojs-ui-core', 'oojs-ui-widgets', 'oojs-ui-windows']);

    if (!window.extraJs)
        await mw.loader.getScript(getRawUrl('User:Evad37/extra.js'));

    mw.loader.load(getRawUrl('User:Tokenzero/tinfobox.css'), 'text/css');

    loadModule(getRawUrl('User:Tokenzero/tinfoboxJournal.js'));
})($);
// </nowiki>
