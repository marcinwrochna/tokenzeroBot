class ExtraJs {
    static Template = class {
        static ExtraJsParam = class {
            name: string;
            value: string;
            wikitext: string;
        };
        constructor (wikitext: string): ExtraJsTemplate;    
        name: string;
        wikitext: string;
        parameters: Array<ExtraJsParam>;
        setName(name: string);
        getParam(paramName: string|number): string;
        addParam(name: string|number, val: string, wikitext: string);
    };
    // We use it a static type but it's actually exposed as an instance property.
    Template = Template;
    parseTemplates(wikitext:string, recursive: boolean): Array<ExtraJs.Template>;
}

interface Window {
    extraJs: ExtraJs;
    tinfobox: { util?: TinfoboxUtil; };
}

interface CallbackWithRequire {
    /** Get the exported value of a module (require(moduleName) returns module.exports). */
    (require: (string) => object);
}

interface NotifyOptions {
    autoHide?: boolean = true;
    /** Here 'short' means 5s, 'long' means 30s. */
    autoHideSeconds?: number | 'short' | 'long' = 'short';
    /** When a notification is tagged only one message
     *   with that tag will be displayed. Trying to display a new notification
     *   with the same tag as one already being displayed will cause the other
     *   notification to be closed and this new notification to open up inside
     *   the same place as the previous notification.
     */
    tag?: string;
    title?: string;
    /** Used for styling. Examples: 'info', 'warn', 'error'. */
    type?: string;
    /**
     *   A boolean indicating if the autoHide timeout should be based on
     *   time the page was visible to user. Or if it should use wall clock time.
     */
    visibleTimeout?: boolean = true;
}

interface MwMap {
    exists(selection: string|Array<string>): boolean;
    /** If selection is an array, return object of key/values;
     *  If no selection is given, return object of all key/values. */
    get<T>(selection?: string|Array<string> , fallback?: T): T;
    set(selection: string|Object<string,any>, value?: any): boolean;
}

interface Mw {
    Api: {
        new (options?: Object<string,any>);
    };    
    config: MwMap;
    loader: {
        /** Asynchronously load a script. */
        getScript(url: string): Promise;
        /** Asynchronously load a script or css. No Promise returned, no way to wait on it! */
        load(modules: string|Array<string>, type: string = 'text/javascript');
        /**
         * Execute a function as soon as one or more required modules are ready.
         *
         * Example of inline dependency on OOjs:
         *     mw.loader.using( 'oojs', function () {
         *         OO.compare( [ 1 ], [ 1 ] );
         *     } );
         *
         * Example of inline dependency obtained via `require()`:
         *     mw.loader.using( [ 'mediawiki.util' ], function ( require ) {
         *         var util = require( 'mediawiki.util' );
         *     } );
         * 
         * Or equivalently:
         *     require = await mw.loader.using( [ 'mediawiki.util' ]);
         *     var util = require( 'mediawiki.util' );
         * 
         * @param {string|Array<string>} dependencies Module name or array of modules names the
         *  callback depends on to be ready before executing
         * @param {CallbackWithRequire} [ready] Callback to execute when all dependencies are ready
         * @param {Function} [error] Callback to execute if one or more dependencies failed
         * @return {jQuery.Promise} With a `require` function
         */        
        using(dependencies: (string|Array<string>), ready?: CallbackWithRequire, error?: Function);
    };
    notify(message: string|jQuery, options: NotifyOptions): Promise<mw.Notification>;
    Notification: {
        close();
    };
    user: {
        tokens: MwMap;
    };
    util: {
        /**
         * Get the link to a page name (relative to `wgServer`),
         *
         * @param {string|null} [pageName] Page name, defaults to wgPageName.
         */
        getUrl(pageName?: string, params?: Object<string,string>): string;
        /** Returns CSSStyleSheet, whose .ownerNode is the created <style> element. */
        addCSS(text: string): object;
        addPortletLink(portletId: string, href: string, text: string,
            id?: string, tooltip?: string, accesskey?: string, nextnode?: string): HTMLElement|null;
        /**
         * Escape string for safe inclusion in regular expression.
         * The following characters are escaped:
         *     \ { } ( ) | . ? * + - ^ $ [ ]
         */            
        escapeRegExp(str: string): string;
    };

}

declare var mw: Mw;