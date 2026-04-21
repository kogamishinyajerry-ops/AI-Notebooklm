const STORAGE_KEYS = {
    apiKey: 'comac.apiKey',
    lastNotebook: 'comac.lastNotebook',
};

const STEP_IDS = ['prepare', 'qa', 'export'];
const STUDIO_TYPE_LABELS = {
    summary: '执行摘要',
    faq: 'FAQ',
    briefing: '技术简报',
    glossary: '术语表',
    action_items: '行动项',
};
const WELCOME_MESSAGE = '先准备资料，再在这里提出问题并查看带出处的回答。';
const DEMO_NOTEBOOK_PATTERNS = [/obsidian candidate workspace/i, /\bdemo\b/i, /立项\s*demo/i];

let currentStep = 'prepare';
let currentNotebookId = null;
let currentNotebookName = null;
let currentSourceId = null;
let currentPage = 1;
let totalPages = 0;
let currentPageWidth = 595;
let currentPageHeight = 842;
let cachedNotebooks = [];
let currentNotes = [];
let currentStudioOutputs = [];
let lastSources = [];
let currentViewerKey = null;
let highlightedNoteId = null;
let shouldScrollHighlightedNote = false;
let highlightTimer = null;
let toastTimer = null;
let pageRetryState = null;
let obsidianState = {
    available: false,
    vault_name: null,
    vault_path: null,
    export_root: null,
};
let platformState = {
    backend: {
        checked: false,
        available: false,
        reason: '后端未连接。',
    },
    llm: {
        checked: false,
        available: false,
        provider: 'local',
        model_name: null,
        configured_url: null,
        is_external_validation: false,
        reason: '尚未检查推理状态。',
        status: 'unknown',
    },
};
let demoState = {
    available: false,
    ready: false,
    notebook: null,
    source: null,
    questions: [],
};
const promptedNoteSaveNotebooks = new Set();

window.currentCitations = [];
window.currentEvidence = [];

const demoStartBtn = document.getElementById('demo-start-btn');
const notebookSelect = document.getElementById('notebook-select');
const newNotebookNameInput = document.getElementById('new-notebook-name');
const createNotebookBtn = document.getElementById('create-notebook-btn');
const uploadInput = document.getElementById('upload-input');
const uploadLabel = document.getElementById('upload-label');
const prepareHint = document.getElementById('prepare-hint');
const prepareEmptyState = document.getElementById('prepare-empty-state');
const prepareBlocker = document.getElementById('prepare-blocker');
const prepareBlockerTitle = document.getElementById('prepare-blocker-title');
const prepareBlockerText = document.getElementById('prepare-blocker-text');
const prepareBlockerAction = document.getElementById('prepare-blocker-action');
const sourceList = document.getElementById('source-list');
const notebookMeta = document.getElementById('notebook-meta');
const sourceMeta = document.getElementById('source-meta');
const notebookChip = document.getElementById('notebook-chip');
const vaultStatusPill = document.getElementById('vault-status-pill');
const prevPageBtn = document.getElementById('prev-page');
const nextPageBtn = document.getElementById('next-page');
const pageNav = document.getElementById('page-nav');
const pageIndicator = document.getElementById('page-indicator');
const pdfTitle = document.getElementById('pdf-title');
const pdfCanvas = document.getElementById('pdf-canvas');
const pdfPlaceholder = document.getElementById('pdf-placeholder');
const canvasWrapper = document.getElementById('canvas-wrapper');
const highlightOverlay = document.getElementById('highlight-overlay');
const retryPageBtn = document.getElementById('retry-page-btn');
const workspaceHint = document.getElementById('workspace-hint');
const demoQuestionStrip = document.getElementById('demo-question-strip');
const demoQuestionList = document.getElementById('demo-question-list');
const qaBlocker = document.getElementById('qa-blocker');
const qaBlockerTitle = document.getElementById('qa-blocker-title');
const qaBlockerText = document.getElementById('qa-blocker-text');
const qaBlockerAction = document.getElementById('qa-blocker-action');
const chatHistory = document.getElementById('chat-history');
const queryInput = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');
const clearHistoryBtn = document.getElementById('clear-history-btn');
const qaMenu = document.getElementById('qa-menu');
const notesList = document.getElementById('notes-list');
const noteViewer = document.getElementById('note-viewer');
const noteViewerTitle = document.getElementById('note-viewer-title');
const noteViewerMeta = document.getElementById('note-viewer-meta');
const noteViewerBody = document.getElementById('note-viewer-body');
const advancedToggle = document.getElementById('advanced-toggle');
const advancedContent = document.getElementById('advanced-content');
const studioTypeSelect = document.getElementById('studio-type-select');
const generateBtn = document.getElementById('generate-btn');
const studioList = document.getElementById('studio-list');
const generateGraphBtn = document.getElementById('generate-graph-btn');
const graphStatus = document.getElementById('graph-status');
const mindmapSvg = document.getElementById('mindmap-svg');
const settingsToggle = document.getElementById('settings-toggle');
const settingsCloseBtn = document.getElementById('settings-close-btn');
const settingsDrawer = document.getElementById('settings-drawer');
const settingsBackdrop = document.getElementById('settings-backdrop');
const apiKeyInput = document.getElementById('api-key-input');
const saveApiKeyBtn = document.getElementById('save-api-key-btn');
const authChip = document.getElementById('auth-chip');
const authStatus = document.getElementById('auth-status');
const vaultStatus = document.getElementById('vault-status');
const vaultMeta = document.getElementById('vault-meta');
const openVaultBtn = document.getElementById('open-vault-btn');
const backendChip = document.getElementById('backend-chip');
const backendMeta = document.getElementById('backend-meta');
const llmChip = document.getElementById('llm-chip');
const llmMeta = document.getElementById('llm-meta');
const toast = document.getElementById('toast');

(async function init() {
    bindEvents();
    apiKeyInput.value = getApiKey();
    updateAuthState(getApiKey() ? 'attached' : 'open');
    clearChatUI(true);
    renderSources([]);
    renderNotes([]);
    renderStudioOutputs([]);
    renderViewer(null);
    switchStep('prepare');
    await refreshPlatformHealth({ reloadWorkspace: true, silent: true });
    await loadDemoStatus();
    updateWorkspaceStatus();
})();

function bindEvents() {
    for (const step of STEP_IDS) {
        const button = document.getElementById(`step-${step}-btn`);
        button.addEventListener('click', () => handleStepSelection(step));
    }

    notebookSelect.addEventListener('change', async () => {
        const notebookId = notebookSelect.value;
        if (!notebookId) {
            resetNotebookContext();
            return;
        }
        await selectNotebook(notebookId);
    });

    createNotebookBtn.addEventListener('click', createNotebook);
    newNotebookNameInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            createNotebook();
        }
    });

    uploadInput.addEventListener('change', handleUpload);
    demoStartBtn.addEventListener('click', startDemo);
    prevPageBtn.addEventListener('click', async () => {
        if (!currentSourceId || currentPage <= 1) {
            return;
        }
        currentPage -= 1;
        updatePageNav();
        await renderPage(currentSourceId, currentPage);
    });
    nextPageBtn.addEventListener('click', async () => {
        if (!currentSourceId || currentPage >= totalPages) {
            return;
        }
        currentPage += 1;
        updatePageNav();
        await renderPage(currentSourceId, currentPage);
    });
    retryPageBtn.addEventListener('click', async () => {
        if (!pageRetryState?.sourceId || !pageRetryState?.pageNumber) {
            return;
        }
        await renderPage(pageRetryState.sourceId, pageRetryState.pageNumber);
    });

    queryInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            submitQuery();
        }
    });
    sendBtn.addEventListener('click', submitQuery);
    prepareBlockerAction.addEventListener('click', async () => {
        await refreshPlatformHealth({ reloadWorkspace: true, silent: false });
    });
    qaBlockerAction.addEventListener('click', async () => {
        await refreshPlatformHealth({ reloadWorkspace: true, silent: false });
    });
    clearHistoryBtn.addEventListener('click', async () => {
        qaMenu.open = false;
        await clearHistory();
    });

    advancedToggle.addEventListener('click', toggleAdvancedContent);
    generateBtn.addEventListener('click', generateStudioOutput);
    generateGraphBtn.addEventListener('click', generateGraph);

    settingsToggle.addEventListener('click', openSettingsDrawer);
    settingsCloseBtn.addEventListener('click', closeSettingsDrawer);
    settingsBackdrop.addEventListener('click', closeSettingsDrawer);

    apiKeyInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            saveApiKey();
        }
    });
    saveApiKeyBtn.addEventListener('click', saveApiKey);
    openVaultBtn.addEventListener('click', openVault);

    document.addEventListener('click', (event) => {
        if (qaMenu.open && !qaMenu.contains(event.target)) {
            qaMenu.open = false;
        }
        document.querySelectorAll('.note-overflow[open]').forEach((node) => {
            if (!node.contains(event.target)) {
                node.open = false;
            }
        });
    });
}

function getApiKey() {
    return localStorage.getItem(STORAGE_KEYS.apiKey) || '';
}

function setApiKey(value) {
    const trimmed = value.trim();
    if (trimmed) {
        localStorage.setItem(STORAGE_KEYS.apiKey, trimmed);
    } else {
        localStorage.removeItem(STORAGE_KEYS.apiKey);
    }
}

function getDefaultHeaders() {
    const headers = new Headers();
    const apiKey = getApiKey();
    if (apiKey) {
        headers.set('X-API-Key', apiKey);
    }
    return headers;
}

async function apiFetch(url, options = {}) {
    const headers = getDefaultHeaders();
    const extraHeaders = new Headers(options.headers || {});
    extraHeaders.forEach((value, key) => headers.set(key, value));
    return fetch(url, { ...options, headers });
}

async function parseApiResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    let payload = null;

    if (contentType.includes('application/json')) {
        try {
            payload = await response.json();
        } catch (_) {
            payload = null;
        }
    } else {
        try {
            payload = await response.text();
        } catch (_) {
            payload = null;
        }
    }

    if (!response.ok) {
        const message =
            (payload && typeof payload === 'object' && (payload.detail || payload.message)) ||
            (typeof payload === 'string' && payload) ||
            `HTTP ${response.status}`;
        const error = new Error(message);
        error.status = response.status;
        error.payload = payload;
        throw error;
    }

    return payload;
}

async function apiJson(url, options = {}) {
    const response = await apiFetch(url, options);
    return parseApiResponse(response);
}

async function fetchJsonAllowError(url, options = {}) {
    try {
        const response = await apiFetch(url, options);
        const contentType = response.headers.get('content-type') || '';
        let payload = null;
        if (contentType.includes('application/json')) {
            try {
                payload = await response.json();
            } catch (_) {
                payload = null;
            }
        } else {
            try {
                payload = await response.text();
            } catch (_) {
                payload = null;
            }
        }
        return { ok: response.ok, status: response.status, payload };
    } catch (error) {
        return { ok: false, status: 0, payload: null, error };
    }
}

function isCurrentDemoNotebook() {
    return Boolean(
        demoState.ready &&
        demoState.notebook &&
        currentNotebookId === demoState.notebook.id
    );
}

function renderDemoState() {
    demoStartBtn.hidden = !demoState.available;
    demoStartBtn.textContent = demoState.ready ? '进入立项 Demo' : '准备立项 Demo';

    const showQuestions = isCurrentDemoNotebook() && demoState.questions.length > 0;
    demoQuestionStrip.hidden = !showQuestions;
    demoQuestionList.innerHTML = '';

    if (!showQuestions) {
        return;
    }

    for (const question of demoState.questions) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'demo-question-btn';
        button.textContent = question;
        button.addEventListener('click', () => runDemoQuestion(question));
        demoQuestionList.appendChild(button);
    }
}

async function loadDemoStatus() {
    const result = await fetchJsonAllowError('/api/v1/demo/status');
    if (result.status === 404) {
        demoState = {
            available: false,
            ready: false,
            notebook: null,
            source: null,
            questions: [],
        };
        renderDemoState();
        return;
    }

    if (!result.ok || !result.payload || typeof result.payload !== 'object') {
        demoState = {
            ...demoState,
            available: false,
        };
        renderDemoState();
        return;
    }

    demoState = {
        available: true,
        ready: Boolean(result.payload.ready),
        notebook: result.payload.notebook || null,
        source: result.payload.source || null,
        questions: Array.isArray(result.payload.questions) ? result.payload.questions : [],
    };
    renderDemoState();
}

async function startDemo() {
    if (!platformState.backend.available) {
        showToast(platformState.backend.reason || '后端未连接，无法准备 Demo。', 'error');
        return;
    }

    demoStartBtn.disabled = true;
    demoStartBtn.textContent = '准备中…';

    try {
        const payload = await apiJson('/api/v1/demo/seed', { method: 'POST' });
        demoState = {
            available: true,
            ready: Boolean(payload.ready),
            notebook: payload.notebook || null,
            source: payload.source || null,
            questions: Array.isArray(payload.questions) ? payload.questions : [],
        };
        await Promise.all([loadObsidianStatus(), loadNotebooks()]);
        if (demoState.notebook?.id) {
            notebookSelect.value = demoState.notebook.id;
            await selectNotebook(demoState.notebook.id, {
                preferredSourceId: demoState.source?.id || null,
            });
        }
        renderDemoState();
        if (currentSourceId && hasReadySources()) {
            switchStep('qa');
        }
        showToast('立项 Demo 已就绪：可直接点击推荐问题。');
    } catch (error) {
        showToast(`准备立项 Demo 失败：${error.message}`, 'error');
    } finally {
        demoStartBtn.disabled = false;
        renderDemoState();
    }
}

function runDemoQuestion(question) {
    if (!currentNotebookId || !hasReadySources()) {
        showToast('Demo 资料尚未就绪，请先点击“进入立项 Demo”。', 'error');
        return;
    }
    switchStep('qa');
    queryInput.value = question;
    submitQuery();
}

function normalizeSourceStatus(source) {
    return String(source?.status || '').trim().toLowerCase();
}

function getSourceStatusMeta(source) {
    const normalized = normalizeSourceStatus(source);

    if (normalized === 'ready' && source?.chunk_count === 0) {
        return {
            normalized: 'failed',
            label: '失败',
            chipClass: 'danger',
            hint: '资料未生成可检索片段，请重新上传可复制文本的 PDF。',
        };
    }

    if (normalized === 'ready') {
        return {
            normalized: 'ready',
            label: 'READY',
            chipClass: 'success',
            hint: '资料已就绪，可进入 Step 2 提问验证。',
        };
    }

    if (normalized === 'uploading') {
        return {
            normalized: 'uploading',
            label: '上传中',
            chipClass: 'muted',
            hint: '文件仍在上传，请稍后。',
        };
    }

    if (normalized === 'processing') {
        return {
            normalized: 'processing',
            label: '处理中',
            chipClass: 'warning',
            hint: '系统正在解析并建立索引，完成后才可预览和提问。',
        };
    }

    if (normalized === 'failed') {
        return {
            normalized: 'failed',
            label: '失败',
            chipClass: 'danger',
            hint: source?.error_message || '处理失败，请重新上传。',
        };
    }

    return {
        normalized: normalized || 'unknown',
        label: source?.status || '未知',
        chipClass: 'muted',
        hint: '当前资料状态未知，请稍后刷新。',
    };
}

function isDemoNotebook(notebook) {
    const label = `${notebook?.name || ''} ${notebook?.id || ''}`;
    return DEMO_NOTEBOOK_PATTERNS.some((pattern) => pattern.test(label));
}

function sortNotebooksByRecency(notebooks) {
    return [...notebooks].sort((left, right) => {
        const leftValue = Date.parse(left?.updated_at || left?.created_at || '') || 0;
        const rightValue = Date.parse(right?.updated_at || right?.created_at || '') || 0;
        return rightValue - leftValue;
    });
}

function selectPreferredNotebookId(notebooks) {
    if (!notebooks.length) {
        return null;
    }

    if (currentNotebookId && notebooks.some((item) => item.id === currentNotebookId)) {
        return currentNotebookId;
    }

    const lastNotebookId = localStorage.getItem(STORAGE_KEYS.lastNotebook);
    const lastNotebook = notebooks.find((item) => item.id === lastNotebookId);
    if (lastNotebook && !isDemoNotebook(lastNotebook)) {
        return lastNotebook.id;
    }

    const latestRealNotebook = sortNotebooksByRecency(notebooks).find((item) => !isDemoNotebook(item));
    if (latestRealNotebook) {
        return latestRealNotebook.id;
    }

    if (lastNotebook) {
        return lastNotebook.id;
    }

    return sortNotebooksByRecency(notebooks)[0]?.id || notebooks[notebooks.length - 1]?.id || null;
}

function describeErrorPayload(payload, fallback) {
    if (payload && typeof payload === 'object') {
        return payload.unavailable_reason || payload.detail || payload.message || payload.error || fallback;
    }
    if (typeof payload === 'string' && payload) {
        return payload;
    }
    return fallback;
}

function updateConnectivityState() {
    backendChip.className = `status-chip ${platformState.backend.available ? 'success' : 'danger'}`;
    backendChip.textContent = platformState.backend.available ? '已连接' : '未连接';
    backendMeta.textContent = platformState.backend.available
        ? 'API 服务正常，可加载 Notebook、资料与导出能力。'
        : platformState.backend.reason;

    const llmProviderLabel = platformState.llm.provider === 'minimax'
        ? 'MiniMax 临时验证'
        : '本地推理';
    let llmChipClass = 'danger';
    let llmChipText = '不可用';
    if (platformState.llm.available) {
        llmChipClass = platformState.llm.is_external_validation ? 'warning' : 'success';
        llmChipText = platformState.llm.is_external_validation ? '临时外部验证' : '可用';
    } else if (platformState.llm.status === 'misconfigured') {
        llmChipClass = 'warning';
        llmChipText = '配置缺失';
    }

    llmChip.className = `status-chip ${llmChipClass}`;
    llmChip.textContent = llmChipText;

    const metaParts = [llmProviderLabel];
    if (platformState.llm.model_name) {
        metaParts.push(platformState.llm.model_name);
    }
    if (platformState.llm.configured_url) {
        metaParts.push(platformState.llm.configured_url);
    }
    if (platformState.llm.available) {
        llmMeta.textContent = `${metaParts.join(' · ')}。`;
        return;
    }
    llmMeta.textContent = `${metaParts.join(' · ')}${metaParts.length ? '。' : ''}${platformState.llm.reason ? ` ${platformState.llm.reason}` : ''}`;
}

function updateQaBlocker() {
    const hasReadySource = hasReadySources();
    qaBlocker.classList.remove('warning');

    if (!platformState.backend.available) {
        qaBlocker.hidden = false;
        qaBlockerTitle.textContent = '后端未连接';
        qaBlockerText.textContent = platformState.backend.reason || '本地 API 服务未启动，Step 2 暂不可用。';
        qaBlockerAction.textContent = '重新检查连接';
        return;
    }

    if (hasReadySource && !platformState.llm.available) {
        qaBlocker.hidden = false;
        qaBlocker.classList.add('warning');
        qaBlockerTitle.textContent = '推理服务不可用';
        qaBlockerText.textContent = platformState.llm.reason || '当前无法生成回答，请先修复推理配置或服务连接。';
        qaBlockerAction.textContent = '重新检查推理';
        return;
    }

    qaBlocker.hidden = true;
}

function updatePrepareBlocker() {
    if (platformState.backend.available) {
        prepareBlocker.hidden = true;
        return;
    }

    prepareBlocker.hidden = false;
    prepareBlockerTitle.textContent = '后端未连接';
    prepareBlockerText.textContent = platformState.backend.reason || '本地 API 服务未启动，当前无法选择 Notebook、上传 PDF 或进入 Demo。';
}

async function refreshPlatformHealth({ reloadWorkspace = false, silent = false } = {}) {
    const backendResult = await fetchJsonAllowError('/api/v1/health');
    if (!backendResult.ok) {
        platformState.backend = {
            checked: true,
            available: false,
            reason: backendResult.error
                ? '无法连接本地 API 服务，请确认 http://127.0.0.1:8012 已启动。'
                : describeErrorPayload(backendResult.payload, `后端检查失败（HTTP ${backendResult.status}）。`),
        };
        platformState.llm = {
            checked: true,
            available: false,
            provider: platformState.llm.provider || 'local',
            model_name: platformState.llm.model_name,
            configured_url: platformState.llm.configured_url,
            is_external_validation: platformState.llm.is_external_validation,
            reason: '后端未连接，暂时无法检查推理状态。',
            status: 'backend_unreachable',
        };
        updateConnectivityState();
        syncControls();
        if (!silent) {
            showToast(platformState.backend.reason, 'error');
        }
        return;
    }

    platformState.backend = {
        checked: true,
        available: true,
        reason: null,
    };

    const llmResult = await fetchJsonAllowError('/api/v1/llm/health');
    const llmPayload = llmResult.payload && typeof llmResult.payload === 'object' ? llmResult.payload : {};
    platformState.llm = {
        checked: true,
        available: llmPayload.available === true || llmPayload.status === 'ok',
        provider: llmPayload.provider || 'local',
        model_name: llmPayload.model_name || null,
        configured_url: llmPayload.configured_url || null,
        is_external_validation: Boolean(llmPayload.is_external_validation),
        reason: llmPayload.unavailable_reason || llmPayload.error || null,
        status: llmPayload.status || (llmResult.ok ? 'ok' : 'unreachable'),
    };

    updateConnectivityState();
    if (reloadWorkspace) {
        await Promise.all([loadObsidianStatus(), loadNotebooks()]);
    }
    syncControls();
}

function handleStepSelection(step) {
    if (step === 'qa' && !hasReadySources()) {
        showToast('先在 Step 1 上传至少一份 READY 资料。', 'error');
        switchStep('prepare');
        return;
    }
    if (step === 'export' && !currentNotebookId) {
        showToast('先选择一个 Notebook。', 'error');
        switchStep('prepare');
        return;
    }
    switchStep(step);
}

function switchStep(step) {
    currentStep = step;
    for (const item of STEP_IDS) {
        const section = document.getElementById(`step-${item}`);
        const button = document.getElementById(`step-${item}-btn`);
        section.classList.toggle('visible', item === step);
        button.classList.toggle('active', item === step);
    }
}

function updateAuthState(mode) {
    authChip.className = 'status-chip';

    if (mode === 'required') {
        authChip.classList.add('warning');
        authChip.textContent = '需要认证';
        authStatus.textContent = '当前服务要求 X-API-Key。请保存可用的 API Key。';
        return;
    }

    if (mode === 'attached') {
        authChip.classList.add('success');
        authChip.textContent = '已附加 API Key';
        authStatus.textContent = '后续请求会自动携带 X-API-Key。';
        return;
    }

    authChip.classList.add('muted');
    authChip.textContent = '开放模式';
    authStatus.textContent = '当前可直接体验；启用认证后可在此附加 API Key。';
}

function updateVaultState() {
    if (!obsidianState.available) {
        vaultStatus.textContent = '未检测到本地 vault';
        vaultMeta.textContent = '导出入口已保留，但需要本地 Obsidian vault 才能真正落盘。';
        vaultStatusPill.textContent = 'Obsidian 未检测';
        vaultStatusPill.className = 'status-chip muted';
        openVaultBtn.disabled = true;
        return;
    }

    vaultStatus.textContent = obsidianState.vault_name;
    vaultMeta.textContent = `导出目录：${obsidianState.export_root || 'COMAC Intelligent NotebookLM'} · ${obsidianState.vault_path}`;
    vaultStatusPill.textContent = `Obsidian：${obsidianState.vault_name}`;
    vaultStatusPill.className = 'status-chip success';
    openVaultBtn.disabled = false;
}

function updateWorkspaceStatus() {
    if (!currentNotebookId) {
        notebookMeta.textContent = '未选择 Notebook';
        notebookChip.textContent = 'Notebook：未选择';
        sourceMeta.textContent = '0 份资料';
        prepareHint.textContent = '先选择或新建 Notebook，再上传资料。';
        workspaceHint.textContent = platformState.backend.available
            ? '上传资料后，在这里提出问题并查看带出处的回答。'
            : '后端未连接时，Step 2 只显示阻塞提示。';
        syncControls();
        return;
    }

    notebookMeta.textContent = currentNotebookName || currentNotebookId;
    notebookChip.textContent = `Notebook：${currentNotebookName || currentNotebookId}`;
    sourceMeta.textContent = `${lastSources.length} 份资料`;

    if (!lastSources.length) {
        prepareHint.textContent = '当前 Notebook 还没有资料，请上传 PDF。';
        workspaceHint.textContent = '当前 Notebook 为空；请先回到 Step 1 上传资料。';
        syncControls();
        return;
    }

    const readyCount = lastSources.filter(isReadySource).length;
    prepareHint.textContent = readyCount
        ? `已接入 ${lastSources.length} 份资料，其中 ${readyCount} 份可检索。`
        : `已接入 ${lastSources.length} 份资料，正在等待处理完成。`;
    workspaceHint.textContent = currentSourceId
        ? '左侧证据页与回答中的引用跳转保持联动。'
        : '选择一份 READY 资料后，即可开始提问验证。';

    syncControls();
}

function syncControls() {
    const hasNotebook = Boolean(currentNotebookId);
    const hasReadySource = hasReadySources();
    const backendAvailable = platformState.backend.available;
    const llmAvailable = platformState.llm.available;
    const canQuery = hasReadySource && backendAvailable && llmAvailable;
    const canPrepare = backendAvailable;

    demoStartBtn.disabled = !backendAvailable || !demoState.available;
    notebookSelect.disabled = !canPrepare;
    newNotebookNameInput.disabled = !canPrepare;
    createNotebookBtn.disabled = !canPrepare;
    uploadLabel.classList.toggle('disabled', !hasNotebook || !canPrepare);
    queryInput.disabled = !canQuery;
    sendBtn.disabled = !canQuery;
    advancedToggle.disabled = !hasReadySource || !backendAvailable;
    generateBtn.disabled = !canQuery;
    generateGraphBtn.disabled = !hasReadySource || !backendAvailable;
    document.getElementById('step-qa-btn').disabled = !hasReadySource;
    document.getElementById('step-export-btn').disabled = !hasNotebook || !backendAvailable;

    if (!hasNotebook) {
        resetPdfViewer('等待载入资料', '选择一份已就绪资料后，这里会显示证据页。');
    }
    updatePrepareBlocker();
    updateQaBlocker();
    updateQaMenuVisibility();
}

async function loadObsidianStatus() {
    try {
        const status = await apiJson('/api/v1/integrations/obsidian/status');
        obsidianState = status;
    } catch (_) {
        obsidianState = { available: false };
    }
    updateVaultState();
    renderNotes(currentNotes);
    renderStudioOutputs(currentStudioOutputs);
}

function openVault() {
    if (!obsidianState.available || !obsidianState.vault_name) {
        showToast('当前没有可用的本地 Obsidian vault。', 'error');
        return;
    }
    openExternal(`obsidian://open?vault=${encodeURIComponent(obsidianState.vault_name)}`);
}

function saveApiKey() {
    setApiKey(apiKeyInput.value);
    apiKeyInput.value = getApiKey();
    updateAuthState(getApiKey() ? 'attached' : 'open');
    showToast(getApiKey() ? '已保存 API Key。' : '已清除本地保存的 API Key。');
    void loadNotebooks();
}

function openSettingsDrawer() {
    settingsDrawer.hidden = false;
    settingsBackdrop.hidden = false;
}

function closeSettingsDrawer() {
    settingsDrawer.hidden = true;
    settingsBackdrop.hidden = true;
}

async function loadNotebooks() {
    if (!platformState.backend.available) {
        cachedNotebooks = [];
        notebookSelect.innerHTML = '<option value="">请选择</option>';
        syncControls();
        return;
    }
    try {
        const notebooks = await apiJson('/api/v1/notebooks');
        cachedNotebooks = Array.isArray(notebooks) ? notebooks : [];
        notebookSelect.innerHTML = '<option value="">请选择</option>';

        for (const notebook of cachedNotebooks) {
            const option = document.createElement('option');
            option.value = notebook.id;
            option.textContent = notebook.name;
            notebookSelect.appendChild(option);
        }

        updateAuthState(getApiKey() ? 'attached' : 'open');

        const preferredNotebookId = selectPreferredNotebookId(cachedNotebooks);

        if (preferredNotebookId && cachedNotebooks.some((item) => item.id === preferredNotebookId)) {
            notebookSelect.value = preferredNotebookId;
            await selectNotebook(preferredNotebookId);
            return;
        }

        if (!cachedNotebooks.length) {
            resetNotebookContext();
        }
    } catch (error) {
        cachedNotebooks = [];
        notebookSelect.innerHTML = '<option value="">请选择</option>';
        if (error.status === 401 || error.status === 403) {
            updateAuthState('required');
        }
        resetNotebookContext();
        showToast(`加载 Notebook 失败：${error.message}`, 'error');
    }
}

async function createNotebook() {
    const name = newNotebookNameInput.value.trim();
    if (!name) {
        showToast('Notebook 名称不能为空。', 'error');
        return;
    }

    try {
        const notebook = await apiJson('/api/v1/notebooks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        newNotebookNameInput.value = '';
        showToast(`已创建 Notebook：${notebook.name}`);
        await loadNotebooks();
        notebookSelect.value = notebook.id;
        await selectNotebook(notebook.id);
    } catch (error) {
        if (error.status === 401 || error.status === 403) {
            updateAuthState('required');
        }
        showToast(`创建 Notebook 失败：${error.message}`, 'error');
    }
}

async function selectNotebook(notebookId, options = {}) {
    currentNotebookId = notebookId;
    const notebook = cachedNotebooks.find((item) => item.id === notebookId);
    currentNotebookName = notebook?.name || notebookId;
    localStorage.setItem(STORAGE_KEYS.lastNotebook, notebookId);
    currentSourceId = null;
    currentPage = 1;
    totalPages = 0;
    window.currentCitations = [];
    window.currentEvidence = [];
    highlightedNoteId = null;
    shouldScrollHighlightedNote = false;
    clearHighlight();
    renderViewer(null);

    await Promise.all([
        loadSources(notebookId, { preferredSourceId: options.preferredSourceId || null }),
        loadChatHistory(notebookId),
        loadNotes(notebookId),
        loadStudioOutputs(notebookId),
    ]);

    if (hasReadySources()) {
        switchStep('qa');
    } else {
        switchStep('prepare');
    }
    renderDemoState();
    updateWorkspaceStatus();
}

function resetNotebookContext() {
    currentNotebookId = null;
    currentNotebookName = null;
    currentSourceId = null;
    currentPage = 1;
    totalPages = 0;
    lastSources = [];
    currentNotes = [];
    currentStudioOutputs = [];
    currentViewerKey = null;
    highlightedNoteId = null;
    shouldScrollHighlightedNote = false;
    window.currentEvidence = [];
    localStorage.removeItem(STORAGE_KEYS.lastNotebook);
    clearChatUI(true);
    renderSources([]);
    renderNotes([]);
    renderStudioOutputs([]);
    renderViewer(null);
    resetPdfViewer('等待载入资料', '选择一份已就绪资料后，这里会显示证据页。');
    renderDemoState();
    switchStep('prepare');
    updateWorkspaceStatus();
}

function isReadySource(source) {
    const normalized = normalizeSourceStatus(source);
    if (normalized !== 'ready') {
        return false;
    }
    if (source?.chunk_count == null) {
        return true;
    }
    return Number(source.chunk_count) > 0;
}

function hasReadySources() {
    return lastSources.some(isReadySource);
}

async function loadSources(notebookId, options = {}) {
    if (!notebookId) {
        return;
    }
    try {
        const sources = await apiJson(`/api/v1/notebooks/${notebookId}/sources`);
        lastSources = Array.isArray(sources) ? sources : [];
        renderSources(lastSources);

        if (!lastSources.length) {
            currentSourceId = null;
            resetPdfViewer('等待载入资料', '选择一份已就绪资料后，这里会显示证据页。');
            updateWorkspaceStatus();
            return;
        }

        const preferredSourceId = options.preferredSourceId || null;
        const preferredSource =
            lastSources.find((item) => item.id === preferredSourceId) ||
            lastSources.find((item) => item.id === currentSourceId) ||
            lastSources.find(isReadySource) ||
            lastSources[0];

        if (preferredSource) {
            await openSource(preferredSource, { silent: true });
        }
    } catch (error) {
        showToast(`加载资料失败：${error.message}`, 'error');
    }
}

function renderSources(sources) {
    prepareEmptyState.classList.toggle('hidden', sources.length > 0);
    sourceList.innerHTML = '';

    if (!sources.length) {
        return;
    }

    for (const source of sources) {
        const statusMeta = getSourceStatusMeta(source);
        const node = document.createElement('button');
        node.type = 'button';
        node.className = `source-item${source.id === currentSourceId ? ' active' : ''}`;
        node.innerHTML = `
            <div class="source-main">
                <span class="source-name">${escapeHtml(source.filename)}</span>
                <span class="source-state">${escapeHtml(formatSourceState(source))}</span>
            </div>
            <span class="status-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.label)}</span>
        `;
        node.addEventListener('click', async () => {
            await openSource(source);
            if (isReadySource(source)) {
                switchStep('qa');
            }
        });
        sourceList.appendChild(node);
    }
}

function formatSourceState(source) {
    if (isReadySource(source) && source.page_count) {
        return `${source.page_count} 页 · ${source.chunk_count || 0} chunks`;
    }
    if (source.error_message) {
        return source.error_message;
    }
    return getSourceStatusMeta(source).hint;
}

async function openSource(source, options = {}) {
    currentSourceId = source.id;
    currentPage = 1;
    totalPages = source.page_count || 1;
    pageRetryState = null;
    renderSources(lastSources);
    updateWorkspaceStatus();

    const statusMeta = getSourceStatusMeta(source);
    if (!isReadySource(source)) {
        resetPdfViewer(source.filename, statusMeta.hint);
        if (!options.silent) {
            showToast(statusMeta.hint, 'error');
        }
        return;
    }

    pdfTitle.textContent = source.filename;
    pdfPlaceholder.hidden = true;
    canvasWrapper.hidden = false;
    updatePageNav();
    await renderPage(source.id, currentPage);
}

async function handleUpload(event) {
    if (!currentNotebookId) {
        showToast('请先选择或新建 Notebook。', 'error');
        uploadInput.value = '';
        return;
    }

    const file = event.target.files?.[0];
    if (!file) {
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    addMessage('system', `正在上传 ${file.name} …`);

    try {
        const response = await apiFetch(`/api/v1/notebooks/${currentNotebookId}/sources/upload`, {
            method: 'POST',
            body: formData,
        });
        const payload = await parseApiResponse(response);
        addMessage('system', `上传完成：${payload.filename}，已索引 ${payload.chunks_indexed} 个片段。`);
        await loadSources(currentNotebookId);
        switchStep(hasReadySources() ? 'qa' : 'prepare');
        showToast(`已上传 ${payload.filename}`);
    } catch (error) {
        addMessage('system', `上传失败：${error.message}`);
        await loadSources(currentNotebookId);
        showToast(`上传失败：${error.message}`, 'error');
    } finally {
        uploadInput.value = '';
    }
}

async function renderPage(sourceId, pageNumber) {
    try {
        const response = await apiFetch(
            `/api/v1/notebooks/${currentNotebookId}/sources/${sourceId}/pages/${pageNumber}`
        );
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const blob = await response.blob();
        const imageUrl = URL.createObjectURL(blob);
        const image = new Image();

        image.onload = () => {
            pdfCanvas.width = image.naturalWidth;
            pdfCanvas.height = image.naturalHeight;
            currentPageWidth = image.naturalWidth / 2;
            currentPageHeight = image.naturalHeight / 2;
            const context = pdfCanvas.getContext('2d');
            context.clearRect(0, 0, pdfCanvas.width, pdfCanvas.height);
            context.drawImage(image, 0, 0);
            URL.revokeObjectURL(imageUrl);
        };

        image.src = imageUrl;
        pageRetryState = null;
        retryPageBtn.hidden = true;
        pdfPlaceholder.hidden = true;
        canvasWrapper.hidden = false;
        pageIndicator.textContent = `${pageNumber} / ${totalPages}`;
    } catch (error) {
        pageRetryState = { sourceId, pageNumber };
        resetPdfViewer('预览不可用', '该页面暂时无法渲染，可重试；若仍失败，请重新上传资料。');
        retryPageBtn.hidden = false;
        showToast(`页面渲染失败：${error.message}`, 'error');
    }
}

function updatePageNav() {
    pageNav.hidden = totalPages <= 1;
    prevPageBtn.disabled = currentPage <= 1;
    nextPageBtn.disabled = currentPage >= totalPages;
    pageIndicator.textContent = totalPages ? `${currentPage} / ${totalPages}` : '— / —';
}

function resetPdfViewer(title, hint) {
    pdfTitle.textContent = title;
    pdfPlaceholder.querySelector('p').textContent = hint;
    pdfPlaceholder.hidden = false;
    canvasWrapper.hidden = true;
    retryPageBtn.hidden = pageRetryState == null;
    pageNav.hidden = true;
    pageIndicator.textContent = '— / —';
    prevPageBtn.disabled = true;
    nextPageBtn.disabled = true;
    clearHighlight();
}

window.showSource = async function showSource(src, page, bboxString) {
    if (!currentNotebookId) {
        return;
    }

    const citation = window.currentCitations.find(
        (item) => item.source_file === src && String(item.page_number) === String(page)
    );
    const bbox = citation?.bbox || parseBboxString(bboxString);

    const sources = lastSources.length
        ? lastSources
        : await apiJson(`/api/v1/notebooks/${currentNotebookId}/sources`);
    const matchedSource = sources.find((item) => item.filename === src);
    if (!matchedSource) {
        showToast('没有找到对应资料。', 'error');
        return;
    }

    switchStep('qa');
    await openSource(matchedSource, { silent: true });
    const targetPage = Number.parseInt(page, 10) || 1;
    currentPage = targetPage;
    totalPages = matchedSource.page_count || targetPage;
    updatePageNav();
    await renderPage(matchedSource.id, currentPage);

    if (bbox) {
        window.setTimeout(() => applyHighlight(bbox), 180);
    }
};

function parseBboxString(value) {
    if (!value) {
        return null;
    }
    const values = String(value).split(',').map(Number);
    return values.length === 4 && values.every((item) => !Number.isNaN(item))
        ? values
        : null;
}

function applyHighlight(bbox) {
    if (!bbox || bbox.length !== 4) {
        return;
    }
    clearHighlight();

    const displayWidth = pdfCanvas.offsetWidth || pdfCanvas.width;
    const displayHeight = pdfCanvas.offsetHeight || pdfCanvas.height;
    const scaleX = displayWidth / currentPageWidth;
    const scaleY = displayHeight / currentPageHeight;

    highlightOverlay.style.left = `${bbox[0] * scaleX}px`;
    highlightOverlay.style.top = `${bbox[1] * scaleY}px`;
    highlightOverlay.style.width = `${(bbox[2] - bbox[0]) * scaleX}px`;
    highlightOverlay.style.height = `${(bbox[3] - bbox[1]) * scaleY}px`;
    highlightOverlay.style.display = 'block';
    highlightOverlay.style.opacity = '1';

    if (highlightTimer) {
        window.clearTimeout(highlightTimer);
    }
    highlightTimer = window.setTimeout(clearHighlight, 3200);
}

function clearHighlight() {
    highlightOverlay.style.opacity = '0';
    window.setTimeout(() => {
        highlightOverlay.style.display = 'none';
    }, 220);
}

function submitQuery() {
    const query = queryInput.value.trim();
    if (!query) {
        return;
    }
    if (!platformState.backend.available) {
        showToast('后端未连接，当前无法提问。', 'error');
        return;
    }
    if (!platformState.llm.available) {
        showToast(platformState.llm.reason || '推理服务不可用。', 'error');
        return;
    }
    if (!currentNotebookId || !hasReadySources()) {
        addMessage('system', '请先在 Step 1 上传至少一份 READY 资料。');
        switchStep('prepare');
        return;
    }

    if (isOnlyWelcomeMessage()) {
        clearChatUI(false);
    }
    queryInput.value = '';
    addMessage('user', query);
    void performChat(query);
}

function isOnlyWelcomeMessage() {
    return (
        chatHistory.children.length === 1 &&
        chatHistory.firstElementChild?.classList.contains('system') &&
        chatHistory.firstElementChild?.textContent?.trim() === WELCOME_MESSAGE
    );
}

function clearChatUI(showWelcome) {
    chatHistory.innerHTML = showWelcome
        ? `<div class="message system">${WELCOME_MESSAGE}</div>`
        : '';
    updateQaMenuVisibility();
}

function addMessage(role, text, citations = [], isVerified = false, evidence = []) {
    const node = document.createElement('div');
    node.className = `message ${role}`;

    if (role === 'assistant') {
        node.innerHTML = [
            formatEvidencePanel(evidence),
            formatVerificationBadge(isVerified, citations),
            `<div class="answer-body">${formatAssistantResponse(text, citations)}</div>`,
        ].join('');
        const saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.className = 'save-note-btn';
        saveBtn.textContent = isVerified ? '保存为笔记' : '保存当前回答';
        saveBtn.addEventListener('click', () => {
            void saveNote(text, citations, saveBtn);
        });
        node.appendChild(saveBtn);
    } else {
        node.textContent = text;
    }

    chatHistory.appendChild(node);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    updateQaMenuVisibility();
}

function formatEvidencePanel(evidence = []) {
    if (!Array.isArray(evidence) || !evidence.length) {
        return '';
    }

    const items = evidence.slice(0, 3).map((item, index) => {
        const bboxString = item?.bbox ? item.bbox.join(',') : '';
        return `
            <button
                class="evidence-item"
                type="button"
                onclick="showSource('${escapeAttr(item.source_file)}', '${escapeAttr(item.page_number)}', '${escapeAttr(bboxString)}')"
            >
                <span class="evidence-rank">证据 ${index + 1}</span>
                <span class="evidence-source">${escapeHtml(item.source_file)} · 第 ${escapeHtml(item.page_number)} 页</span>
                <span class="evidence-snippet">${escapeHtml(item.snippet || '')}</span>
            </button>
        `;
    }).join('');

    return `
        <div class="evidence-panel">
            <div class="evidence-panel-title">先看系统检索到的证据</div>
            <div class="evidence-list">${items}</div>
        </div>
    `;
}

function formatVerificationBadge(isVerified, citations = []) {
    if (isVerified && citations.length) {
        return '<div class="verification-badge success">已验证引用：回答中的 citation 已通过来源页校验。</div>';
    }
    return '<div class="verification-badge warning">回答未通过引用门禁：可参考证据片段，但不要将其标记为已验证结论。</div>';
}

function formatAssistantResponse(text, citations = []) {
    const placeholders = [];
    const tokenized = String(text).replace(
        /<citation src=['"]([^'"]+)['"] page=['"]([^'"]+)['"]>(.*?)<\/citation>/gs,
        (_match, src, page) => {
            const citation = citations.find(
                (item) => item.source_file === src && String(item.page_number) === String(page)
            );
            const bboxString = citation?.bbox ? citation.bbox.join(',') : '';
            const index = placeholders.length;
            placeholders.push(
                `<button class="citation-btn" type="button" onclick="showSource('${escapeAttr(src)}', '${escapeAttr(page)}', '${escapeAttr(bboxString)}')">出处：${escapeHtml(src)} · 第 ${escapeHtml(page)} 页</button>`
            );
            return `__CITATION_${index}__`;
        }
    );

    let escaped = escapeHtml(tokenized).replace(/\n/g, '<br>');
    placeholders.forEach((html, index) => {
        escaped = escaped.replace(`__CITATION_${index}__`, html);
    });
    return escaped;
}

async function performChat(query) {
    const thinking = document.createElement('div');
    thinking.className = 'message thinking';
    thinking.textContent = '正在生成回答…';
    chatHistory.appendChild(thinking);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    try {
        const response = await apiJson('/api/v1/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, notebook_id: currentNotebookId }),
        });
        thinking.remove();
        window.currentCitations = response.citations || [];
        window.currentEvidence = response.evidence || [];
        addMessage(
            'assistant',
            response.answer,
            response.citations || [],
            response.is_fully_verified,
            response.evidence || [],
        );
        if (!promptedNoteSaveNotebooks.has(currentNotebookId)) {
            promptedNoteSaveNotebooks.add(currentNotebookId);
            addMessage('system', '回答已生成，可点击下方“保存为笔记”进入 Step 3。');
            showToast('回答已生成，可保存为笔记后导出到 Obsidian。');
        }
    } catch (error) {
        thinking.remove();
        if (error.status === 401 || error.status === 403) {
            updateAuthState('required');
        }
        if (error.status === 503) {
            await refreshPlatformHealth({ reloadWorkspace: false, silent: true });
        }
        addMessage('system', `提问失败：${error.message}`);
        showToast(`提问失败：${error.message}`, 'error');
    }
}

async function loadChatHistory(notebookId) {
    if (!notebookId) {
        return;
    }
    try {
        const messages = await apiJson(`/api/v1/notebooks/${notebookId}/history?limit=50`);
        if (!messages.length) {
            clearChatUI(true);
            return;
        }
        clearChatUI(false);
        for (const message of messages) {
            addMessage(
                message.role,
                message.content,
                message.citations || [],
                message.is_fully_verified,
            );
        }
        updateQaMenuVisibility();
    } catch (error) {
        showToast(`加载对话历史失败：${error.message}`, 'error');
    }
}

async function clearHistory() {
    if (!currentNotebookId) {
        return;
    }
    if (!window.confirm('确认清空当前 Notebook 的问答历史？')) {
        return;
    }

    try {
        await apiJson(`/api/v1/notebooks/${currentNotebookId}/history`, {
            method: 'DELETE',
        });
        clearChatUI(true);
        showToast('已清空问答历史。');
    } catch (error) {
        showToast(`清空历史失败：${error.message}`, 'error');
    }
}

async function loadNotes(notebookId) {
    if (!notebookId) {
        return;
    }
    try {
        const notes = await apiJson(`/api/v1/notebooks/${notebookId}/notes`);
        currentNotes = Array.isArray(notes) ? notes : [];
        renderNotes(currentNotes);
    } catch (error) {
        showToast(`加载笔记失败：${error.message}`, 'error');
    }
}

function renderNotes(notes) {
    notesList.innerHTML = '';

    if (!notes.length) {
        notesList.innerHTML = '<p class="field-hint">还没有笔记。先去 Step 2 生成回答并保存，再回来导出。</p>';
        if (!notes.some((note) => note.id === highlightedNoteId)) {
            highlightedNoteId = null;
            shouldScrollHighlightedNote = false;
        }
        return;
    }

    const obsidianUnavailableReason = getObsidianUnavailableReason();
    let highlightedNode = null;

    for (const note of [...notes].reverse()) {
        const exportDisabled = !obsidianState.available;
        const isHighlighted = note.id === highlightedNoteId;
        const node = document.createElement('div');
        node.className = `note-item${isHighlighted ? ' active' : ''}`;
        node.dataset.noteId = note.id;
        node.innerHTML = `
            <div>
                <div class="note-title">${escapeHtml(note.title)}</div>
                <div class="note-meta">${escapeHtml(formatDateTime(note.created_at))}</div>
            </div>
            <div class="note-actions">
                <button class="note-action-btn" type="button">查看</button>
                <button class="note-action-btn" type="button"${exportDisabled ? ' disabled' : ''}>导出到 Obsidian</button>
                <details class="note-overflow">
                    <summary class="note-action-btn">更多</summary>
                    <div class="menu-panel">
                        <button class="menu-item danger" type="button">删除</button>
                    </div>
                </details>
            </div>
            ${exportDisabled ? `<div class="field-hint note-inline-hint">${escapeHtml(obsidianUnavailableReason)}</div>` : ''}
        `;

        const [viewBtn, exportBtn] = node.querySelectorAll('.note-action-btn');
        const deleteBtn = node.querySelector('.menu-item');
        const overflow = node.querySelector('.note-overflow');

        viewBtn.addEventListener('click', () => {
            void viewNote(note.id);
        });
        if (!exportDisabled) {
            exportBtn.addEventListener('click', () => {
                void exportNoteToObsidian(note.id);
            });
        }
        deleteBtn.addEventListener('click', async () => {
            overflow.open = false;
            await deleteNote(note.id);
        });

        if (isHighlighted) {
            highlightedNode = node;
        }
        notesList.appendChild(node);
    }

    if (!notes.some((note) => note.id === highlightedNoteId)) {
        highlightedNoteId = null;
        shouldScrollHighlightedNote = false;
        return;
    }

    if (highlightedNode && shouldScrollHighlightedNote) {
        window.requestAnimationFrame(() => {
            highlightedNode.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
        shouldScrollHighlightedNote = false;
    }
}

async function viewNote(noteId) {
    if (!currentNotebookId) {
        return;
    }
    try {
        const note = await apiJson(`/api/v1/notebooks/${currentNotebookId}/notes/${noteId}`);
        highlightedNoteId = note.id;
        shouldScrollHighlightedNote = false;
        renderNotes(currentNotes);
        renderViewer({
            key: `note:${note.id}`,
            title: note.title,
            meta: formatDateTime(note.created_at),
            body: formatAssistantResponse(note.content, note.citations || []),
        });
        switchStep('export');
    } catch (error) {
        showToast(`打开笔记失败：${error.message}`, 'error');
    }
}

async function deleteNote(noteId) {
    if (!currentNotebookId) {
        return;
    }
    try {
        await apiJson(`/api/v1/notebooks/${currentNotebookId}/notes/${noteId}`, {
            method: 'DELETE',
        });
        if (highlightedNoteId === noteId) {
            highlightedNoteId = null;
            shouldScrollHighlightedNote = false;
        }
        if (currentViewerKey === `note:${noteId}`) {
            renderViewer(null);
        }
        await loadNotes(currentNotebookId);
        showToast('笔记已删除。');
    } catch (error) {
        showToast(`删除笔记失败：${error.message}`, 'error');
    }
}

async function exportNoteToObsidian(noteId) {
    if (!currentNotebookId) {
        return;
    }
    try {
        const result = await apiJson(
            `/api/v1/notebooks/${currentNotebookId}/notes/${noteId}/export/obsidian`,
            { method: 'POST' }
        );
        await loadObsidianStatus();
        showToast(`已导出到 ${result.relative_path}`);
        openExternal(result.obsidian_url);
    } catch (error) {
        showToast(`导出笔记失败：${error.message}`, 'error');
    }
}

async function saveNote(content, citations, button) {
    if (!currentNotebookId) {
        return;
    }

    try {
        button.disabled = true;
        button.textContent = '保存中…';
        const note = await apiJson(`/api/v1/notebooks/${currentNotebookId}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, citations }),
        });
        button.textContent = '已保存';
        highlightedNoteId = note.id;
        shouldScrollHighlightedNote = true;
        await loadNotes(currentNotebookId);
        renderViewer({
            key: `note:${note.id}`,
            title: note.title,
            meta: formatDateTime(note.created_at),
            body: formatAssistantResponse(note.content, note.citations || []),
        });
        switchStep('export');
        showToast('笔记已保存。');
    } catch (error) {
        button.disabled = false;
        button.textContent = '保存失败';
        showToast(`保存笔记失败：${error.message}`, 'error');
    }
}

function renderViewer(payload) {
    if (!payload) {
        currentViewerKey = null;
        noteViewer.hidden = true;
        noteViewerTitle.textContent = '笔记详情';
        noteViewerMeta.textContent = '';
        noteViewerBody.innerHTML = '';
        return;
    }

    currentViewerKey = payload.key;
    noteViewer.hidden = false;
    noteViewerTitle.textContent = payload.title || '详情';
    noteViewerMeta.textContent = payload.meta || '';
    noteViewerBody.innerHTML = payload.body || '';
}

async function loadStudioOutputs(notebookId) {
    if (!notebookId) {
        return;
    }
    try {
        const outputs = await apiJson(`/api/v1/notebooks/${notebookId}/studio`);
        currentStudioOutputs = Array.isArray(outputs) ? outputs : [];
        renderStudioOutputs(currentStudioOutputs);
    } catch (error) {
        showToast(`加载结构化输出失败：${error.message}`, 'error');
    }
}

function renderStudioOutputs(outputs) {
    studioList.innerHTML = '';

    if (!outputs.length) {
        studioList.innerHTML = '<p class="field-hint">还没有结构化输出。需要时再展开高级能力生成。</p>';
        return;
    }

    const obsidianUnavailableReason = getObsidianUnavailableReason();

    for (const output of [...outputs].reverse()) {
        const exportDisabled = !obsidianState.available;
        const node = document.createElement('div');
        node.className = 'studio-item';
        node.innerHTML = `
            <div>
                <div class="studio-title">${escapeHtml(output.title)}</div>
                <div class="studio-meta">${escapeHtml(STUDIO_TYPE_LABELS[output.output_type] || output.output_type)} · ${escapeHtml(formatDateTime(output.created_at))}</div>
            </div>
            <div class="studio-actions">
                <button class="studio-action-btn" type="button">查看</button>
                <button class="studio-action-btn" type="button">保存为笔记</button>
                <button class="studio-action-btn" type="button"${exportDisabled ? ' disabled' : ''}>导出</button>
                <button class="studio-action-btn" type="button">删除</button>
            </div>
            ${exportDisabled ? `<div class="field-hint note-inline-hint">${escapeHtml(obsidianUnavailableReason)}</div>` : ''}
        `;

        const actionButtons = node.querySelectorAll('.studio-action-btn');
        actionButtons[0].addEventListener('click', () => {
            void viewStudioOutput(output.id);
        });
        actionButtons[1].addEventListener('click', () => {
            void saveStudioAsNote(output.id);
        });
        if (!exportDisabled) {
            actionButtons[2].addEventListener('click', () => {
                void exportStudioToObsidian(output.id);
            });
        }
        actionButtons[3].addEventListener('click', () => {
            void deleteStudioOutput(output.id);
        });

        studioList.appendChild(node);
    }
}

async function generateStudioOutput() {
    if (!currentNotebookId || !hasReadySources()) {
        showToast('没有 READY 资料时不能生成结构化输出。', 'error');
        return;
    }
    if (!platformState.llm.available) {
        showToast(platformState.llm.reason || '推理服务不可用，暂时无法生成结构化输出。', 'error');
        return;
    }

    const outputType = studioTypeSelect.value;
    generateBtn.disabled = true;
    generateBtn.textContent = '生成中…';

    try {
        await apiJson(`/api/v1/notebooks/${currentNotebookId}/studio/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ output_type: outputType }),
        });
        await loadStudioOutputs(currentNotebookId);
        showToast(`已生成 ${STUDIO_TYPE_LABELS[outputType] || outputType}。`);
        openAdvancedContent(true);
    } catch (error) {
        if (error.status === 503) {
            await refreshPlatformHealth({ reloadWorkspace: false, silent: true });
        }
        showToast(`生成结构化输出失败：${error.message}`, 'error');
    } finally {
        generateBtn.disabled = !(hasReadySources() && platformState.backend.available && platformState.llm.available);
        generateBtn.textContent = '生成';
    }
}

async function viewStudioOutput(outputId) {
    if (!currentNotebookId) {
        return;
    }
    try {
        const output = await apiJson(`/api/v1/notebooks/${currentNotebookId}/studio/${outputId}`);
        renderViewer({
            key: `studio:${output.id}`,
            title: output.title,
            meta: `${STUDIO_TYPE_LABELS[output.output_type] || output.output_type} · ${formatDateTime(output.created_at)}`,
            body: formatAssistantResponse(output.content, output.citations || []),
        });
        switchStep('export');
        openAdvancedContent(true);
    } catch (error) {
        showToast(`打开结构化输出失败：${error.message}`, 'error');
    }
}

async function saveStudioAsNote(outputId) {
    if (!currentNotebookId) {
        return;
    }
    try {
        const note = await apiJson(
            `/api/v1/notebooks/${currentNotebookId}/studio/${outputId}/save-as-note`,
            { method: 'POST' }
        );
        highlightedNoteId = note.id;
        shouldScrollHighlightedNote = true;
        await loadNotes(currentNotebookId);
        renderViewer({
            key: `note:${note.id}`,
            title: note.title,
            meta: formatDateTime(note.created_at),
            body: formatAssistantResponse(note.content, note.citations || []),
        });
        switchStep('export');
        showToast('已保存为笔记。');
    } catch (error) {
        showToast(`保存结构化输出失败：${error.message}`, 'error');
    }
}

async function exportStudioToObsidian(outputId) {
    if (!currentNotebookId) {
        return;
    }
    try {
        const result = await apiJson(
            `/api/v1/notebooks/${currentNotebookId}/studio/${outputId}/export/obsidian`,
            { method: 'POST' }
        );
        await loadObsidianStatus();
        showToast(`已导出到 ${result.relative_path}`);
        openExternal(result.obsidian_url);
    } catch (error) {
        showToast(`导出结构化输出失败：${error.message}`, 'error');
    }
}

async function deleteStudioOutput(outputId) {
    if (!currentNotebookId) {
        return;
    }
    try {
        await apiJson(`/api/v1/notebooks/${currentNotebookId}/studio/${outputId}`, {
            method: 'DELETE',
        });
        if (currentViewerKey === `studio:${outputId}`) {
            renderViewer(null);
        }
        await loadStudioOutputs(currentNotebookId);
        showToast('结构化输出已删除。');
    } catch (error) {
        showToast(`删除结构化输出失败：${error.message}`, 'error');
    }
}

function toggleAdvancedContent() {
    openAdvancedContent(advancedContent.hidden);
}

function openAdvancedContent(forceVisible) {
    advancedContent.hidden = !forceVisible;
    advancedToggle.textContent = forceVisible ? '收起高级能力' : '高级能力';
    if (forceVisible && currentNotebookId) {
        void loadStudioOutputs(currentNotebookId);
        void loadGraph(currentNotebookId);
    }
}

async function generateGraph() {
    if (!currentNotebookId || !hasReadySources()) {
        showToast('没有 READY 资料时不能生成知识图谱。', 'error');
        return;
    }

    graphStatus.textContent = '正在生成知识图谱…';
    mindmapSvg.innerHTML = '';
    try {
        const graph = await apiJson(`/api/v1/notebooks/${currentNotebookId}/graph/generate`, {
            method: 'POST',
        });
        renderMindMap(graph.mindmap);
        graphStatus.textContent = '图谱已生成，可点击节点直接提问。';
        openAdvancedContent(true);
        showToast('知识图谱已生成。');
    } catch (error) {
        graphStatus.textContent = `生成失败：${error.message}`;
        showToast(`生成知识图谱失败：${error.message}`, 'error');
    }
}

async function loadGraph(notebookId) {
    if (!notebookId) {
        return;
    }

    if (!hasReadySources()) {
        graphStatus.textContent = '需要至少一份 READY 资料后才可生成。';
        mindmapSvg.innerHTML = '';
        return;
    }

    try {
        const graph = await apiJson(`/api/v1/notebooks/${notebookId}/graph`);
        renderMindMap(graph.mindmap);
        graphStatus.textContent = '已加载最近一次知识图谱。';
    } catch (error) {
        if (error.status === 404) {
            graphStatus.textContent = '尚未生成图谱，按需点击“生成知识图谱”。';
            mindmapSvg.innerHTML = '';
            return;
        }
        graphStatus.textContent = '加载图谱失败。';
    }
}

function renderMindMap(mindmap) {
    if (!mindmap) {
        mindmapSvg.innerHTML = '';
        return;
    }

    mindmapSvg.innerHTML = '';
    const width = mindmapSvg.clientWidth || 320;
    const height = mindmapSvg.clientHeight || 360;
    const cx = width / 2;
    const cy = height / 2;
    const radii = [0, 92, 170, 240];
    const svgNs = 'http://www.w3.org/2000/svg';
    const queue = [{ node: mindmap, depth: 0, start: 0, end: Math.PI * 2 }];
    const positions = {};
    const nodes = [];
    const edges = [];

    while (queue.length) {
        const { node, depth, start, end } = queue.shift();
        const angle = (start + end) / 2;
        const radius = radii[Math.min(depth, radii.length - 1)];
        const x = cx + radius * Math.cos(angle);
        const y = cy + radius * Math.sin(angle);
        positions[node.id] = { x, y };
        nodes.push({ node, x, y, depth });

        if (node.children?.length) {
            const span = (end - start) / node.children.length;
            node.children.forEach((child, index) => {
                edges.push({ parent: node.id, child: child.id });
                queue.push({
                    node: child,
                    depth: depth + 1,
                    start: start + index * span,
                    end: start + (index + 1) * span,
                });
            });
        }
    }

    edges.forEach(({ parent, child }) => {
        const from = positions[parent];
        const to = positions[child];
        if (!from || !to) {
            return;
        }
        const path = document.createElementNS(svgNs, 'path');
        path.setAttribute('d', `M${from.x},${from.y} Q${(from.x + to.x) / 2},${(from.y + to.y) / 2} ${to.x},${to.y}`);
        path.setAttribute('class', 'mm-edge');
        mindmapSvg.appendChild(path);
    });

    nodes.forEach(({ node, x, y, depth }) => {
        const group = document.createElementNS(svgNs, 'g');
        group.setAttribute('class', 'mm-node');
        group.setAttribute('transform', `translate(${x},${y})`);

        const circle = document.createElementNS(svgNs, 'circle');
        const baseRadius = depth === 0 ? 28 : depth === 1 ? 20 : 14;
        circle.setAttribute('r', baseRadius);
        circle.addEventListener('click', () => {
            queryInput.value = node.label;
            switchStep('qa');
            submitQuery();
        });
        group.appendChild(circle);

        const text = document.createElementNS(svgNs, 'text');
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('dy', '0.35em');
        const maxLength = depth === 0 ? 7 : depth === 1 ? 5 : 4;
        text.textContent = node.label.length > maxLength
            ? `${node.label.slice(0, maxLength)}…`
            : node.label;
        group.appendChild(text);

        const title = document.createElementNS(svgNs, 'title');
        title.textContent = node.label;
        group.appendChild(title);

        mindmapSvg.appendChild(group);
    });
}

function showToast(message, kind = 'success') {
    toast.textContent = message;
    toast.className = `toast visible ${kind}`;
    if (toastTimer) {
        window.clearTimeout(toastTimer);
    }
    toastTimer = window.setTimeout(() => {
        toast.classList.remove('visible');
    }, 2600);
}

function updateQaMenuVisibility() {
    qaMenu.hidden = !currentNotebookId || isOnlyWelcomeMessage() || !platformState.backend.available;
}

function openExternal(url) {
    if (!url) {
        return;
    }
    const link = document.createElement('a');
    link.href = url;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function formatDateTime(value) {
    if (!value) {
        return '';
    }
    try {
        return new Date(value).toLocaleString();
    } catch (_) {
        return value;
    }
}

function getObsidianUnavailableReason() {
    return obsidianState.available
        ? ''
        : '未检测到本地 Obsidian vault，当前只能查看内容，暂不能导出。';
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function escapeAttr(value) {
    return String(value)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"');
}
