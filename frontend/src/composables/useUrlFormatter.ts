/**
 * Composable for formatting URLs in text to HTML links
 */

/**
 * Converts plain URLs in text to HTML anchor tags
 * @param text - Text that may contain URLs
 * @returns Text with URLs converted to HTML links
 */
export function formatUrlsAsLinks(text: string): string {
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

/**
 * Composable function for URL formatting
 * Can be extended in the future with additional formatting options
 */
export function useUrlFormatter() {
  return {
    formatUrlsAsLinks,
  };
}

