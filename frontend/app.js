/**
 * AI Business Advisor - Frontend Application
 * WebSocket client with streaming message support and thinking logs
 */

// =============================================================================
// Configuration
// =============================================================================

const CONFIG = {
    // WebSocket URL - auto-detect protocol
    WS_URL: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/chat`,
    // Reconnection settings
    RECONNECT_DELAY: 3000,
    MAX_RECONNECT_ATTEMPTS: 5,
    // Ping interval to keep connection alive
    PING_INTERVAL: 30000,
    // Max thinking logs to show
    MAX_THINKING_LOGS: 15,
};

// =============================================================================
// State Management
// =============================================================================

const state = {
    socket: null,
    isConnected: false,
    isTyping: false,
    isThinking: false,
    isInThinkingMode: false,  // Track if we're inside <think> tags
    thinkingBuffer: '',       // Buffer for thinking content display
    streamBuffer: '',         // Buffer for handling split tags across tokens
    currentMessage: '',
    reconnectAttempts: 0,
    pingInterval: null,
    location: 'India',
    searchProvider: 'tavily',
    thinkingLogs: [],
    inlineThinkingElement: null,  // Reference to inline thinking section in chat
    inlineThinkingContent: null,  // Reference to content area of inline thinking
    sessionId: null,              // Session ID from server
    currentValidationBtn: null,   // Reference to the validation button of the current message
};

// =============================================================================
// DOM Elements
// =============================================================================

const elements = {
    chatMessages: document.getElementById('chatMessages'),
    messageInput: document.getElementById('messageInput'),
    sendButton: document.getElementById('sendButton'),
    connectionStatus: document.getElementById('connectionStatus'),
    typingIndicator: document.getElementById('typingIndicator'),
    typingText: document.getElementById('typingText'),
    locationSelect: document.getElementById('location'),
    toolToast: document.getElementById('toolToast'),
    toolText: document.getElementById('toolText'),
    modelStatus: document.getElementById('modelStatus'),
    thinkingPanel: document.getElementById('thinkingPanel'),
    thinkingLogs: document.getElementById('thinkingLogs'),
    xaiToggle: document.getElementById('xaiToggle'),
    searchProvider: document.getElementById('searchProvider'),
};

// =============================================================================
// WebSocket Connection
// =============================================================================

function connectWebSocket() {
    try {
        state.socket = new WebSocket(CONFIG.WS_URL);

        state.socket.onopen = handleSocketOpen;
        state.socket.onclose = handleSocketClose;
        state.socket.onerror = handleSocketError;
        state.socket.onmessage = handleSocketMessage;
    } catch (error) {
        console.error('WebSocket connection error:', error);
        updateConnectionStatus('error', 'Connection failed');
    }
}

function handleSocketOpen() {
    console.log('WebSocket connected');
    state.isConnected = true;
    state.reconnectAttempts = 0;
    updateConnectionStatus('connected', 'Connected');
    elements.modelStatus.textContent = 'Ready';

    // Start ping interval
    state.pingInterval = setInterval(() => {
        if (state.socket && state.socket.readyState === WebSocket.OPEN) {
            state.socket.send(JSON.stringify({ type: 'ping' }));
        }
    }, CONFIG.PING_INTERVAL);
}

function handleSocketClose(event) {
    console.log('WebSocket closed:', event.code, event.reason);
    state.isConnected = false;
    clearInterval(state.pingInterval);
    updateConnectionStatus('error', 'Disconnected');

    // Attempt reconnection
    if (state.reconnectAttempts < CONFIG.MAX_RECONNECT_ATTEMPTS) {
        state.reconnectAttempts++;
        updateConnectionStatus('error', `Reconnecting (${state.reconnectAttempts}/${CONFIG.MAX_RECONNECT_ATTEMPTS})...`);
        setTimeout(connectWebSocket, CONFIG.RECONNECT_DELAY);
    }
}

function handleSocketError(error) {
    console.error('WebSocket error:', error);
    updateConnectionStatus('error', 'Error');
}

function handleSocketMessage(event) {
    try {
        const data = JSON.parse(event.data);

        switch (data.type) {
            case 'system':
                // Capture session ID if present
                if (data.session_id) {
                    state.sessionId = data.session_id;
                    console.log('Session ID:', state.sessionId);
                }
                break;

            case 'typing':
                showTypingIndicator(data.content);
                showThinkingPanel();
                break;

            case 'thinking':
                addThinkingLog(data.content);
                break;

            case 'thinking_done':
                // Keep panel visible but stop adding logs
                break;

            case 'token':
                appendToken(data.content);
                break;

            case 'tool_status':
                handleToolStatus(data);
                break;

            case 'done':
                finishMessage();
                break;

            case 'error':
                showError(data.content);
                break;

            case 'pong':
                // Keep-alive response, no action needed
                break;
        }
    } catch (error) {
        console.error('Error parsing message:', error);
    }
}

// =============================================================================
// Thinking Panel
// =============================================================================

function showThinkingPanel() {
    // Note: We now use inline thinking sections in the chat flow
    // This function just resets state for compatibility
    state.isThinking = true;
    state.thinkingLogs = [];
    state.isInThinkingMode = false;
    state.thinkingBuffer = '';
    elements.modelStatus.textContent = 'Thinking...';
}

function hideThinkingPanel() {
    state.isThinking = false;
    elements.thinkingPanel.classList.remove('visible');
}

function markThinkingComplete() {
    // Update inline thinking section header to show it's complete
    if (!state.inlineThinkingElement) return;

    const thinkingTitle = state.inlineThinkingElement.querySelector('.inline-thinking-title');
    const thinkingSpinner = state.inlineThinkingElement.querySelector('.inline-thinking-spinner');

    if (thinkingTitle) {
        thinkingTitle.textContent = '✅ ARIA finished thinking';
    }
    if (thinkingSpinner) {
        thinkingSpinner.style.display = 'none';
    }

    // Add a visual indicator that thinking is done
    state.inlineThinkingElement.classList.add('thinking-done');
}

function addThinkingLog(logData) {
    // Add to state
    state.thinkingLogs.push(logData);

    // Limit number of logs shown
    if (state.thinkingLogs.length > CONFIG.MAX_THINKING_LOGS) {
        state.thinkingLogs.shift();
        // Remove first child from DOM
        if (elements.thinkingLogs.firstChild) {
            elements.thinkingLogs.firstChild.remove();
        }
    }

    // Create log entry element
    const logEntry = document.createElement('div');
    logEntry.className = 'thinking-log-entry';
    logEntry.innerHTML = `
        <span class="log-icon">${logData.icon || '💭'}</span>
        <span class="log-message">${escapeHtml(logData.message || logData.label)}</span>
    `;

    // Add animation class
    logEntry.classList.add('log-enter');

    elements.thinkingLogs.appendChild(logEntry);

    // Scroll to bottom of logs
    elements.thinkingLogs.scrollTop = elements.thinkingLogs.scrollHeight;

    // Update typing text to show latest action
    if (logData.label) {
        elements.typingText.textContent = `ARIA is ${logData.label.toLowerCase()}...`;
    }
}

function appendThinkingContent(content) {
    // Stream thinking content to the inline thinking section in chat
    if (!state.inlineThinkingContent) return;

    // Get or create the thinking content element
    let thinkingText = state.inlineThinkingContent.querySelector('.thinking-stream-text');
    if (!thinkingText) {
        thinkingText = document.createElement('div');
        thinkingText.className = 'thinking-stream-text';
        thinkingText.innerHTML = `
            <span class="log-icon">🧠</span>
            <span class="thinking-text-content"></span>
        `;
        state.inlineThinkingContent.appendChild(thinkingText);
    }

    const textElement = thinkingText.querySelector('.thinking-text-content');
    state.thinkingBuffer += content;
    textElement.textContent = state.thinkingBuffer;

    // Scroll to bottom of chat
    scrollToBottom();
}

function addToolSearchLog(toolName, query) {
    addThinkingLog({
        icon: '🔍',
        label: 'Searching Web',
        message: `Searching: "${query.substring(0, 60)}${query.length > 60 ? '...' : ''}"`
    });
}

// =============================================================================
// Message Handling
// =============================================================================

function sendMessage() {
    const message = elements.messageInput.value.trim();

    if (!message || !state.isConnected) {
        return;
    }

    // Add user message to chat
    addMessage(message, 'user');

    // Create inline thinking section in chat (will be populated by streaming)
    createInlineThinkingSection();

    // Clear input
    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';

    // Send to server
    const payload = {
        type: 'message',
        content: message,
        location: state.location,
        search_provider: state.searchProvider,
    };
    console.log('Sending WebSocket message:', payload);
    state.socket.send(JSON.stringify(payload));

    // Reset current message buffer
    state.currentMessage = '';
    state.streamBuffer = '';
    state.isInThinkingMode = false;
    elements.modelStatus.textContent = 'Processing...';
}

function createInlineThinkingSection() {
    // Create an inline thinking section that appears in the chat flow
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'inline-thinking-section';
    thinkingDiv.id = 'currentInlineThinking';
    thinkingDiv.innerHTML = `
        <div class="inline-thinking-header">
            <div class="thinking-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" />
                </svg>
            </div>
            <span class="inline-thinking-title">ARIA is thinking...</span>
            <div class="inline-thinking-spinner"></div>
        </div>
        <div class="inline-thinking-content"></div>
    `;

    elements.chatMessages.appendChild(thinkingDiv);
    scrollToBottom();

    // Store reference
    state.inlineThinkingElement = thinkingDiv;
    state.inlineThinkingContent = thinkingDiv.querySelector('.inline-thinking-content');
}

function addMessage(content, type = 'assistant') {
    // Don't hide thinking panel for assistant messages - let it persist

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;

    const isUser = type === 'user';
    const avatarSVG = isUser
        ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
               <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
               <circle cx="12" cy="7" r="4"/>
           </svg>`
        : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
               <path d="M12 2L2 7L12 12L22 7L12 2Z"/>
               <path d="M2 17L12 22L22 17"/>
               <path d="M2 12L12 17L22 12"/>
           </svg>`;

    messageDiv.innerHTML = `
        <div class="message-avatar">${avatarSVG}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-sender">${isUser ? 'You' : 'ARIA'}</span>
                <span class="message-badge">${isUser ? 'User' : 'AI Advisor'}</span>
            </div>
            <div class="message-text">${isUser ? escapeHtml(content) : ''}</div>
            ${!isUser ? `
                <div class="validation-container">
                    <button class="validate-btn" style="display: none;" data-content="">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                            <path d="M9 11l3 3L22 4" />
                            <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                        </svg>
                        Validate Response
                    </button>
                    <div class="validation-result"></div>
                </div>
            ` : ''}
        </div>
    `;

    elements.chatMessages.appendChild(messageDiv);
    scrollToBottom();

    // Store references to the message elements if it's an assistant message
    if (!isUser) {
        state.currentMessageElement = messageDiv.querySelector('.message-text');
        state.currentValidationBtn = messageDiv.querySelector('.validate-btn');
    }

    return messageDiv;
}

function appendToken(token) {
    // Add token to stream buffer
    state.streamBuffer += token;

    // Process the buffer
    processStreamBuffer();
}

function processStreamBuffer() {
    // Keep processing until we can't make progress
    let madeProgress = true;

    while (madeProgress && state.streamBuffer.length > 0) {
        madeProgress = false;

        if (state.isInThinkingMode) {
            // We're inside <think> tags, look for closing tag
            const closeIndex = state.streamBuffer.indexOf('</think>');

            if (closeIndex !== -1) {
                // Found closing tag - process thinking content before it
                const thinkingContent = state.streamBuffer.substring(0, closeIndex);
                if (thinkingContent) {
                    appendThinkingContent(thinkingContent);
                }

                // Remove thinking content and closing tag from buffer
                state.streamBuffer = state.streamBuffer.substring(closeIndex + 8);
                state.isInThinkingMode = false;
                madeProgress = true;

                console.log('Found </think>, remaining buffer:', JSON.stringify(state.streamBuffer.substring(0, 50)));

                // Mark thinking as complete
                markThinkingComplete();
                addThinkingLog({
                    icon: '✅',
                    label: 'Thinking Complete',
                    message: 'ARIA has finished reasoning'
                });

            } else if (state.streamBuffer.length > 8) {
                // No closing tag found yet, but buffer has content
                // Keep last 8 chars in case </think> is split across tokens
                const safeLength = state.streamBuffer.length - 8;
                if (safeLength > 0) {
                    appendThinkingContent(state.streamBuffer.substring(0, safeLength));
                    state.streamBuffer = state.streamBuffer.substring(safeLength);
                    madeProgress = true;
                }
            }
            // If buffer is <= 8 chars, wait for more tokens

        } else {
            // We're not in thinking mode
            const openIndex = state.streamBuffer.indexOf('<think>');

            if (openIndex !== -1) {
                // Found opening tag
                const beforeThink = state.streamBuffer.substring(0, openIndex);
                if (beforeThink.trim()) {
                    appendActualContent(beforeThink);
                }

                // Remove content before and including <think>
                state.streamBuffer = state.streamBuffer.substring(openIndex + 7);
                state.isInThinkingMode = true;
                state.thinkingBuffer = '';
                madeProgress = true;

                // Show thinking indicator
                if (!state.isThinking) {
                    showThinkingPanel();
                }
                addThinkingLog({
                    icon: '💭',
                    label: 'Reasoning',
                    message: 'ARIA is analyzing your question...'
                });

            } else if (state.streamBuffer.length > 7) {
                // No opening tag, output content (keep last 7 chars for potential split <think>)
                const safeLength = state.streamBuffer.length - 7;
                if (safeLength > 0) {
                    appendActualContent(state.streamBuffer.substring(0, safeLength));
                    state.streamBuffer = state.streamBuffer.substring(safeLength);
                    madeProgress = true;
                }
            }
            // If buffer is <= 7 chars, wait for more tokens
        }
    }
}

function appendActualContent(token) {
    console.log('appendActualContent called with:', JSON.stringify(token.substring(0, 100)));

    // Hide typing indicator once we start receiving actual content
    hideTypingIndicator();
    // Update thinking panel header to show thinking is complete (but keep it visible)
    markThinkingComplete();

    // Create message element if doesn't exist
    if (!state.currentMessageElement) {
        console.log('Creating new assistant message element');
        addMessage('', 'assistant');
    }

    state.currentMessage += token;
    console.log('Current message length:', state.currentMessage.length);

    // Render markdown
    state.currentMessageElement.innerHTML = renderMarkdown(state.currentMessage);
    scrollToBottom();
}

/**
 * Validate a specific assistant message
 * @param {HTMLElement} button - The validate button that was clicked
 * @param {string} content - The content to validate
 */
async function validateMessage(button, content) {
    if (!state.sessionId) {
        console.error('No session ID available for validation');
        return;
    }

    const messageDiv = button.closest('.message');
    const resultContainer = messageDiv.querySelector('.validation-result');

    // Show loading state
    button.disabled = true;
    button.innerHTML = '<span class="spinner-small"></span> Verifying Claims...';
    resultContainer.innerHTML = `
        <div class="validation-loading">
            <div class="loader-bar"></div>
            <p>Cross-referencing stated figures with source tool data...</p>
        </div>
    `;
    resultContainer.className = 'validation-result visible loading';

    try {
        const response = await fetch('/api/validate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message_content: content,
                session_id: state.sessionId
            }),
        });

        const data = await response.json();

        // Remove loading state
        button.style.display = 'none';
        resultContainer.classList.remove('loading');

        if (data.total_claims === 0) {
            // Use the detailed summary from the backend
            const summaryHtml = renderMarkdown(data.summary || 'No specific data points (prices/metrics) were found in this message to validate.');
            resultContainer.innerHTML = `
                <div class="validation-info">
                    <div class="val-summary-detailed">${summaryHtml}</div>
                </div>
            `;
            return;
        }

        // Build status summary
        const statusClass = data.is_valid ? 'success' : 'error';
        const statusIcon = data.is_valid ? '✅' : '⚠️';

        // Build the metrics cards
        let metricsHtml = `
            <div class="validation-metrics">
                <div class="metric-card">
                    <span class="metric-label">Total Claims</span>
                    <span class="metric-value">${data.total_claims}</span>
                </div>
                <div class="metric-card ${data.verified_claims > 0 ? 'passed' : ''}">
                    <span class="metric-label">Verified</span>
                    <span class="metric-value">${data.verified_claims}</span>
                </div>
                ${data.failed_claims > 0 ? `
                <div class="metric-card failed">
                    <span class="metric-label">Inconsistencies</span>
                    <span class="metric-value">${data.failed_claims}</span>
                </div>
                ` : ''}
            </div>
        `;

        // Build the comparison table
        let tableRows = data.checks.map(check => {
            const statusLabel = check.status.toUpperCase();
            const statusClass = `status-${check.status}`;
            const diffHtml = check.status === 'failed' ? `<span class="diff-tag">(${check.diff_pct}% dev)</span>` : '';
            const unit = check.unit || '$';

            return `
                <tr>
                    <td><strong>${check.key || 'N/A'}</strong></td>
                    <td>${unit}${check.claimed != null ? check.claimed.toLocaleString() : 'N/A'}</td>
                    <td>${check.actual != null ? unit + check.actual.toLocaleString() : '<span class="muted">N/A</span>'}</td>
                    <td>
                        <span class="val-status-tag ${statusClass}">${statusLabel}</span>
                        ${diffHtml}
                    </td>
                </tr>
            `;
        }).join('');

        let tableHtml = `
            <div class="val-table-wrapper">
                <table class="val-comparison-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>AI Stated</th>
                            <th>Reference</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}
                    </tbody>
                </table>
            </div>
        `;

        // Render summary as markdown for proper formatting
        const summaryHtml = renderMarkdown(data.summary || '');

        resultContainer.innerHTML = `
            <div class="validation-report ${statusClass}">
                <div class="val-header">
                    <span class="val-icon">${statusIcon}</span>
                    <span class="val-title">${data.is_valid ? 'Integrity Check Passed' : 'Data Inconsistency Detected'}</span>
                </div>
                <div class="val-summary-detailed">${summaryHtml}</div>
                ${metricsHtml}
                ${tableHtml}
            </div>
        `;
        resultContainer.classList.add(statusClass);

    } catch (error) {
        console.error('Validation error:', error);
        button.disabled = false;
        button.textContent = 'Retry Validation';
        resultContainer.innerHTML = '<div class="validation-error">Error connecting to validation service. Please check your connection.</div>';
    }
}

function finishMessage() {
    // Flush any remaining content in the stream buffer
    if (state.streamBuffer.length > 0) {
        console.log('Flushing remaining buffer:', JSON.stringify(state.streamBuffer));
        if (state.isInThinkingMode) {
            // If still in thinking mode, content goes to thinking
            appendThinkingContent(state.streamBuffer);
        } else {
            // Otherwise it's actual content
            appendActualContent(state.streamBuffer);
        }
        state.streamBuffer = '';
    }

    hideTypingIndicator();
    // Don't hide thinking panel - let it persist for the user to review
    hideToolToast();
    state.currentMessageElement = null;
    // state.currentMessage = ''; // Removed to allow capture below
    state.isInThinkingMode = false;
    state.thinkingBuffer = '';
    state.streamBuffer = '';
    // Clear inline thinking references (they persist in DOM but we're done adding to them)
    state.inlineThinkingElement = null;
    state.inlineThinkingContent = null;
    elements.modelStatus.textContent = 'Ready';

    // Show validation button for the finished message
    if (state.currentValidationBtn) {
        state.currentValidationBtn.style.display = 'flex';
        const contentSnapshot = state.currentMessage;

        // Use a clean click handler
        const btn = state.currentValidationBtn;
        btn.onclick = () => validateMessage(btn, contentSnapshot);
    }

    state.currentMessageElement = null;
    state.currentValidationBtn = null;
    state.currentMessage = '';
}

function showError(message) {
    hideTypingIndicator();
    hideThinkingPanel();
    hideToolToast();

    const errorDiv = document.createElement('div');
    errorDiv.className = 'message system-message error-message';
    errorDiv.innerHTML = `
        <div class="message-avatar" style="background: linear-gradient(135deg, #ef4444, #dc2626);">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-sender">System</span>
                <span class="message-badge" style="background: #ef4444;">Error</span>
            </div>
            <div class="message-text" style="border-color: rgba(239, 68, 68, 0.3);">
                ${escapeHtml(message)}
            </div>
        </div>
    `;

    elements.chatMessages.appendChild(errorDiv);
    scrollToBottom();

    state.currentMessageElement = null;
    state.currentValidationBtn = null;
    elements.modelStatus.textContent = 'Error';
}

// =============================================================================
// Tool Status Handling
// =============================================================================

function handleToolStatus(data) {
    if (data.status === 'start') {
        showToolToast(data.content || `Using ${data.tool}...`);
        updateTypingText(`🔍 ${data.content || 'Searching...'}`);

        // Add to thinking logs
        if (data.query) {
            addToolSearchLog(data.tool, data.query);
        }

        // Add a status message to the chat stream
        const statusDiv = document.createElement('div');
        statusDiv.className = 'message system-message tool-usage';
        statusDiv.id = `tool-${data.tool}-${Date.now()}`;
        statusDiv.innerHTML = `
            <div class="message-content">
                <div class="tool-badge">
                    <span class="tool-icon">🔍</span>
                    <span class="tool-name">${data.content || 'Researching...'}</span>
                </div>
            </div>
        `;
        elements.chatMessages.appendChild(statusDiv);
        scrollToBottom();
    } else if (data.status === 'end') {
        hideToolToast();
        updateTypingText('ARIA is analyzing results...');
        addThinkingLog({
            icon: '✅',
            label: 'Search Complete',
            message: 'Web search completed successfully'
        });
    } else if (data.status === 'complete') {
        // Final tool status with query info
        const statusDiv = document.createElement('div');
        statusDiv.className = 'message system-message tool-usage tool-complete';
        statusDiv.innerHTML = `
            <div class="message-content">
                <div class="tool-badge tool-complete-badge">
                    <span class="tool-icon">✅</span>
                    <span class="tool-name">${data.content || 'Search complete'}</span>
                </div>
            </div>
        `;
        elements.chatMessages.appendChild(statusDiv);
        scrollToBottom();
    }
}

function showToolToast(message) {
    elements.toolText.textContent = message;
    elements.toolToast.classList.add('visible');
}

function hideToolToast() {
    elements.toolToast.classList.remove('visible');
}

// =============================================================================
// Typing Indicator
// =============================================================================

function showTypingIndicator(show = true) {
    if (show) {
        elements.typingIndicator.classList.add('visible');
        state.isTyping = true;
    }
}

function hideTypingIndicator() {
    elements.typingIndicator.classList.remove('visible');
    state.isTyping = false;
}

function updateTypingText(text) {
    elements.typingText.textContent = text;
}

// =============================================================================
// UI Helpers
// =============================================================================

function updateConnectionStatus(status, text) {
    elements.connectionStatus.className = `connection-status ${status}`;
    elements.connectionStatus.querySelector('.status-text').textContent = text;
}

function scrollToBottom() {
    elements.chatMessages.scrollTo({
        top: elements.chatMessages.scrollHeight,
        behavior: 'smooth'
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// XAI Parsing Logic
// =============================================================================

function applyXAIParsing(html) {
    // 1. Causal Explanation Wrapper
    // Pattern: <strong>Causal Explanation</strong>:? (content)
    html = html.replace(
        /<p><strong>Causal Explanation<\/strong>:?\s*([\s\S]*?)<\/p>/g,
        '<div class="xai-container"><div class="xai-header">🧠 Causal Reasoning (The Why)</div><div class="xai-content">$1</div></div>'
    );

    // 2. Ethical/Regulatory Check
    // Pattern: <strong>Ethical & Regulatory Check</strong>
    html = html.replace(
        /<p><strong>Ethical & Regulatory Check<\/strong>:?<\/p>([\s\S]*?)<\/ul>/g,
        '<div class="xai-container"><div class="xai-header">🛡️ Ethical Guardrails</div><div class="xai-content">$1</ul></div></div>'
    );

    // 3. Counterfactuals (Recourse)
    // Pattern: <strong>Counterfactuals.*?</strong>
    html = html.replace(
        /<p><strong>Counterfactuals.*?<\/strong>:?<\/p>/g,
        '<div class="recourse-box"><div class="recourse-title">⚡ Recourse (Counterfactuals)</div>'
    );
    // Note: The recourse content usually follows. We just style the header and let the content flow or wrap it if possible.
    // Better strategy for Recourse: identifying the section

    // 4. Compliance Status Badges (Green/Yellow/Red)
    html = html.replace(/\[Compliance Status\]:?\s*\[?(Green|Yellow|Red)\]?/gi, (match, color) => {
        return `<span class="compliance-badge ${color.toLowerCase()}"><span class="status-dot"></span>${color.toUpperCase()} Compliance</span>`;
    });

    return html;
}


// =============================================================================
// Markdown Rendering (Basic)
// =============================================================================

function renderMarkdown(text) {
    if (!text) return '';

    let html = escapeHtml(text);

    // 1. Code blocks - Keep these first
    const codeBlocks = [];
    html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const id = `__CODE_BLOCK_${codeBlocks.length}__`;
        codeBlocks.push(`<pre><code class="language-${lang || ''}">${code}</code></pre>`);
        return id;
    });

    // 2. Robust Table Parsing
    const lines = html.split('\n');
    let resultLines = [];
    let currentTable = [];

    const isTableLine = (line) => {
        const trimmed = line.trim();
        return trimmed.startsWith('|') && trimmed.endsWith('|');
    };

    const isTableSeparator = (line) => {
        const trimmed = line.trim();
        return trimmed.startsWith('|') && trimmed.endsWith('|') && /^[| \-: \t]+$/.test(trimmed) && trimmed.includes('-');
    };

    const parseTable = (rows) => {
        if (rows.length < 2) return rows.join('\n');

        const getCells = (row) => {
            let cells = row.trim().split('|');
            // Remove first and last empty cells
            if (cells[0] === '') cells.shift();
            if (cells.length > 0 && cells[cells.length - 1] === '') cells.pop();
            return cells;
        };

        const headers = getCells(rows[0]).map(cell => `<th>${cell.trim()}</th>`).join('');

        // Skip separator row (rows[1])
        const bodyRows = rows.slice(2).map(row => {
            const cells = getCells(row).map(cell => `<td>${cell.trim()}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');

        return `<div class="table-container"><table><thead><tr>${headers}</tr></thead><tbody>${bodyRows}</tbody></table></div>`;
    };

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (isTableLine(line)) {
            currentTable.push(line);
        } else {
            if (currentTable.length >= 2 && currentTable.some(l => isTableSeparator(l))) {
                resultLines.push(parseTable(currentTable));
            } else {
                resultLines = resultLines.concat(currentTable);
            }
            currentTable = [];
            resultLines.push(line);
        }
    }
    if (currentTable.length >= 2 && currentTable.some(l => isTableSeparator(l))) {
        resultLines.push(parseTable(currentTable));
    } else {
        resultLines = resultLines.concat(currentTable);
    }
    html = resultLines.join('\n');

    // 3. Block Elements
    html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/^---$/gm, '<hr>');
    html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

    // 4. Inline Elements
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
    html = html.replace(/_(.+?)_/g, '<em>$1</em>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    // 5. Lists
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // 6. Paragraphs and Line Breaks
    html = html.replace(/\n\n/g, '</p><p>');
    const processedLines = html.split('\n');
    html = processedLines.map(line => {
        if (line.match(/^<(ul|ol|li|table|thead|tbody|tr|th|td|h1|h2|h3|h4|hr|blockquote|pre|p|div|section)/) ||
            line.match(/<\/(ul|ol|li|table|thead|tbody|tr|th|td|h1|h2|h3|h4|hr|blockquote|pre|p|div|section)>$/) ||
            line.includes('class="table-container"')) {
            return line;
        }
        if (line.trim() === '') return line;
        return line + '<br>';
    }).join('\n');

    if (!html.trim().startsWith('<')) {
        html = '<p>' + html + '</p>';
    }

    // 7. Restore Code Blocks
    codeBlocks.forEach((block, i) => {
        html = html.replace(`__CODE_BLOCK_${i}__`, block);
    });

    html = html.replace(/<\/(ul|ol|table|h1|h2|h3|h4|hr|blockquote|pre|p|div)><br>/g, '</$1>');

    return applyXAIParsing(html);
}

// =============================================================================
// Event Listeners
// =============================================================================

// Send button click
elements.sendButton.addEventListener('click', sendMessage);

// Enter key to send (Shift+Enter for new line)
elements.messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto-resize textarea
elements.messageInput.addEventListener('input', () => {
    elements.messageInput.style.height = 'auto';
    elements.messageInput.style.height = Math.min(elements.messageInput.scrollHeight, 150) + 'px';
});

// Location change
elements.locationSelect.addEventListener('change', (e) => {
    state.location = e.target.value;
    console.log('Location changed to:', state.location);
});

// Disable send button when not connected
setInterval(() => {
    elements.sendButton.disabled = !state.isConnected || state.isTyping;
}, 100);

// Search Provider change
if (elements.searchProvider) {
    elements.searchProvider.addEventListener('change', (e) => {
        state.searchProvider = e.target.value;
        console.log('Search Provider changed to:', state.searchProvider);
    });
}

// XAI Toggle
if (elements.xaiToggle) {
    elements.xaiToggle.addEventListener('change', (e) => {
        if (e.target.checked) {
            document.body.classList.add('xai-active');
        } else {
            document.body.classList.remove('xai-active');
        }
    });
    // Init state
    if (elements.xaiToggle.checked) {
        document.body.classList.add('xai-active');
    }
}

// =============================================================================
// Initialize
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize location from select
    state.location = elements.locationSelect.value;

    // Connect to WebSocket
    connectWebSocket();

    // Focus input
    elements.messageInput.focus();
});

// Reconnect on visibility change (when user returns to tab)
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && !state.isConnected) {
        connectWebSocket();
    }
});
