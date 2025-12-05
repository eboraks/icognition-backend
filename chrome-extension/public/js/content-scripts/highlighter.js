// Check if script is already loaded
if (typeof window.iCognitionHighlighter === 'undefined') {
    console.log('iCognition Highlighter: Initializing...');
    
    // Create a namespace for our highlighter
    window.iCognitionHighlighter = {
        currentHighlights: [],
        
        removeExistingHighlights() {
            console.debug('Removing existing highlights:', this.currentHighlights.length);
            // First remove all highlights we've tracked
            this.currentHighlights.forEach(highlight => {
                const parent = highlight.parentNode;
                if (parent) {
                    parent.replaceChild(document.createTextNode(highlight.textContent), highlight);
                    parent.normalize();
                }
            });
            
            // Also find and remove any of our highlights that might have been missed
            const allHighlights = document.querySelectorAll('mark.icognition-highlight');
            allHighlights.forEach(highlight => {
                const parent = highlight.parentNode;
                if (parent) {
                    parent.replaceChild(document.createTextNode(highlight.textContent), highlight);
                    parent.normalize();
                }
            });
            
            this.currentHighlights = [];
        },

        getTextNodes() {
            const textNodes = [];
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: function(node) {
                        if (!node.textContent.trim() || 
                            node.parentElement.tagName === 'SCRIPT' || 
                            node.parentElement.tagName === 'STYLE' ||
                            node.parentElement.style.display === 'none' ||
                            node.parentElement.style.visibility === 'hidden') {
                            return NodeFilter.FILTER_REJECT;
                        }
                        return NodeFilter.FILTER_ACCEPT;
                    }
                },
                false
            );

            let node;
            while (node = walker.nextNode()) {
                textNodes.push(node);
            }
            return textNodes;
        },

        highlightNode(node, start, end) {
            const range = document.createRange();
            range.setStart(node, start);
            range.setEnd(node, end);
            
            const highlight = document.createElement('mark');
            highlight.className = 'icognition-highlight';
            highlight.style.backgroundColor = '#ffeb3b';
            highlight.style.color = 'black';
            highlight.style.padding = '2px';
            highlight.style.borderRadius = '2px';
            
            try {
                range.surroundContents(highlight);
                this.currentHighlights.push(highlight);
                return true;
            } catch (e) {
                console.error('Error highlighting node:', e);
                return false;
            }
        },

        // Normalize text for better matching
        normalizeText(text) {
            return text
                .replace(/\s+/g, ' ')           // Replace multiple spaces with a single space
                .replace(/[\n\r\t]/g, ' ')      // Replace newlines and tabs with spaces
                .replace(/\u2019/g, "'")        // Replace right single quotation mark
                .replace(/\u201C|\u201D/g, '"') // Replace curly quotes
                .replace(/\u2013|\u2014/g, '-') // Replace em/en dashes
                .trim();                         // Remove leading/trailing whitespace
        },

        // Find text with fuzzy matching
        findTextInNode(node, searchText) {
            const nodeText = this.normalizeText(node.textContent);
            const normalizedSearch = this.normalizeText(searchText);
            
            // Try exact match first
            const exactIndex = nodeText.indexOf(normalizedSearch);
            if (exactIndex >= 0) {
                return { 
                    index: exactIndex, 
                    length: normalizedSearch.length
                };
            }
            
            // Try case-insensitive match
            const lowerNodeText = nodeText.toLowerCase();
            const lowerSearchText = normalizedSearch.toLowerCase();
            const caseInsensitiveIndex = lowerNodeText.indexOf(lowerSearchText);
            if (caseInsensitiveIndex >= 0) {
                return { 
                    index: caseInsensitiveIndex, 
                    length: lowerSearchText.length
                };
            }
            
            return null;
        },

        // Find text that spans across multiple nodes using first and last words
        findTextAcrossNodes(textNodes, startText, endText, maxDistance = 200) {
            if (!startText || !endText) return null;
            
            const normalizedStartText = this.normalizeText(startText).toLowerCase();
            const normalizedEndText = this.normalizeText(endText).toLowerCase();
            
            console.log('Looking for text between:', normalizedStartText, 'and', normalizedEndText);
            
            // Find all nodes containing the start text
            const startNodes = [];
            for (let i = 0; i < textNodes.length; i++) {
                const nodeText = this.normalizeText(textNodes[i].textContent).toLowerCase();
                if (nodeText.includes(normalizedStartText)) {
                    startNodes.push({ 
                        node: textNodes[i], 
                        index: i, 
                        position: nodeText.indexOf(normalizedStartText)
                    });
                }
            }
            
            if (startNodes.length === 0) {
                console.log('No nodes found containing start text');
                return null;
            }
            
            console.log('Found start text in nodes:', startNodes.length);
            
            // For each start node, look for an end node within maxDistance nodes
            for (const startNode of startNodes) {
                const maxEndIndex = Math.min(startNode.index + maxDistance, textNodes.length);
                
                // Check if the start node itself contains the end text
                const startNodeText = this.normalizeText(startNode.node.textContent).toLowerCase();
                const endInStartNode = startNodeText.indexOf(normalizedEndText, startNode.position + normalizedStartText.length);
                
                if (endInStartNode >= 0) {
                    // Both start and end are in the same node
                    console.log('Found both start and end in the same node');
                    return {
                        startNode: startNode.node,
                        startIndex: startNode.position,
                        endNode: startNode.node,
                        endIndex: endInStartNode + normalizedEndText.length,
                        isSingleNode: true
                    };
                }
                
                // Look for end text in subsequent nodes
                for (let i = startNode.index + 1; i < maxEndIndex; i++) {
                    const nodeText = this.normalizeText(textNodes[i].textContent).toLowerCase();
                    const endPosition = nodeText.indexOf(normalizedEndText);
                    
                    if (endPosition >= 0) {
                        console.log('Found end text in a different node');
                        return {
                            startNode: startNode.node,
                            startIndex: startNode.position,
                            endNode: textNodes[i],
                            endIndex: endPosition + normalizedEndText.length,
                            isSingleNode: false,
                            // Store nodes in between for potential highlighting
                            middleNodes: textNodes.slice(startNode.index + 1, i)
                        };
                    }
                }
            }
            
            console.log('Could not find end text within range of any start node');
            return null;
        },

        // Highlight text that spans across multiple nodes
        highlightAcrossNodes(result) {
            if (result.isSingleNode) {
                // If both start and end are in the same node, use the simple highlighter
                return this.highlightNode(
                    result.startNode, 
                    result.startIndex, 
                    result.endIndex
                );
            } else {
                // For multi-node spans, we need to highlight each node separately
                try {
                    // Highlight the start node from the start position to the end
                    const startHighlighted = this.highlightNode(
                        result.startNode,
                        result.startIndex,
                        result.startNode.textContent.length
                    );
                    
                    // Highlight any nodes in between completely
                    if (result.middleNodes && result.middleNodes.length > 0) {
                        result.middleNodes.forEach(node => {
                            this.highlightNode(node, 0, node.textContent.length);
                        });
                    }
                    
                    // Highlight the end node from the beginning to the end position
                    const endHighlighted = this.highlightNode(
                        result.endNode,
                        0,
                        result.endIndex
                    );
                    
                    // If start was successfully highlighted, scroll to it
                    if (startHighlighted) {
                        result.startNode.parentElement.scrollIntoView({ 
                            behavior: 'smooth', 
                            block: 'center' 
                        });
                        return true;
                    } else if (endHighlighted) {
                        // If only end was highlighted, scroll to that
                        result.endNode.parentElement.scrollIntoView({
                            behavior: 'smooth',
                            block: 'center'
                        });
                        return true;
                    }
                    
                    return false;
                } catch (e) {
                    console.error('Error highlighting across nodes:', e);
                    return false;
                }
            }
        },

        highlightText(verbatim) {
            console.debug('Starting highlight process for verbatim:', verbatim);
            this.removeExistingHighlights();
            
            if (!verbatim || verbatim.trim() === '') {
                console.error('Empty verbatim provided');
                return false;
            }
            
            // Normalize the verbatim text
            const normalizedVerbatim = this.normalizeText(verbatim);
            console.log('Normalized verbatim:', normalizedVerbatim);
            
            const textNodes = this.getTextNodes();
            console.debug('Found text nodes:', textNodes.length);

            // First try exact match in single node (for short citations)
            if (normalizedVerbatim.length < 200) {
                for (let node of textNodes) {
                    const match = this.findTextInNode(node, normalizedVerbatim);
                    if (match) {
                        const highlighted = this.highlightNode(node, match.index, match.index + match.length);
                        if (highlighted) {
                            node.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            return true;
                        }
                    }
                }
            }

            // Main strategy: Try with first 3 words and last 3 words
            const words = normalizedVerbatim.split(' ');
            
            // Determine how many words to use based on citation length
            let firstWordCount = 3;
            let lastWordCount = 3;
            
            // For shorter citations, use fewer words
            if (words.length < 10) {
                firstWordCount = Math.max(1, Math.floor(words.length / 4));
                lastWordCount = Math.max(1, Math.floor(words.length / 4));
            }
            
            if (words.length >= (firstWordCount + lastWordCount)) {
                const firstWords = words.slice(0, firstWordCount).join(' ');
                const lastWords = words.slice(-lastWordCount).join(' ');
                
                console.log(`Trying to match using first ${firstWordCount} words and last ${lastWordCount} words:`, 
                    firstWords, lastWords);
                
                const acrossNodesResult = this.findTextAcrossNodes(
                    textNodes, 
                    firstWords, 
                    lastWords
                );
                
                if (acrossNodesResult) {
                    const highlighted = this.highlightAcrossNodes(acrossNodesResult);
                    if (highlighted) return true;
                }
                
                // If that didn't work, try with just 2 words on each end
                if (firstWordCount > 2 && lastWordCount > 2 && words.length >= 4) {
                    const firstTwoWords = words.slice(0, 2).join(' ');
                    const lastTwoWords = words.slice(-2).join(' ');
                    
                    console.log('Trying with just 2 words on each end:', firstTwoWords, lastTwoWords);
                    
                    const twoWordsResult = this.findTextAcrossNodes(
                        textNodes,
                        firstTwoWords,
                        lastTwoWords
                    );
                    
                    if (twoWordsResult) {
                        const highlighted = this.highlightAcrossNodes(twoWordsResult);
                        if (highlighted) return true;
                    }
                }
            }

            // Fallback: Try with individual sentences (for cases where the citation is broken up)
            const sentences = normalizedVerbatim.split(/[.!?]+/)
                .map(s => s.trim())
                .filter(s => s.length > 15); // Only keep sentences with reasonable length
            
            if (sentences.length > 0) {
                console.log('Fallback: Trying to match individual sentences');
                let foundAny = false;
                
                for (let sentence of sentences) {
                    for (let node of textNodes) {
                        const match = this.findTextInNode(node, sentence);
                        if (match) {
                            const highlighted = this.highlightNode(node, match.index, match.index + match.length);
                            if (highlighted) {
                                if (!foundAny) {
                                    node.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                    foundAny = true;
                                }
                                break; // Move to next sentence
                            }
                        }
                    }
                }
                
                if (foundAny) return true;
            }

            console.log('No matches found for citation');
            return false;
        }
    };

    // Set up message listener only once
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        console.debug('Content script received message:', request);
        
        if (request.action === 'highlight') {
            try {
                if (!request.verbatim) {
                    console.error('No verbatim text provided in request');
                    sendResponse({ success: false, error: 'No verbatim text provided' });
                    return true;
                }
                
                const found = window.iCognitionHighlighter.highlightText(request.verbatim);
                console.debug('Highlight result:', found);
                sendResponse({ success: found });
            } catch (error) {
                console.error('Highlighting error:', error);
                sendResponse({ success: false, error: error.message || 'Unknown error in highlighting' });
            }
            return true;
        } else if (request.action === 'ping') {
            // Simple ping to check if the content script is loaded
            sendResponse({ status: 'ok' });
            return true;
        }
        
        return true; // Keep the message channel open
    });
    
    console.log('iCognition Highlighter: Initialized and ready');
} else {
    console.log('iCognition Highlighter: Already initialized');
}

// Send a ready message to the background script
try {
    chrome.runtime.sendMessage({ action: 'content_script_ready' });
} catch (e) {
    console.error('Error sending ready message:', e);
}
