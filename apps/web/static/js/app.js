/**
 * COMAC Intelligent NotebookLM — Frontend
 * S-19: PDF viewer with page-image API + citation bbox highlight
 * S-20: Chat history persistence + Notes panel
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentNotebookId = null;
let currentSourceId   = null;
let currentPage       = 1;
let totalPages        = 0;
let currentPageWidth  = 595;  // PDF points (A4 default); updated on render
let currentPageHeight = 842;
let highlightTimer    = null;
window.currentCitations = [];

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const queryInput       = document.getElementById('query-input');
const sendBtn          = document.getElementById('send-btn');
const chatHistory      = document.getElementById('chat-history');
const notebookSelect   = document.getElementById('notebook-select');
const newNotebookBtn   = document.getElementById('new-notebook-btn');
const sourceList       = document.getElementById('source-list');
const uploadInput      = document.getElementById('upload-input');
const prevPageBtn      = document.getElementById('prev-page');
const nextPageBtn      = document.getElementById('next-page');
const pageIndicator    = document.getElementById('page-indicator');
const pdfCanvas        = document.getElementById('pdf-canvas');
const canvasWrapper    = document.getElementById('canvas-wrapper');
const pdfPlaceholder   = document.getElementById('pdf-placeholder');
const pdfTitle         = document.getElementById('pdf-title');
const highlightOverlay = document.getElementById('highlight-overlay');
const clearHistoryBtn  = document.getElementById('clear-history-btn');
const notesList        = document.getElementById('notes-list');
const refreshNotesBtn  = document.getElementById('refresh-notes-btn');

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
(async function init() {
    await loadNotebooks();
    const opts = notebookSelect.options;
    if (opts.length === 2) {
        notebookSelect.selectedIndex = 1;
        await selectNotebook(opts[1].value);
    }
})();

// ---------------------------------------------------------------------------
// Notebooks
// ---------------------------------------------------------------------------
async function loadNotebooks() {
    try {
        const resp = await fetch('/api/v1/notebooks');
        const notebooks = await resp.json();
        notebookSelect.innerHTML = '<option value="">— select —</option>';
        for (const nb of notebooks) {
            const opt = document.createElement('option');
            opt.value = nb.id;
            opt.textContent = nb.name;
            notebookSelect.appendChild(opt);
        }
    } catch (e) {
        console.error('Failed to load notebooks', e);
    }
}

notebookSelect.addEventListener('change', async () => {
    const id = notebookSelect.value;
    if (id) await selectNotebook(id);
});

newNotebookBtn.addEventListener('click', async () => {
    const name = prompt('Notebook name:');
    if (!name) return;
    const resp = await fetch('/api/v1/notebooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });
    if (resp.ok) {
        const nb = await resp.json();
        await loadNotebooks();
        notebookSelect.value = nb.id;
        await selectNotebook(nb.id);
    }
});

async function selectNotebook(notebookId) {
    currentNotebookId = notebookId;
    currentSourceId = null;
    resetPdfViewer();
    clearChatUI();
    await Promise.all([
        loadSources(notebookId),
        loadChatHistory(notebookId),
        loadNotes(notebookId),
    ]);
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------
async function loadSources(notebookId) {
    try {
        const resp = await fetch(`/api/v1/notebooks/${notebookId}/sources`);
        renderSources(await resp.json());
    } catch (e) {
        console.error('Failed to load sources', e);
    }
}

function renderSources(sources) {
    if (!sources.length) {
        sourceList.innerHTML = '<p class="empty-hint">No sources yet</p>';
        return;
    }
    sourceList.innerHTML = '';
    for (const src of sources) {
        const div = document.createElement('div');
        div.className = 'source-item' + (src.id === currentSourceId ? ' active' : '');
        div.title = src.filename;
        div.innerHTML = `
            <span class="source-name">${escapeHtml(src.filename)}</span>
            <span class="source-meta">${src.page_count ? src.page_count + ' pp' : src.status}</span>
        `;
        div.addEventListener('click', () => openSource(src));
        sourceList.appendChild(div);
    }
}

async function openSource(src) {
    currentSourceId = src.id;
    currentPage  = 1;
    totalPages   = src.page_count || 1;
    pdfTitle.textContent = src.filename;
    pdfPlaceholder.style.display = 'none';
    canvasWrapper.style.display  = 'flex';
    updatePageNav();
    await renderPage(src.id, currentPage);
    // Refresh sidebar active state
    await loadSources(currentNotebookId);
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------
uploadInput.addEventListener('change', async (e) => {
    if (!currentNotebookId) { alert('Select a notebook first.'); return; }
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    addMessage('system', `Uploading ${escapeHtml(file.name)}…`);
    try {
        const resp = await fetch(
            `/api/v1/notebooks/${currentNotebookId}/sources/upload`,
            { method: 'POST', body: form }
        );
        if (!resp.ok) throw new Error((await resp.json()).detail);
        const data = await resp.json();
        addMessage('system', `✓ ${escapeHtml(data.filename)} indexed — ${data.chunks_indexed} chunks`);
        await loadSources(currentNotebookId);
    } catch (err) {
        addMessage('system', `Upload failed: ${escapeHtml(err.message)}`);
    }
    uploadInput.value = '';
});

// ---------------------------------------------------------------------------
// PDF Page Rendering (page-image API → canvas)
// ---------------------------------------------------------------------------
async function renderPage(sourceId, pageNum) {
    const url = `/api/v1/notebooks/${currentNotebookId}/sources/${sourceId}/pages/${pageNum}`;
    try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        const imgUrl = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
            pdfCanvas.width  = img.naturalWidth;
            pdfCanvas.height = img.naturalHeight;
            // 144 DPI render = 2× scale → original pts = dimension / 2
            currentPageWidth  = img.naturalWidth  / 2;
            currentPageHeight = img.naturalHeight / 2;
            pdfCanvas.getContext('2d').drawImage(img, 0, 0);
            URL.revokeObjectURL(imgUrl);
        };
        img.src = imgUrl;
        pageIndicator.textContent = `${pageNum} / ${totalPages}`;
    } catch (e) {
        console.error('renderPage error', e);
    }
}

function updatePageNav() {
    prevPageBtn.disabled = currentPage <= 1;
    nextPageBtn.disabled = currentPage >= totalPages;
    pageIndicator.textContent = `${currentPage} / ${totalPages}`;
}

prevPageBtn.addEventListener('click', async () => {
    if (currentPage > 1 && currentSourceId) {
        currentPage--;
        updatePageNav();
        await renderPage(currentSourceId, currentPage);
    }
});

nextPageBtn.addEventListener('click', async () => {
    if (currentPage < totalPages && currentSourceId) {
        currentPage++;
        updatePageNav();
        await renderPage(currentSourceId, currentPage);
    }
});

function resetPdfViewer() {
    pdfPlaceholder.style.display = 'flex';
    canvasWrapper.style.display  = 'none';
    pdfTitle.textContent = 'Document Preview';
    pageIndicator.textContent = '— / —';
    prevPageBtn.disabled = true;
    nextPageBtn.disabled = true;
    clearHighlight();
}

// ---------------------------------------------------------------------------
// Citation highlight (S-19)
// ---------------------------------------------------------------------------
window.showSource = async (src, page, bboxStr) => {
    const citation = window.currentCitations?.find(
        c => c.source_file === src && c.page_number == page
    );
    const bbox = citation?.bbox || parseBboxStr(bboxStr);

    if (!currentNotebookId) return;
    try {
        const resp = await fetch(`/api/v1/notebooks/${currentNotebookId}/sources`);
        const sources = await resp.json();
        const match = sources.find(s => s.filename === src);
        if (!match) return;

        const needsPageLoad = match.id !== currentSourceId || currentPage !== parseInt(page);
        if (needsPageLoad) {
            currentSourceId = match.id;
            currentPage     = parseInt(page) || 1;
            totalPages      = match.page_count || currentPage;
            pdfTitle.textContent = match.filename;
            pdfPlaceholder.style.display = 'none';
            canvasWrapper.style.display  = 'flex';
            updatePageNav();
            await renderPage(match.id, currentPage);
        }
        setTimeout(() => applyHighlight(bbox), 200);
    } catch (e) {
        console.error('showSource error', e);
    }
};

function parseBboxStr(str) {
    if (!str) return null;
    const parts = String(str).split(',').map(Number);
    return parts.length === 4 && parts.every(n => !isNaN(n)) ? parts : null;
}

function applyHighlight(bbox) {
    if (!bbox || bbox.length !== 4) return;
    clearHighlight();

    // Scale PDF-points bbox to canvas display pixels
    const displayW = pdfCanvas.offsetWidth  || pdfCanvas.width;
    const displayH = pdfCanvas.offsetHeight || pdfCanvas.height;
    const scaleX = displayW / currentPageWidth;
    const scaleY = displayH / currentPageHeight;

    highlightOverlay.style.left    = `${bbox[0] * scaleX}px`;
    highlightOverlay.style.top     = `${bbox[1] * scaleY}px`;
    highlightOverlay.style.width   = `${(bbox[2] - bbox[0]) * scaleX}px`;
    highlightOverlay.style.height  = `${(bbox[3] - bbox[1]) * scaleY}px`;
    highlightOverlay.style.opacity = '1';
    highlightOverlay.style.display = 'block';
    highlightOverlay.scrollIntoView({ behavior: 'smooth', block: 'center' });

    if (highlightTimer) clearTimeout(highlightTimer);
    highlightTimer = setTimeout(clearHighlight, 3000);
}

function clearHighlight() {
    highlightOverlay.style.opacity = '0';
    setTimeout(() => { highlightOverlay.style.display = 'none'; }, 300);
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
queryInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && queryInput.value.trim()) submitQuery();
});
sendBtn.addEventListener('click', () => {
    if (queryInput.value.trim()) submitQuery();
});

function submitQuery() {
    const query = queryInput.value.trim();
    queryInput.value = '';
    addMessage('user', query);
    performChat(query);
}

function addMessage(role, text, citations = [], isVerified = false) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    if (role === 'assistant') {
        div.innerHTML = formatAssistantResponse(text, citations);
        // Save-as-note button for assistant messages
        const saveBtn = document.createElement('button');
        saveBtn.className = 'save-note-btn';
        saveBtn.textContent = '💾 Save note';
        saveBtn.addEventListener('click', () => saveNote(text, citations));
        div.appendChild(saveBtn);
    } else {
        div.textContent = text;
    }

    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function formatAssistantResponse(text, citations = []) {
    return text.replace(
        /<citation src=['"]([^'"]+)['"] page=['"]([^'"]+)['"]>(.*?)<\/citation>/gs,
        (match, src, page, content) => {
            const citObj = citations.find(c => c.source_file === src && c.page_number == page);
            const bboxStr = citObj?.bbox ? citObj.bbox.join(',') : '';
            return `<button class="citation-btn"
                onclick="showSource('${escapeAttr(src)}','${escapeAttr(page)}','${bboxStr}')">
                &#128196; ${escapeHtml(src)} p.${escapeHtml(page)}
            </button>`;
        }
    );
}

async function performChat(query) {
    if (!currentNotebookId) {
        addMessage('system', 'Please select a notebook first.');
        return;
    }
    const thinking = document.createElement('div');
    thinking.className = 'message assistant thinking';
    thinking.textContent = '…';
    chatHistory.appendChild(thinking);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    try {
        const resp = await fetch('/api/v1/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, notebook_id: currentNotebookId }),
        });
        thinking.remove();

        if (!resp.ok) {
            const err = await resp.json();
            addMessage('system', `Error ${resp.status}: ${err.detail}`);
            return;
        }
        const data = await resp.json();
        window.currentCitations = data.citations;
        addMessage('assistant', data.answer, data.citations, data.is_fully_verified);
    } catch (err) {
        thinking.remove();
        addMessage('system', 'Error: Failed to connect to local brain.');
    }
}

// ---------------------------------------------------------------------------
// Chat History (S-20)
// ---------------------------------------------------------------------------
async function loadChatHistory(notebookId) {
    try {
        const resp = await fetch(`/api/v1/notebooks/${notebookId}/history?limit=50`);
        if (!resp.ok) return;
        const messages = await resp.json();
        if (!messages.length) return;
        clearChatUI();
        for (const msg of messages) {
            addMessage(msg.role, msg.content, msg.citations || [], msg.is_fully_verified);
        }
    } catch (e) {
        console.error('loadChatHistory error', e);
    }
}

function clearChatUI() {
    chatHistory.innerHTML = `<div class="message system">Hello. I'm your Intelligent Engineering Assistant. Select a notebook and upload documents, then ask questions.</div>`;
}

clearHistoryBtn.addEventListener('click', async () => {
    if (!currentNotebookId) return;
    if (!confirm('Clear all chat history for this notebook?')) return;
    await fetch(`/api/v1/notebooks/${currentNotebookId}/history`, { method: 'DELETE' });
    clearChatUI();
});

// ---------------------------------------------------------------------------
// Notes (S-20)
// ---------------------------------------------------------------------------
async function loadNotes(notebookId) {
    if (!notebookId) return;
    try {
        const resp = await fetch(`/api/v1/notebooks/${notebookId}/notes`);
        renderNotes(await resp.json());
    } catch (e) {
        console.error('loadNotes error', e);
    }
}

function renderNotes(notes) {
    if (!notes.length) {
        notesList.innerHTML = '<p class="empty-hint">No saved notes</p>';
        return;
    }
    notesList.innerHTML = '';
    for (const note of [...notes].reverse()) {
        const div = document.createElement('div');
        div.className = 'note-item';
        const date = new Date(note.created_at).toLocaleDateString();
        div.innerHTML = `
            <div class="note-title">${escapeHtml(note.title)}</div>
            <div class="note-meta">${escapeHtml(date)}</div>
            <div class="note-actions">
                <button class="toolbar-btn" onclick="expandNote('${note.id}')">View</button>
                <button class="toolbar-btn danger" onclick="deleteNote('${note.id}')">&#128465;</button>
            </div>
        `;
        notesList.appendChild(div);
    }
}

window.expandNote = async (noteId) => {
    if (!currentNotebookId) return;
    const resp = await fetch(`/api/v1/notebooks/${currentNotebookId}/notes/${noteId}`);
    const note = await resp.json();
    addMessage('assistant', note.content, note.citations || []);
};

window.deleteNote = async (noteId) => {
    if (!currentNotebookId) return;
    await fetch(`/api/v1/notebooks/${currentNotebookId}/notes/${noteId}`, { method: 'DELETE' });
    await loadNotes(currentNotebookId);
};

async function saveNote(content, citations) {
    if (!currentNotebookId) return;
    try {
        await fetch(`/api/v1/notebooks/${currentNotebookId}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, citations }),
        });
        await loadNotes(currentNotebookId);
    } catch (e) {
        console.error('saveNote error', e);
    }
}

refreshNotesBtn.addEventListener('click', () => {
    if (currentNotebookId) loadNotes(currentNotebookId);
});

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escapeAttr(str) {
    return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}
