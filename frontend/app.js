// --- App State ---
let socket = null;
let currentAgentTextBuffer = "";
let currentBotMessageBubble = null;

// --- DOM Elements ---
const messagesList = document.getElementById("messages-list");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("user-chat-input");
const typingIndicator = document.getElementById("bot-typing-indicator");
const interactivePanel = document.getElementById("interactive-panel-container");
const chatContainer = document.getElementById("chat-message-container");

// --- Initialize App ---
document.addEventListener("DOMContentLoaded", () => {
    connectWebSocket();
    setupChatForm();
    setupAutoResizeInput();
});

// --- WebSocket Connection ---
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    
    // Retrieve or generate a session ID that persists in the browser
    let sessionId = localStorage.getItem("infra_agent_session_id");
    if (!sessionId) {
        sessionId = "session_" + Math.random().toString(36).substring(2, 15);
        localStorage.setItem("infra_agent_session_id", sessionId);
    }
    
    const wsUrl = `${protocol}//${window.location.host}/ws/chat?session_id=${sessionId}`;
    
    updateWsBadge("connecting");
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        logger("WebSocket connection established.");
        updateWsBadge("connected");
    };

    socket.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleServerMessage(msg);
        } catch (err) {
            console.error("Error parsing socket message:", err, event.data);
        }
    };

    socket.onclose = () => {
        logger("WebSocket connection closed.");
        updateWsBadge("disconnected");
        // Try to reconnect in 5 seconds
        setTimeout(connectWebSocket, 5000);
    };

    socket.onerror = (error) => {
        console.error("WebSocket error:", error);
    };
}

// --- Badge & Credentials Status UI ---
function updateWsBadge(state) {
    // UI badge removed as per request
}

function updateAwsCredentialsUI(available) {
    const banner = document.getElementById("aws-creds-banner");
    if (!banner) return;
    
    banner.className = "creds-banner";
    if (available) {
        banner.classList.add("creds-active");
        banner.querySelector(".banner-icon").textContent = "✅";
        banner.querySelector(".banner-text").textContent = "AWS credentials active. Ready for deployment.";
    } else {
        banner.classList.add("creds-missing");
        banner.querySelector(".banner-icon").textContent = "⚠️";
        banner.querySelector(".banner-text").textContent = "AWS credentials missing. Provisioning steps 5 & 6 will fail.";
    }
}

// --- Handle Incoming Server Messages ---
function handleServerMessage(msg) {
    const { type } = msg;

    switch (type) {
        case "credentials_status":
            updateAwsCredentialsUI(msg.available);
            break;
            
        case "status":
            updateTimeline(msg.step);
            const stepIcons = {
                1: "🔍",
                2: "📝",
                3: "🧪",
                4: "👥",
                5: "📊",
                6: "🚀"
            };
            const icon = stepIcons[msg.step] || "⚙️";
            addLogMessage("system", `${icon} ${msg.description}`);
            setTypingIndicator(true);
            break;

        case "text":
            handleStreamedToken(msg.content);
            break;

        case "complete":
            setTypingIndicator(false);
            finalizeStreamedResponse();
            addLogMessage("complete", msg.content || "Session finished.");
            // Mark all steps as complete
            updateTimeline(7);
            break;

        case "error":
            setTypingIndicator(false);
            finalizeStreamedResponse();
            addLogMessage("error", msg.message);
            break;

        case "info_request":
            setTypingIndicator(false);
            finalizeStreamedResponse();
            showInfoRequestPanel(msg.prompt);
            break;

        case "script_approval":
            setTypingIndicator(false);
            finalizeStreamedResponse();
            showScriptApprovalPanel(msg.code);
            break;

        case "plan_approval":
            setTypingIndicator(false);
            finalizeStreamedResponse();
            showPlanApprovalPanel(msg.plan);
            break;
    }
}

// --- Text Streaming Helpers ---
function handleStreamedToken(token) {
    if (!currentBotMessageBubble) {
        setTypingIndicator(false);
        // Create new bot message container
        const messageDiv = document.createElement("div");
        messageDiv.className = "message message-bot";
        
        const senderDiv = document.createElement("div");
        senderDiv.className = "msg-sender";
        senderDiv.textContent = "Infra Agent";
        messageDiv.appendChild(senderDiv);
        
        currentBotMessageBubble = document.createElement("div");
        currentBotMessageBubble.className = "msg-bubble";
        messageDiv.appendChild(currentBotMessageBubble);
        
        messagesList.appendChild(messageDiv);
        currentAgentTextBuffer = "";
    }
    
    currentAgentTextBuffer += token;
    currentBotMessageBubble.innerHTML = formatMarkdown(currentAgentTextBuffer);
    scrollToBottom();
}

function finalizeStreamedResponse() {
    currentBotMessageBubble = null;
    currentAgentTextBuffer = "";
}

// --- Timeline Updates ---
function updateTimeline(activeStepNum) {
    for (let i = 1; i <= 6; i++) {
        const stepEl = document.getElementById(`step-${i}`);
        if (!stepEl) continue;
        if (i < activeStepNum) {
            stepEl.className = "timeline-step step-completed";
        } else if (i === activeStepNum) {
            stepEl.className = "timeline-step step-active";
        } else {
            stepEl.className = "timeline-step step-pending";
        }
    }
}

// --- HITL Interactive Panels Injection ---
function showInfoRequestPanel(prompt) {
    interactivePanel.innerHTML = `
        <div class="hitl-card">
            <h3>🔍 Information Required</h3>
            <p class="hitl-desc">${formatMarkdown(prompt)}</p>
            <div class="hitl-form-group">
                <input type="text" id="hitl-info-input" class="hitl-input" placeholder="Type your answer here..." autocomplete="off">
            </div>
            <div class="hitl-actions">
                <button id="hitl-info-submit" class="btn-primary">Submit Answer</button>
            </div>
        </div>
    `;
    interactivePanel.classList.remove("hidden");
    
    const input = document.getElementById("hitl-info-input");
    input.focus();
    
    // Submit handler
    const submitBtn = document.getElementById("hitl-info-submit");
    const submitAction = () => {
        const value = input.value.trim();
        if (!value) return;
        
        // Hide panel
        interactivePanel.classList.add("hidden");
        interactivePanel.innerHTML = "";
        
        // Add message to chat list log
        addLogMessage("user", value);
        
        // Send back
        sendSocketMessage({
            type: "info_response",
            text: value
        });
        setTypingIndicator(true);
    };

    submitBtn.onclick = submitAction;
    input.onkeydown = (e) => {
        if (e.key === "Enter") {
            submitAction();
        }
    };
}

function showScriptApprovalPanel(code) {
    interactivePanel.innerHTML = `
        <div class="hitl-card">
            <h3>📝 Review Generated Terraform Configuration (main.tf)</h3>
            <p class="hitl-desc">Review the resource script code below. Approve to format and validate, or request changes.</p>
            <div class="code-panel">
                <pre><code class="language-hcl" id="tf-code-block">${escapeHtml(code)}</code></pre>
            </div>
            
            <div id="script-feedback-box" class="feedback-box hidden">
                <label for="script-feedback-input">Describe changes to apply:</label>
                <textarea id="script-feedback-input" class="hitl-input" rows="2" placeholder="e.g. 'Use t3.micro instead', 'Add a tags map with Environment=Dev'"></textarea>
            </div>
            
            <div class="hitl-actions">
                <button id="btn-approve-script" class="btn-success">Approve Configuration</button>
                <button id="btn-reject-script" class="btn-danger">Request Changes</button>
                <button id="btn-cancel-reject-script" class="btn-secondary hidden">Cancel</button>
                <button id="btn-submit-script-feedback" class="btn-primary hidden">Submit Requests</button>
            </div>
        </div>
    `;
    interactivePanel.classList.remove("hidden");
    scrollToBottom();

    const approveBtn = document.getElementById("btn-approve-script");
    const rejectBtn = document.getElementById("btn-reject-script");
    const cancelRejectBtn = document.getElementById("btn-cancel-reject-script");
    const submitFeedbackBtn = document.getElementById("btn-submit-script-feedback");
    const feedbackBox = document.getElementById("script-feedback-box");
    const feedbackInput = document.getElementById("script-feedback-input");

    approveBtn.onclick = () => {
        interactivePanel.classList.add("hidden");
        interactivePanel.innerHTML = "";
        addLogMessage("user", "[Approved Terraform script configuration]");
        sendSocketMessage({
            type: "script_approval_response",
            approved: true
        });
        setTypingIndicator(true);
    };

    rejectBtn.onclick = () => {
        // Toggle view
        approveBtn.classList.add("hidden");
        rejectBtn.classList.add("hidden");
        cancelRejectBtn.classList.remove("hidden");
        submitFeedbackBtn.classList.remove("hidden");
        feedbackBox.classList.remove("hidden");
        feedbackInput.focus();
    };

    cancelRejectBtn.onclick = () => {
        approveBtn.classList.remove("hidden");
        rejectBtn.classList.remove("hidden");
        cancelRejectBtn.classList.add("hidden");
        submitFeedbackBtn.classList.add("hidden");
        feedbackBox.classList.add("hidden");
        feedbackInput.value = "";
    };

    submitFeedbackBtn.onclick = () => {
        const feedback = feedbackInput.value.trim();
        if (!feedback) return;

        interactivePanel.classList.add("hidden");
        interactivePanel.innerHTML = "";
        addLogMessage("user", `[Script Rejected] Requested Changes: ${feedback}`);
        sendSocketMessage({
            type: "script_approval_response",
            approved: false,
            feedback: feedback
        });
        setTypingIndicator(true);
    };
}

function showPlanApprovalPanel(plan) {
    interactivePanel.innerHTML = `
        <div class="hitl-card">
            <h3>📊 Review Execution Plan (terraform plan)</h3>
            <p class="hitl-desc">Review the resource execution blueprint. Ready to apply changes to AWS?</p>
            <div class="console-panel">
                <pre><code id="tf-plan-block">${escapeHtml(plan)}</code></pre>
            </div>
            
            <div id="plan-feedback-box" class="feedback-box hidden">
                <label for="plan-feedback-input">Describe changes / inputs required:</label>
                <textarea id="plan-feedback-input" class="hitl-input" rows="2" placeholder="e.g. 'Bucket needs to be private', 'Add tags'"></textarea>
            </div>
            
            <div class="hitl-actions">
                <button id="btn-approve-plan" class="btn-success">Deploy Infrastructure</button>
                <button id="btn-reject-plan" class="btn-danger">Modify Infrastructure</button>
                <button id="btn-cancel-reject-plan" class="btn-secondary hidden">Cancel</button>
                <button id="btn-submit-plan-feedback" class="btn-primary hidden">Submit Changes</button>
            </div>
        </div>
    `;
    interactivePanel.classList.remove("hidden");
    scrollToBottom();

    const approveBtn = document.getElementById("btn-approve-plan");
    const rejectBtn = document.getElementById("btn-reject-plan");
    const cancelRejectBtn = document.getElementById("btn-cancel-reject-plan");
    const submitFeedbackBtn = document.getElementById("btn-submit-plan-feedback");
    const feedbackBox = document.getElementById("plan-feedback-box");
    const feedbackInput = document.getElementById("plan-feedback-input");

    approveBtn.onclick = () => {
        interactivePanel.classList.add("hidden");
        interactivePanel.innerHTML = "";
        addLogMessage("user", "[Approved Terraform execution plan. Commencing Apply]");
        sendSocketMessage({
            type: "plan_approval_response",
            approved: true
        });
        setTypingIndicator(true);
    };

    rejectBtn.onclick = () => {
        approveBtn.classList.add("hidden");
        rejectBtn.classList.add("hidden");
        cancelRejectBtn.classList.remove("hidden");
        submitFeedbackBtn.classList.remove("hidden");
        feedbackBox.classList.remove("hidden");
        feedbackInput.focus();
    };

    cancelRejectBtn.onclick = () => {
        approveBtn.classList.remove("hidden");
        rejectBtn.classList.remove("hidden");
        cancelRejectBtn.classList.add("hidden");
        submitFeedbackBtn.classList.add("hidden");
        feedbackBox.classList.add("hidden");
        feedbackInput.value = "";
    };

    submitFeedbackBtn.onclick = () => {
        const feedback = feedbackInput.value.trim();
        if (!feedback) return;

        interactivePanel.classList.add("hidden");
        interactivePanel.innerHTML = "";
        addLogMessage("user", `[Plan Rejected] Requested Modifications: ${feedback}`);
        sendSocketMessage({
            type: "plan_approval_response",
            approved: false,
            feedback: feedback
        });
        setTypingIndicator(true);
    };
}

// --- Chat Input & Forms Handling ---
function setupChatForm() {
    chatForm.onsubmit = (event) => {
        event.preventDefault();
        const content = chatInput.value.trim();
        if (!content) return;

        // Reset text area
        chatInput.value = "";
        chatInput.style.height = "auto";

        // Check if agent is currently running. If not, this starts the session!
        if (messagesList.children.length === 0) {
            // Remove welcome container
            const welcome = document.querySelector(".chat-welcome-msg");
            if (welcome) welcome.remove();
            
            addLogMessage("user", content);
            sendSocketMessage({
                type: "start",
                prompt: content
            });
            updateTimeline(1);
        } else {
            // Normal chat response
            addLogMessage("user", content);
            sendSocketMessage({
                type: "chat",
                content: content
            });
        }

        setTypingIndicator(true);
    };

    // Submit on Enter (unless shift is held)
    chatInput.onkeydown = (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            chatForm.requestSubmit();
        }
    };
}

function setupAutoResizeInput() {
    chatInput.addEventListener("input", function() {
        this.style.height = "auto";
        this.style.height = (this.scrollHeight - 10) + "px";
    });
}

// --- Chat Append Log Messages ---
function addLogMessage(sender, text) {
    // If it's a welcome message deletion
    if (messagesList.children.length === 0) {
        const welcome = document.querySelector(".chat-welcome-msg");
        if (welcome) welcome.remove();
    }

    const messageDiv = document.createElement("div");
    messageDiv.className = `message message-${sender}`;
    if (sender === "complete" || sender === "system") {
        messageDiv.classList.add("message-bot");
    }

    const senderDiv = document.createElement("div");
    senderDiv.className = "msg-sender";
    senderDiv.textContent = sender === "user" ? "You" : (sender === "system" ? "" : (sender === "complete" ? "" : "Infra Agent"));
    if (sender === "system" || sender === "complete") {
        senderDiv.style.display = "none";
    }
    messageDiv.appendChild(senderDiv);

    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    
    if (sender === "system") {
        messageDiv.className = "message message-system";
        bubble.style.background = "#f0f4f8";
        bubble.style.border = "1px solid #d0e0f0";
        bubble.style.color = "#4a5568";
        bubble.style.fontSize = "0.85rem";
        bubble.style.fontFamily = "var(--font-sans)";
        bubble.style.borderRadius = "20px";
        bubble.style.padding = "0.4rem 1rem";
        bubble.style.margin = "0.25rem auto";
        bubble.style.textAlign = "center";
        bubble.style.display = "inline-block";
    } else if (sender === "error") {
        bubble.style.background = "rgba(255, 82, 82, 0.05)";
        bubble.style.border = "1px solid rgba(255, 82, 82, 0.15)";
        bubble.style.color = "var(--error)";
        bubble.style.fontSize = "0.9rem";
    } else if (sender === "complete") {
        bubble.style.background = "rgba(50, 205, 50, 0.05)";
        bubble.style.border = "1px solid var(--success)";
        bubble.style.color = "var(--success)";
        bubble.style.fontWeight = "500";
        bubble.style.fontSize = "0.95rem";
    }

    bubble.innerHTML = formatMarkdown(text);
    messageDiv.appendChild(bubble);
    messagesList.appendChild(messageDiv);
    
    scrollToBottom();
}

// --- Utilities ---
function sendSocketMessage(msg) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(msg));
    } else {
        console.error("Socket not connected. Message dropped:", msg);
        addLogMessage("error", "Error: Lost server connection. Retrying...");
    }
}

function setTypingIndicator(show) {
    const isHidden = typingIndicator.classList.contains("hidden");
    if (show && isHidden) {
        typingIndicator.classList.remove("hidden");
        scrollToBottom();
    } else if (!show && !isHidden) {
        typingIndicator.classList.add("hidden");
    }
}

function formatMarkdown(text) {
    if (!text) return "";
    let formatted = escapeHtml(text)
        // Bold markdown
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        // Monospace code tags
        .replace(/`(.*?)`/g, "<code>$1</code>")
        // New lines
        .replace(/\n/g, "<br>");
    return formatted;
}

function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function logger(msg) {
    console.log(`[App] ${msg}`);
}
