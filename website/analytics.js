(function () {
    "use strict";
    // Replace with your real GA4 property ID to enable event delivery.
    window.ENXROSS_GA4_ID = window.ENXROSS_GA4_ID || "G-XXXXXXXXXX";

    const ATTR_KEYS = [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "ref"
    ];

    const FIRST_TOUCH_KEY = "enxross_first_touch";
    const LAST_TOUCH_KEY = "enxross_last_touch";
    const LANDING_PAGE_KEY = "enxross_landing_page";

    function readStorage(key) {
        try {
            return localStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }

    function writeStorage(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (error) {
            // Storage can fail in strict privacy contexts.
        }
    }

    function safeParse(value) {
        if (!value) return null;
        try {
            return JSON.parse(value);
        } catch (error) {
            return null;
        }
    }

    function initGa4() {
        const measurementId = (window.ENXROSS_GA4_ID || readStorage("enxross_ga4_id") || "").trim();
        if (!measurementId || measurementId === "G-XXXXXXXXXX") {
            return;
        }

        if (window.gtag) {
            return;
        }

        const script = document.createElement("script");
        script.async = true;
        script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(measurementId);
        document.head.appendChild(script);

        window.dataLayer = window.dataLayer || [];
        window.gtag = function () {
            window.dataLayer.push(arguments);
        };
        window.gtag("js", new Date());
        window.gtag("config", measurementId, { send_page_view: true });
    }

    function readAttributionFromUrl() {
        const query = new URLSearchParams(window.location.search);
        const payload = {};

        ATTR_KEYS.forEach((key) => {
            const value = query.get(key);
            if (value) {
                payload[key] = value;
            }
        });

        return payload;
    }

    function persistAttribution() {
        const existingFirst = safeParse(readStorage(FIRST_TOUCH_KEY));
        const existingLanding = readStorage(LANDING_PAGE_KEY);
        const queryAttribution = readAttributionFromUrl();
        const hasUtm = Object.keys(queryAttribution).length > 0;

        if (!existingLanding) {
            writeStorage(LANDING_PAGE_KEY, window.location.href);
        }

        if (hasUtm) {
            const payload = {
                ...queryAttribution,
                timestamp_iso: new Date().toISOString(),
                page_path: window.location.pathname
            };

            writeStorage(LAST_TOUCH_KEY, JSON.stringify(payload));
            if (!existingFirst) {
                writeStorage(FIRST_TOUCH_KEY, JSON.stringify(payload));
            }
            return;
        }

        if (!existingFirst) {
            const fallback = {
                source: document.referrer ? "referrer" : "direct",
                referrer: document.referrer || "",
                timestamp_iso: new Date().toISOString(),
                page_path: window.location.pathname
            };
            writeStorage(FIRST_TOUCH_KEY, JSON.stringify(fallback));
            writeStorage(LAST_TOUCH_KEY, JSON.stringify(fallback));
        }
    }

    function getStoredAttribution() {
        return {
            first_touch: readStorage(FIRST_TOUCH_KEY) || "",
            last_touch: readStorage(LAST_TOUCH_KEY) || "",
            landing_page: readStorage(LANDING_PAGE_KEY) || window.location.href
        };
    }

    function fillFormAttribution(form) {
        const attribution = getStoredAttribution();

        const firstInput = form.querySelector('[data-attribution="first_touch"]');
        if (firstInput) {
            firstInput.value = attribution.first_touch;
        }

        const lastInput = form.querySelector('[data-attribution="last_touch"]');
        if (lastInput) {
            lastInput.value = attribution.last_touch;
        }

        const landingInput = form.querySelector('[data-attribution="landing_page"]');
        if (landingInput) {
            landingInput.value = attribution.landing_page;
        }
    }

    window.enxrossTrack = function (eventName, params) {
        if (!window.gtag) return;
        const payload = Object.assign({ transport_type: "beacon" }, params || {});
        window.gtag("event", eventName, payload);
    };

    function trackDiscordLinks() {
        const links = document.querySelectorAll("a[href]");
        links.forEach((link) => {
            const href = link.getAttribute("href") || "";
            const isDiscordLink = href.includes("join-discord.html") || href.includes("discord.gg/");
            if (!isDiscordLink) return;

            link.addEventListener("click", function () {
                let source = link.getAttribute("data-source") || "unknown";
                if (href.includes("join-discord.html")) {
                    const queryString = href.split("?")[1] || "";
                    const params = new URLSearchParams(queryString);
                    source = params.get("src") || source;
                }

                window.enxrossTrack("discord_click", {
                    source: source,
                    page_path: window.location.pathname,
                    link_text: (link.textContent || "discord").trim().slice(0, 64)
                });
            });
        });
    }

    function trackForms() {
        const forms = document.querySelectorAll("form[data-track-form]");
        forms.forEach((form) => {
            fillFormAttribution(form);
            form.addEventListener("submit", function () {
                fillFormAttribution(form);
                window.enxrossTrack(form.getAttribute("data-track-form"), {
                    page_path: window.location.pathname,
                    form_name: form.getAttribute("name") || "unknown"
                });
            });
        });
    }

    function trackCustomClickElements() {
        const clickables = document.querySelectorAll("[data-track-event]");
        clickables.forEach((node) => {
            node.addEventListener("click", function () {
                window.enxrossTrack(node.getAttribute("data-track-event"), {
                    page_path: window.location.pathname,
                    label: node.getAttribute("data-track-label") || ""
                });
            });
        });
    }

    initGa4();
    persistAttribution();
    trackDiscordLinks();
    trackForms();
    trackCustomClickElements();
})();
