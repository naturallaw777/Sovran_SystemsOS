/******/ (() => { // webpackBootstrap
/******/ 	"use strict";
var __webpack_exports__ = {};

;// CONCATENATED MODULE: ./src/autofill/enums/autofill-port.enums.ts
const AutofillPort = {
    InjectedScript: "autofill-injected-script-port",
};


;// CONCATENATED MODULE: ./src/autofill/utils/index.ts
var __awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};

/**
 * Generates a random string of characters that formatted as a custom element name.
 */
function generateRandomCustomElementName() {
    const generateRandomChars = (length) => {
        const chars = "abcdefghijklmnopqrstuvwxyz";
        const randomChars = [];
        const randomBytes = new Uint8Array(length);
        globalThis.crypto.getRandomValues(randomBytes);
        for (let byteIndex = 0; byteIndex < randomBytes.length; byteIndex++) {
            const byte = randomBytes[byteIndex];
            randomChars.push(chars[byte % chars.length]);
        }
        return randomChars.join("");
    };
    const length = Math.floor(Math.random() * 5) + 8; // Between 8 and 12 characters
    const numHyphens = Math.min(Math.max(Math.floor(Math.random() * 4), 1), length - 1); // At least 1, maximum of 3 hyphens
    const hyphenIndices = [];
    while (hyphenIndices.length < numHyphens) {
        const index = Math.floor(Math.random() * (length - 1)) + 1;
        if (!hyphenIndices.includes(index)) {
            hyphenIndices.push(index);
        }
    }
    hyphenIndices.sort((a, b) => a - b);
    let randomString = "";
    let prevIndex = 0;
    for (let index = 0; index < hyphenIndices.length; index++) {
        const hyphenIndex = hyphenIndices[index];
        randomString = randomString + generateRandomChars(hyphenIndex - prevIndex) + "-";
        prevIndex = hyphenIndex;
    }
    randomString += generateRandomChars(length - prevIndex);
    return randomString;
}
/**
 * Builds a DOM element from an SVG string.
 *
 * @param svgString - The SVG string to build the DOM element from.
 * @param ariaHidden - Determines whether the SVG should be hidden from screen readers.
 */
function buildSvgDomElement(svgString, ariaHidden = true) {
    const domParser = new DOMParser();
    const svgDom = domParser.parseFromString(svgString, "image/svg+xml");
    const domElement = svgDom.documentElement;
    domElement.setAttribute("aria-hidden", `${ariaHidden}`);
    return domElement;
}
/**
 * Sends a message to the extension.
 *
 * @param command - The command to send.
 * @param options - The options to send with the command.
 */
function sendExtensionMessage(command, options = {}) {
    return __awaiter(this, void 0, void 0, function* () {
        return new Promise((resolve) => {
            chrome.runtime.sendMessage(Object.assign({ command }, options), (response) => {
                if (chrome.runtime.lastError) {
                    return;
                }
                resolve(response);
            });
        });
    });
}
/**
 * Sets CSS styles on an element.
 *
 * @param element - The element to set the styles on.
 * @param styles - The styles to set on the element.
 * @param priority - Determines whether the styles should be set as important.
 */
function setElementStyles(element, styles, priority) {
    if (!element || !styles || !Object.keys(styles).length) {
        return;
    }
    for (const styleProperty in styles) {
        element.style.setProperty(styleProperty.replace(/([a-z])([A-Z])/g, "$1-$2"), // Convert camelCase to kebab-case
        styles[styleProperty], priority ? "important" : undefined);
    }
}
/**
 * Get data from local storage based on the keys provided.
 *
 * @param keys - String or array of strings of keys to get from local storage
 */
function getFromLocalStorage(keys) {
    return __awaiter(this, void 0, void 0, function* () {
        return new Promise((resolve) => {
            chrome.storage.local.get(keys, (storage) => resolve(storage));
        });
    });
}
/**
 * Sets up a long-lived connection with the extension background
 * and triggers an onDisconnect event if the extension context
 * is invalidated.
 *
 * @param callback - Callback function to run when the extension disconnects
 */
function setupExtensionDisconnectAction(callback) {
    const port = chrome.runtime.connect({ name: AutofillPort.InjectedScript });
    const onDisconnectCallback = (disconnectedPort) => {
        callback(disconnectedPort);
        port.onDisconnect.removeListener(onDisconnectCallback);
    };
    port.onDisconnect.addListener(onDisconnectCallback);
}
/**
 * Handles setup of the extension disconnect action for the autofill init class
 * in both instances where the overlay might or might not be initialized.
 *
 * @param windowContext - The global window context
 */
function setupAutofillInitDisconnectAction(windowContext) {
    if (!windowContext.bitwardenAutofillInit) {
        return;
    }
    const onDisconnectCallback = () => {
        windowContext.bitwardenAutofillInit.destroy();
        delete windowContext.bitwardenAutofillInit;
    };
    setupExtensionDisconnectAction(onDisconnectCallback);
}


;// CONCATENATED MODULE: ./src/autofill/content/autofiller.ts
var autofiller_awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadAutofiller);
}
else {
    loadAutofiller();
}
function loadAutofiller() {
    let pageHref = null;
    let filledThisHref = false;
    let delayFillTimeout;
    let doFillInterval;
    const handleExtensionDisconnect = () => {
        clearDoFillInterval();
        clearDelayFillTimeout();
    };
    const handleExtensionMessage = (message) => {
        if (message.command === "fillForm" && pageHref === message.url) {
            filledThisHref = true;
        }
    };
    setupExtensionEventListeners();
    triggerUserFillOnLoad();
    function triggerUserFillOnLoad() {
        var _a, _b;
        return autofiller_awaiter(this, void 0, void 0, function* () {
            const activeUserIdKey = "activeUserId";
            const userKeyStorage = yield getFromLocalStorage(activeUserIdKey);
            const activeUserId = userKeyStorage[activeUserIdKey];
            const activeUserStorage = yield getFromLocalStorage(activeUserId);
            if (((_b = (_a = activeUserStorage === null || activeUserStorage === void 0 ? void 0 : activeUserStorage[activeUserId]) === null || _a === void 0 ? void 0 : _a.settings) === null || _b === void 0 ? void 0 : _b.enableAutoFillOnPageLoad) === true) {
                clearDoFillInterval();
                doFillInterval = setInterval(() => doFillIfNeeded(), 500);
            }
        });
    }
    function doFillIfNeeded(force = false) {
        if (force || pageHref !== window.location.href) {
            if (!force) {
                // Some websites are slow and rendering all page content. Try to fill again later
                // if we haven't already.
                filledThisHref = false;
                clearDelayFillTimeout();
                delayFillTimeout = window.setTimeout(() => {
                    if (!filledThisHref) {
                        doFillIfNeeded(true);
                    }
                }, 1500);
            }
            pageHref = window.location.href;
            const msg = {
                command: "bgCollectPageDetails",
                sender: "autofiller",
            };
            chrome.runtime.sendMessage(msg);
        }
    }
    function clearDoFillInterval() {
        if (doFillInterval) {
            window.clearInterval(doFillInterval);
        }
    }
    function clearDelayFillTimeout() {
        if (delayFillTimeout) {
            window.clearTimeout(delayFillTimeout);
        }
    }
    function setupExtensionEventListeners() {
        setupExtensionDisconnectAction(handleExtensionDisconnect);
        chrome.runtime.onMessage.addListener(handleExtensionMessage);
    }
}

/******/ })()
;