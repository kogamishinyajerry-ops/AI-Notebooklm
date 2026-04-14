const queryInput = document.getElementById('query-input');
const chatHistory = document.getElementById('chat-history');
const highlightOverlay = document.getElementById('highlight');

queryInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && queryInput.value.trim()) {
        const query = queryInput.value.trim();
        queryInput.value = '';
        addMessage('user', query);
        performChat(query);
    }
});

function addMessage(role, text) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    // Simple placeholder for rendering citations into buttons
    // The backend returns XML tags like <citation src='...' page='...'>...</citation>
    if (role === 'assistant') {
        div.innerHTML = formatAssistantResponse(text);
    } else {
        div.textContent = text;
    }
    
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function formatAssistantResponse(text) {
    // Regex to convert <citation src='S' page='P'>Text</citation> to a button
    return text.replace(/<citation src=['"]([^'"]+)['"] page=['"]([^'"]+)['"]>(.*?)<\/citation>/g, (match, src, page, content) => {
        return `<button class="citation-btn" onclick="showSource('${src}', '${page}')">
            ${src} P.${page}
        </button>`;
    });
}

async function performChat(query) {
    try {
        const response = await fetch('/api/v1/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                space_id: 'default'
            })
        });
        
        const data = await response.json();
        
        // Store citations globally so they are accessible via window.showSource
        window.currentCitations = data.citations;
        
        addMessage('assistant', data.answer);
    } catch (err) {
        addMessage('system', 'Error: Failed to connect to local brain.');
    }
}

window.showSource = (src, page) => {
    console.log(`Navigating to ${src} Page ${page}`);
    
    // Find the citation metadata to get BBox
    const citation = window.currentCitations?.find(c => c.source_file === src && c.page_number == page);
    
    if (citation && citation.bbox) {
        applyHighlight(citation.bbox);
    }
};

function applyHighlight(bbox) {
    // BBox: [x0, y0, x1, y1]
    // In our mock, we just apply these as px for demonstration.
    // In production, we would scale these to the current viewport width/height.
    highlightOverlay.style.display = 'block';
    highlightOverlay.style.left = `${bbox[0]}px`;
    highlightOverlay.style.top = `${bbox[1]}px`;
    highlightOverlay.style.width = `${bbox[2] - bbox[0]}px`;
    highlightOverlay.style.height = `${bbox[3] - bbox[1]}px`;
    
    // Smooth scroll to highlight if nested deep
    highlightOverlay.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
