async function storeBookmark(url) { 
    chrome.storage.local.get(["bookmarks"]).then((value) => {
        let bookmarks = value.bookmarks
        bookmarks.push(url)
        chrome.storage.local.set({ bookmarks: bookmarks }).then(() => {});
    });
}

async function getStoreBookmarks() { 
    chrome.storage.local.get(["bookmarks"]).then((value) => {
        return value.bookmarks
    });
}

export function caspitalFirstLetter(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
}


export const CommunicationEnum = {
    NEW_DOC: "new-doc",
    NEW_QANDA: "new-qanda",
    CHAT_MESSAGE: "chat-message",
    DOC_IN_PROGRESS: "doc-in-progress",
    ADD_BOOKMARK: "add-bookmark",
    ASK_QUESTION: "ask-question",
    FETCH_QANDA: "fetch-qanda",
    ASK_QUESTION: "ask-question",
    DELETE_QANDA: "delete-qanda",
    PROGRESS_PERCENTAGE: "progress_percentage",
    FETCH_DOCUMENT: "fetch-document",
    FETCH_CHAT: "fetch-chat",
    CHAT_READY: "chat-ready",
    CHAT_NOT_READY: "chat-not-ready",
    ERROR: "error",
    SUGGESTED_QUESTIONS: 'suggested-questions',
};

/**
 * Converts plain URLs in text to HTML anchor tags
 * @param {string} text - Text that may contain URLs
 * @returns {string} Text with URLs converted to HTML links
 */
export function formatUrlsAsLinks(text) {
    if (!text) {
        return text;
    }

    // URL pattern: matches http:// or https:// URLs
    // Excludes common trailing punctuation that's not part of the URL
    const urlPattern = /(https?:\/\/[^\s<>"')]+)/gi;

    return text.replace(urlPattern, (url) => {
        // Clean up URL (remove trailing punctuation that might not be part of URL)
        const cleanUrl = url.replace(/[.,;:!?)]+$/, '');
        return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">${cleanUrl}</a>`;
    });
}

export function cleanUrl(url) {
    url = decodeURIComponent(url);
    // Define the regex
    const pageRegex = /(http.*:\/\/[a-zA-Z0-9:\/\.\-\@\%\_]*)/;

    // Match the regex against the URL
    const matches = url.match(pageRegex);

    // Get the first match
    let cleanUrl;
    if (matches) {
        cleanUrl = matches[0];
    } else {
        // If no match, use the URL as the page URL
        cleanUrl = url;
    }

    return cleanUrl;
}

/**
 * Check if URL appears to be an article page
 * @param {URL} urlObj - Parsed URL object
 * @returns {boolean} True if URL looks like an article
 */
function isArticlePage(urlObj) {
    const pathname = urlObj.pathname.toLowerCase();
    const searchParams = urlObj.searchParams;
    
    // Common article URL patterns
    const articlePatterns = [
        /\/article[s]?\/?/,
        /\/story\/?/,
        /\/post\/?/,
        /\/entry\/?/,
        /\/opinion\/?/,
        /\/news\/?/,
        /\/blog\/?/,
        /\/[0-9]{4}\/[0-9]{2}\/[0-9]{2}\//, // Date-based URLs
        /\/[a-z0-9-]+-[a-z0-9-]+-[a-z0-9-]+/i, // Slug-like patterns (3+ segments)
    ];
    
    // Check pathname patterns
    for (const pattern of articlePatterns) {
        if (pattern.test(pathname)) {
            return true;
        }
    }
    
    // Check query parameters that indicate articles
    const articleParams = ['article', 'story', 'post', 'id', 'slug'];
    for (const param of articleParams) {
        if (searchParams.has(param)) {
            return true;
        }
    }
    
    // Check if pathname has multiple segments (likely an article)
    const segments = pathname.split('/').filter(s => s.length > 0);
    if (segments.length >= 2) {
        // Check if it's not just a category page
        const categoryPages = ['category', 'tag', 'author', 'archive', 'search', 'page'];
        if (!categoryPages.some(cat => pathname.includes(`/${cat}/`))) {
            return true;
        }
    }
    
    return false;
}

/**
 * Detect problematic page types based on URL
 * @param {string} url - URL to analyze
 * @param {boolean} hasContent - Whether content will be available from extension injection
 * @returns {Object} Detection result with page type, issues, and warnings
 */
export function detectPageType(url, hasContent = true) {
    if (!url) {
        return {
            page_type: 'standard',
            issues: [],
            warnings: [],
            requires_js: false,
            has_paywall: false,
            requires_login: false,
            is_dynamic: false,
            is_article: false
        };
    }

    // Parse URL to get domain
    try {
        const urlObj = new URL(url);
        let domain = urlObj.hostname.toLowerCase();
        
        // Remove www. prefix for matching
        if (domain.startsWith('www.')) {
            domain = domain.substring(4);
        }

        // Check if it's an article page
        const isArticle = isArticlePage(urlObj);

        const detection = {
            page_type: 'standard',
            issues: [],
            warnings: [],
            requires_js: false,
            has_paywall: false,
            requires_login: false,
            is_dynamic: false,
            is_article: isArticle
        };

        // JavaScript-required domains
        const jsRequiredDomains = ['facebook.com', 'fb.com', 'instagram.com', 'linkedin.com'];
        for (const jsDomain of jsRequiredDomains) {
            if (domain.includes(jsDomain)) {
                detection.page_type = 'js_required';
                detection.requires_js = true;
                detection.warnings.push(`This site (${domain}) requires JavaScript to render content. Content extraction may fail or return placeholder text.`);
                detection.issues.push('javascript_required');
                break;
            }
        }

        // Paywall domains - but only warn if it's not an article OR if content won't be available
        const paywallDomains = ['nytimes.com', 'wsj.com', 'washingtonpost.com', 'medium.com'];
        for (const paywallDomain of paywallDomains) {
            if (domain.includes(paywallDomain)) {
                detection.has_paywall = true;
                
                // If it's an article page and we have content, don't show warning
                // The extension can extract content even from paywall sites if user is logged in
                if (isArticle && hasContent) {
                    // Don't add warning - extension will send content
                    detection.page_type = 'article_with_content';
                } else {
                    // Show warning only if not an article or content unavailable
                    detection.warnings.push(`This site (${domain}) may have paywall restrictions. ${isArticle ? 'If you\'re logged in, content extraction should work.' : 'Content extraction may be limited.'}`);
                    detection.issues.push('paywall');
                }
                break;
            }
        }

        // Login-required domains
        const loginRequiredDomains = ['yahoo.com', 'reddit.com'];
        for (const loginDomain of loginRequiredDomains) {
            if (domain.includes(loginDomain)) {
                detection.requires_login = true;
                // Only warn if not an article or no content
                if (!isArticle || !hasContent) {
                    detection.warnings.push(`This site (${domain}) may require login to access content.`);
                    detection.issues.push('login_required');
                }
                break;
            }
        }

        // Dynamic content domains
        const dynamicDomains = ['youtube.com', 'youtu.be', 'tiktok.com'];
        for (const dynamicDomain of dynamicDomains) {
            if (domain.includes(dynamicDomain)) {
                detection.is_dynamic = true;
                detection.warnings.push(`This site (${domain}) serves dynamic/video content that may not be extractable via static HTML.`);
                detection.issues.push('dynamic_content');
                break;
            }
        }

        return detection;
    } catch (error) {
        // If URL parsing fails, return standard detection
        console.warn('Failed to parse URL for detection:', error);
        return {
            page_type: 'standard',
            issues: [],
            warnings: [],
            requires_js: false,
            has_paywall: false,
            requires_login: false,
            is_dynamic: false,
            is_article: false
        };
    }
}
