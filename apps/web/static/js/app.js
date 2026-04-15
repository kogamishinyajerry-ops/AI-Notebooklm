/**
 * COMAC 智能 NotebookLM — V3.0 Gap D 流式认知工作台
 * =====================================================
 *
 * Gap D 升级内容（相对于 V2.5）：
 *   Task D-2: 流式 Chat 渲染（SSE EventSource）
 *             引用卡片收藏面板（Citation Library，替代 Studio Notes 扩展）
 *   Task D-3: 衍生产物生成（对比表 / 技术简报）
 *             产物卡片渲染 + Markdown 导出
 *
 * 架构：纯 Vanilla JS，无构建工具，C1 合规（零外部 CDN 新增）
 */

console.log("🚀 COMAC V3.0 Gap D — 流式认知工作台启动中...");

// ---------------------------------------------------------------------------
// 全局状态
// ---------------------------------------------------------------------------

let allDocs = [];
window.currentCitations = [];

/**
 * citationLibrary: 引用卡片收藏库（Gap D Task D-2）
 * 结构: [{id, source_file, page_number, content, bbox, tag, pinned_at}]
 */
let citationLibrary = JSON.parse(localStorage.getItem('comac_citation_library') || '[]');

/**
 * artifacts: 已生成的衍生产物列表（Gap D Task D-3）
 * 结构: [{id, artifact_type, topic, content, generated_at, is_fully_verified, citations}]
 */
let artifacts = [];

let ui = {};

// ---------------------------------------------------------------------------
// 初始化
// ---------------------------------------------------------------------------

window.onload = () => {
    initApp();
    initSplitters();
};

function initApp() {
    ui = {
        queryInput:        document.getElementById('query-input'),
        chatHistory:       document.getElementById('chat-history'),
        notesContainer:    document.getElementById('notes-container'),
        guideBtn:          document.getElementById('guide-btn'),
        guideModal:        document.getElementById('guide-modal'),
        podcastBtn:        document.getElementById('podcast-btn'),
        podcastModal:      document.getElementById('podcast-modal'),
        graphBtn:          document.getElementById('graph-btn'),
        graphModal:        document.getElementById('graph-modal'),
        graphStatus:       document.getElementById('graph-status'),
        graphRebuildBtn:   document.getElementById('graph-rebuild-btn'),
        exportBtn:         document.getElementById('export-btn'),
        pdfPage:           document.getElementById('pdf-page'),
        sourceFilter:      document.getElementById('source-filter'),
        dataContainer:     document.getElementById('data-container'),
        tableCount:        document.getElementById('table-count'),
        podcastContent:    document.getElementById('podcast-content'),
        guideSummary:      document.getElementById('guide-summary'),
        suggestedQuestions:document.getElementById('suggested-questions'),
        // Gap D 新增
        citationLibPanel:  document.getElementById('citation-lib-panel'),
        citationLibList:   document.getElementById('citation-lib-list'),
        citationLibCount:  document.getElementById('citation-lib-count'),
        artifactPanel:     document.getElementById('artifact-panel'),
        artifactList:      document.getElementById('artifact-list'),
        artifactTopicInput:document.getElementById('artifact-topic'),
        artifactTypeSelect:document.getElementById('artifact-type'),
        artifactGenBtn:    document.getElementById('artifact-gen-btn'),
        streamIndicator:   document.getElementById('stream-indicator'),
    };

    // Chat 输入
    if (ui.queryInput) {
        ui.queryInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && ui.queryInput.value.trim()) {
                const query = ui.queryInput.value.trim();
                ui.queryInput.value = '';
                addMessage('user', query);
                performStreamingChat(query);  // Gap D: 替换为流式版本
            }
        });
    }

    // 来源过滤
    if (ui.sourceFilter) {
        ui.sourceFilter.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            renderSourceGallery(allDocs.filter(d => d.filename.toLowerCase().includes(term)));
        });
    }

    // 按钮绑定
    if (ui.podcastBtn)   ui.podcastBtn.addEventListener('click', handlePodcast);
    if (ui.graphBtn)     ui.graphBtn.addEventListener('click', handleGraph);
    if (ui.graphRebuildBtn) ui.graphRebuildBtn.addEventListener('click', handleGraphRebuild);
    if (ui.exportBtn)    ui.exportBtn.addEventListener('click', handleExport);
    if (ui.guideBtn)     ui.guideBtn.addEventListener('click', handleGuide);

    // Gap D — 衍生产物生成按钮
    if (ui.artifactGenBtn) {
        ui.artifactGenBtn.addEventListener('click', handleGenerateArtifact);
    }

    // 初始加载
    fetchDocuments();
    renderCitationLibrary();
    renderArtifactList();
}

// ---------------------------------------------------------------------------
// Splitter（保持不变）
// ---------------------------------------------------------------------------

function initSplitters() {
    setupSplitter('gutter-1', 'col-doc', 'col-chat');
    setupSplitter('gutter-2', 'col-chat', 'col-studio');
}

function setupSplitter(id, leftId, rightId) {
    const gutter = document.getElementById(id);
    const leftCol = document.getElementById(leftId);
    const rightCol = document.getElementById(rightId);
    if (!gutter || !leftCol || !rightCol) return;

    let startX, startLeftFlex, startRightFlex;
    gutter.addEventListener('mousedown', (e) => {
        startX = e.clientX;
        startLeftFlex  = parseFloat(getComputedStyle(leftCol).flexGrow);
        startRightFlex = parseFloat(getComputedStyle(rightCol).flexGrow);
        const onMove = (ev) => {
            const delta = (ev.clientX - startX) / 300;
            leftCol.style.flexGrow  = Math.max(0.1, startLeftFlex  + delta);
            rightCol.style.flexGrow = Math.max(0.1, startRightFlex - delta);
        };
        const onUp = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            document.body.style.cursor = 'default';
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        document.body.style.cursor = 'col-resize';
    });
}

// ---------------------------------------------------------------------------
// 文档管理（保持不变）
// ---------------------------------------------------------------------------

async function fetchDocuments() {
    try {
        const resp = await fetch('/api/v1/documents');
        allDocs = await resp.json();
        renderSourceGallery(allDocs);
    } catch (err) { console.error("文档加载失败:", err); }
}

function renderSourceGallery(docs) {
    const sourceList = document.getElementById('source-list');
    if (!sourceList) return;
    sourceList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.65rem; padding: 10px 0;">YOUR SOURCES</p>';
    docs.forEach((doc, idx) => {
        const div = document.createElement('div');
        div.className = 'source-card';
        div.id = `doc-${doc.filename.replace(/[^a-zA-Z0-9]/g, '_')}`;
        div.innerHTML = `<h4 style="font-size: 0.8rem;">${doc.filename}</h4><p style="font-size: 0.65rem; color: var(--text-muted);">Industrial Spec</p>`;
        div.onclick = () => selectDocument(doc.filename);
        sourceList.appendChild(div);
        if (idx === 0) selectDocument(doc.filename);
    });
}

async function selectDocument(filename) {
    document.querySelectorAll('.source-card').forEach(c => c.classList.remove('active'));
    const target = document.getElementById(`doc-${filename.replace(/[^a-zA-Z0-9]/g, '_')}`);
    if (target) target.classList.add('active');
    try {
        const resp = await fetch(`/api/v1/documents/${filename}/preview`);
        const chunks = await resp.json();
        ui.pdfPage.innerHTML = '<div id="highlight" class="highlight-overlay" style="display:none;"></div>';
        ui.dataContainer.innerHTML = '';
        const contentDiv = document.createElement('div');
        contentDiv.innerHTML = `<h2 style="font-weight:500;font-size:1.4rem;margin-bottom:20px;color:#1a73e8;">${filename}</h2>`;
        let tableCount = 0;
        chunks.forEach(chunk => {
            if (chunk.metadata && chunk.metadata.type === "table") {
                tableCount++;
                renderTableToUI(chunk.text);
            } else {
                const p = document.createElement('p');
                p.style.cssText = 'margin-bottom:20px;font-size:0.9rem;line-height:1.8';
                p.textContent = chunk.text;
                contentDiv.appendChild(p);
            }
        });
        ui.pdfPage.appendChild(contentDiv);
        if (ui.tableCount) ui.tableCount.textContent = tableCount;
    } catch (err) { console.error("文档预览失败:", err); }
}

function renderTableToUI(jsonStr) {
    try {
        const data = JSON.parse(jsonStr);
        if (!data || data.length === 0) return;
        const headers = Object.keys(data[0]);
        const table = document.createElement('table');
        table.className = 'vision-table';
        const thead = document.createElement('thead');
        const hRow = document.createElement('tr');
        headers.forEach(h => { const th = document.createElement('th'); th.textContent = h; hRow.appendChild(th); });
        thead.appendChild(hRow); table.appendChild(thead);
        const tbody = document.createElement('tbody');
        data.forEach(row => {
            const tr = document.createElement('tr');
            headers.forEach(h => { const td = document.createElement('td'); td.textContent = row[h] || ""; tr.appendChild(td); });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody); ui.dataContainer.appendChild(table);
    } catch(e) { console.warn("表格渲染错误:", e); }
}

window.switchView = (viewId) => {
    document.getElementById('view-doc').style.display = viewId === 'doc' ? 'block' : 'none';
    document.getElementById('view-data').style.display = viewId === 'data' ? 'block' : 'none';
    document.getElementById('tab-doc').classList.toggle('active', viewId === 'doc');
    document.getElementById('tab-data').classList.toggle('active', viewId === 'data');
};

// ---------------------------------------------------------------------------
// Gap D Task D-2 — 流式 Chat（SSE EventSource）
// ---------------------------------------------------------------------------

/**
 * performStreamingChat — 替换原 performChat。
 * 使用 fetch + ReadableStream 读取 SSE，逐 token 追加到 AI 气泡。
 */
async function performStreamingChat(query) {
    // 创建 AI 消息气泡（先占位）
    const msgDiv = document.createElement('div');
    msgDiv.className = 'msg-bubble msg-ai msg-streaming';
    const textSpan = document.createElement('span');
    textSpan.className = 'stream-text';
    const cursorSpan = document.createElement('span');
    cursorSpan.className = 'stream-cursor';
    cursorSpan.textContent = '▌';
    msgDiv.appendChild(textSpan);
    msgDiv.appendChild(cursorSpan);
    if (ui.chatHistory) {
        ui.chatHistory.appendChild(msgDiv);
        ui.chatHistory.scrollTop = ui.chatHistory.scrollHeight;
    }

    // 流式指示器
    if (ui.streamIndicator) ui.streamIndicator.style.display = 'flex';

    let fullText = '';
    let citationsRendered = false;

    try {
        const response = await fetch('/api/v1/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, space_id: 'default' }),
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // 保留未完整的行

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const raw = line.slice(6).trim();
                if (!raw) continue;

                let evt;
                try { evt = JSON.parse(raw); } catch { continue; }

                if (evt.type === 'delta') {
                    fullText += evt.text;
                    textSpan.innerHTML = formatAssistantResponse(fullText);
                    if (ui.chatHistory) ui.chatHistory.scrollTop = ui.chatHistory.scrollHeight;

                } else if (evt.type === 'citations') {
                    window.currentCitations = evt.citations;
                    // 渲染引用小结附在气泡下方
                    if (evt.citations && evt.citations.length > 0 && !citationsRendered) {
                        const citRow = document.createElement('div');
                        citRow.className = 'citation-row';
                        evt.citations.forEach(c => {
                            const pill = document.createElement('span');
                            pill.className = 'citation-pill';
                            pill.textContent = `${c.source_file} p.${c.page_number}`;
                            pill.onclick = () => showSource(c.source_file, c.page_number);
                            const pin = document.createElement('button');
                            pin.className = 'pin-note-btn';
                            pin.textContent = '📌';
                            pin.title = '收藏到引用库';
                            pin.onclick = (e) => { e.stopPropagation(); saveToCitationLibrary(c); };
                            citRow.appendChild(pill);
                            citRow.appendChild(pin);
                        });
                        msgDiv.appendChild(citRow);
                        citationsRendered = true;
                    }

                } else if (evt.type === 'done') {
                    if (evt.answer) {
                        fullText = evt.answer;
                        textSpan.innerHTML = formatAssistantResponse(fullText);
                    }
                    if (evt.is_verified === false) {
                        const status = document.createElement('div');
                        status.style.cssText = 'margin-top:8px;font-size:0.75rem;color:#a15c00;background:#fff4e5;border:1px solid #f3d19c;border-radius:8px;padding:8px 10px;';
                        status.textContent = '该流式回答未完全通过校验，已自动切换为安全结果。';
                        msgDiv.appendChild(status);
                    }
                    // 流结束：移除游标和流式样式
                    cursorSpan.remove();
                    msgDiv.classList.remove('msg-streaming');
                }
            }
        }
    } catch (err) {
        console.error("流式 Chat 失败，降级为批处理:", err);
        // 降级：使用原批处理接口
        try {
            const resp = await fetch('/api/v1/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, space_id: 'default' }),
            });
            const data = await resp.json();
            window.currentCitations = data.citations;
            cursorSpan.remove();
            textSpan.innerHTML = formatAssistantResponse(data.answer);
            msgDiv.classList.remove('msg-streaming');
        } catch (err2) {
            textSpan.textContent = '[错误] 无法连接到后端服务。';
        }
    } finally {
        if (ui.streamIndicator) ui.streamIndicator.style.display = 'none';
        if (ui.chatHistory) ui.chatHistory.scrollTop = ui.chatHistory.scrollHeight;
    }
}

// ---------------------------------------------------------------------------
// Gap D Task D-2 — 引用卡片收藏库
// ---------------------------------------------------------------------------

/**
 * saveToCitationLibrary — 将引用卡片保存到本地库。
 */
function saveToCitationLibrary(citation, tag = '') {
    const entry = {
        id: `cit_${Date.now()}_${Math.random().toString(36).slice(2,6)}`,
        source_file: citation.source_file,
        page_number: citation.page_number,
        content: citation.content,
        bbox: citation.bbox || [0,0,0,0],
        tag: tag || (citation.source_file.toLowerCase().includes('faa') ? '适航法规' : '工程参数'),
        pinned_at: new Date().toLocaleString('zh-CN'),
    };
    citationLibrary.unshift(entry);
    // 持久化到 localStorage（脱网可用）
    try { localStorage.setItem('comac_citation_library', JSON.stringify(citationLibrary)); } catch(e) {}
    renderCitationLibrary();

    // 视觉反馈
    showToast(`📌 已收藏：${citation.source_file} p.${citation.page_number}`);
}

function renderCitationLibrary() {
    if (!ui.citationLibList) return;
    if (ui.citationLibCount) ui.citationLibCount.textContent = citationLibrary.length;

    ui.citationLibList.innerHTML = '';
    if (citationLibrary.length === 0) {
        ui.citationLibList.innerHTML = '<p class="empty-hint">点击引用旁的 📌 收藏到此处</p>';
        return;
    }

    citationLibrary.forEach((entry, idx) => {
        const card = document.createElement('div');
        card.className = `citation-lib-card ${entry.tag === '适航法规' ? 'regulatory' : 'internal'}`;
        card.innerHTML = `
            <div class="cit-lib-header">
                <span class="cit-lib-src">${entry.source_file}</span>
                <span class="cit-lib-page">第 ${entry.page_number} 页</span>
                <span class="cit-lib-tag">${entry.tag}</span>
                <button class="cit-lib-del" title="删除" onclick="removeCitation(${idx})">✕</button>
            </div>
            <div class="cit-lib-content">${entry.content}</div>
            <div class="cit-lib-footer">
                <span>收藏于 ${entry.pinned_at}</span>
                <button class="cit-lib-jump" onclick="showSource('${entry.source_file}', ${entry.page_number})">跳转原文</button>
            </div>
        `;
        ui.citationLibList.appendChild(card);
    });
}

window.removeCitation = (idx) => {
    citationLibrary.splice(idx, 1);
    try { localStorage.setItem('comac_citation_library', JSON.stringify(citationLibrary)); } catch(e) {}
    renderCitationLibrary();
};

// ---------------------------------------------------------------------------
// Gap D Task D-3 — 衍生产物生成
// ---------------------------------------------------------------------------

async function handleGenerateArtifact() {
    const topic = ui.artifactTopicInput ? ui.artifactTopicInput.value.trim() : '';
    const artifactType = ui.artifactTypeSelect ? ui.artifactTypeSelect.value : 'technical_brief';
    if (!topic) { showToast('请输入生成主题'); return; }

    if (ui.artifactGenBtn) {
        ui.artifactGenBtn.disabled = true;
        ui.artifactGenBtn.textContent = '生成中...';
    }

    try {
        // 将收藏库中的引用作为上下文传入
        const citedSources = citationLibrary.slice(0, 5).map(c => ({
            source_file: c.source_file,
            page_number: c.page_number,
            content: c.content,
            bbox: c.bbox,
        }));

        const resp = await fetch('/api/v1/artifacts/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                artifact_type: artifactType,
                topic: topic,
                space_id: 'default',
                cited_sources: citedSources.length > 0 ? citedSources : null,
            }),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        // 追加到产物列表
        artifacts.unshift({ ...data, id: `art_${Date.now()}` });
        renderArtifactList();
        if (ui.artifactTopicInput) ui.artifactTopicInput.value = '';
        showToast(`✅ 产物生成完成：${topic}`);

    } catch (err) {
        console.error("衍生产物生成失败:", err);
        showToast('生成失败，请检查后端连接');
    } finally {
        if (ui.artifactGenBtn) {
            ui.artifactGenBtn.disabled = false;
            ui.artifactGenBtn.textContent = '生成产物';
        }
    }
}

function renderArtifactList() {
    if (!ui.artifactList) return;
    ui.artifactList.innerHTML = '';
    if (artifacts.length === 0) {
        ui.artifactList.innerHTML = '<p class="empty-hint">输入主题后点击「生成产物」</p>';
        return;
    }
    artifacts.forEach((art, idx) => {
        const card = document.createElement('div');
        card.className = 'artifact-card';
        const typeLabel = art.artifact_type === 'comparison_table' ? '📊 对比表' : '📝 技术简报';
        const verificationBadge = art.is_fully_verified
            ? '<span class="badge" style="background:#e8f5e9;color:#1b5e20;">已验证</span>'
            : '<span class="badge" style="background:#fff4e5;color:#a15c00;">待核验</span>';
        card.innerHTML = `
            <div class="artifact-header">
                <span class="artifact-type-tag">${typeLabel}</span>
                <span class="artifact-topic">${art.topic}</span>
                <div class="artifact-actions">
                    <button onclick="exportArtifact(${idx})" title="导出 Markdown">⬇ 导出</button>
                    <button onclick="removeArtifact(${idx})" title="删除">✕</button>
                </div>
            </div>
            <div class="artifact-content">${renderMarkdown(art.content)}</div>
            ${renderArtifactCitationRow(art.citations || [])}
            <div class="artifact-footer" style="display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap;">
                <span>生成时间：${art.generated_at}</span>
                ${verificationBadge}
            </div>
        `;
        ui.artifactList.appendChild(card);
    });
}

window.exportArtifact = (idx) => {
    const art = artifacts[idx];
    if (!art) return;
    const blob = new Blob([`# ${art.topic}\n\n${art.content}`], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `COMAC_${art.artifact_type}_${art.topic.slice(0,20).replace(/\s/g,'_')}.md`;
    a.click();
    URL.revokeObjectURL(url);
};

window.removeArtifact = (idx) => {
    artifacts.splice(idx, 1);
    renderArtifactList();
};

// ---------------------------------------------------------------------------
// 引用源跳转
// ---------------------------------------------------------------------------

function escapeJsString(value) {
    return String(value ?? '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/\r?\n/g, ' ');
}

function buildCitationPayload(citation) {
    const bbox = Array.isArray(citation.bbox) ? citation.bbox : [0, 0, 0, 0];
    const pageNumber = citation.page_number ?? 0;
    return `{source_file:'${escapeJsString(citation.source_file)}',page_number:${JSON.stringify(pageNumber)},content:'${escapeJsString(citation.content || '')}',bbox:${JSON.stringify(bbox)}}`;
}

function renderCitationActions(citation) {
    const safeSrc = escapeJsString(citation.source_file);
    const safePage = escapeJsString(citation.page_number);
    const label = escapeHtml(`${citation.source_file} p.${citation.page_number}`);
    return `<span class="inline-citation">
        <button class="citation-pill" onclick="showSource('${safeSrc}','${safePage}')">${label}</button>
        <button class="pin-note-btn" onclick="saveToCitationLibrary(${buildCitationPayload(citation)})">📌</button>
    </span>`;
}

function renderArtifactCitationRow(citations) {
    if (!citations || citations.length === 0) return '';
    return `<div class="citation-row">${citations.map(renderCitationActions).join('')}</div>`;
}

function findCitationBySourcePage(src, page) {
    const targetSrc = String(src);
    const targetPage = String(page);
    const artifactCitations = artifacts.flatMap(art => art.citations || []);
    const pools = [...(window.currentCitations || []), ...citationLibrary, ...artifactCitations];
    return pools.find(
        citation =>
            String(citation.source_file) === targetSrc &&
            String(citation.page_number) === targetPage
    );
}

window.showSource = (src, page) => {
    selectDocument(src).then(() => {
        const citation = findCitationBySourcePage(src, page);
        if (citation && Array.isArray(citation.bbox) && citation.bbox.length === 4) {
            const hl = document.getElementById('highlight');
            if (hl) {
                hl.style.display = 'block';
                hl.style.left   = `${citation.bbox[0]}px`;
                hl.style.top    = `${citation.bbox[1]}px`;
                hl.style.width  = `${citation.bbox[2] - citation.bbox[0]}px`;
                hl.style.height = `${citation.bbox[3] - citation.bbox[1]}px`;
                hl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    });
};

// ---------------------------------------------------------------------------
// 消息渲染（保留原有 Citation XML 解析）
// ---------------------------------------------------------------------------

function formatAssistantResponse(text) {
    return text.replace(
        /<citation src=['"]([^'"]+)['"] page=['"]([^'"]+)['"]>(.*?)<\/citation>/g,
        (match, src, page, content) => renderCitationActions({
            source_file: src,
            page_number: page,
            content,
            bbox: [0, 0, 0, 0],
        })
    );
}

function addMessage(role, text) {
    const div = document.createElement('div');
    div.className = `msg-bubble msg-${role === 'assistant' ? 'ai' : 'user'}`;
    div.innerHTML = role === 'assistant' ? formatAssistantResponse(text) : text;
    if (ui.chatHistory) {
        ui.chatHistory.appendChild(div);
        ui.chatHistory.scrollTop = ui.chatHistory.scrollHeight;
    }
}

// ---------------------------------------------------------------------------
// 简易 Markdown 渲染（表格 + 粗体 + 代码）
// ---------------------------------------------------------------------------

function renderMarkdown(md) {
    if (!md) return '';
    let html = md
        // 代码块
        .replace(/```[\s\S]*?```/g, m => `<pre><code>${escapeHtml(m.slice(3, -3).trim())}</code></pre>`)
        // 行内代码
        .replace(/`([^`]+)`/g, (_, c) => `<code>${escapeHtml(c)}</code>`)
        // 粗体
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // Markdown 表格（简易版）
        .replace(/\|(.+)\|\n\|[-| :]+\|\n((?:\|.+\|\n?)+)/g, (match, header, rows) => {
            const ths = header.split('|').filter(s => s.trim()).map(h => `<th>${h.trim()}</th>`).join('');
            const trs = rows.trim().split('\n').map(row => {
                const tds = row.split('|').filter(s => s.trim()).map(c => `<td>${c.trim()}</td>`).join('');
                return `<tr>${tds}</tr>`;
            }).join('');
            return `<table class="artifact-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
        })
        // 段落换行
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');
    return `<p>${html}</p>`;
}

function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ---------------------------------------------------------------------------
// Toast 通知
// ---------------------------------------------------------------------------

function showToast(msg) {
    const existing = document.getElementById('comac-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.id = 'comac-toast';
    toast.className = 'comac-toast';
    toast.textContent = msg;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('visible'));
    setTimeout(() => { toast.classList.remove('visible'); setTimeout(() => toast.remove(), 300); }, 2500);
}

// ---------------------------------------------------------------------------
// Modal Handlers（保持原有）
// ---------------------------------------------------------------------------

async function handlePodcast() {
    if (ui.podcastModal) ui.podcastModal.style.display = 'flex';
    if (ui.podcastContent) ui.podcastContent.innerHTML = '正在唤醒深度研讨模式...';
    try {
        const resp = await fetch('/api/v1/audio/script?space_id=industrial');
        const data = await resp.json();
        if (ui.podcastContent) {
            ui.podcastContent.innerHTML = '';
            data.dialogue.forEach(line => {
                const p = document.createElement('p');
                p.style.marginBottom = '12px';
                const speakerId = line.speaker === data.host_1 ? '1' : '2';
                p.innerHTML = `<span class="speaker-tag speaker-${speakerId}">${line.speaker}:</span> ${line.text}`;
                ui.podcastContent.appendChild(p);
            });
        }
    } catch (err) { console.error(err); }
}

async function handleGraph() {
    if (ui.graphModal) ui.graphModal.style.display = 'flex';
    await loadKnowledgeGraph();
}

async function loadKnowledgeGraph(rebuildReport = null) {
    try {
        const resp = await fetch('/api/v1/knowledge-graph?space_id=industrial');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        renderGraph(data);
        renderGraphStatus(data.graph_stats || {}, rebuildReport);
    } catch (err) {
        console.error("知识图谱加载失败:", err);
        if (ui.graphStatus) ui.graphStatus.textContent = '图谱加载失败，请检查后端连接。';
        showToast('知识图谱加载失败');
    }
}

async function handleGraphRebuild() {
    if (!ui.graphRebuildBtn) return;
    ui.graphRebuildBtn.disabled = true;
    ui.graphRebuildBtn.textContent = '重建中...';
    try {
        const resp = await fetch('/api/v1/knowledge-graph/rebuild?space_id=industrial', {
            method: 'POST',
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const report = data.report || {};
        await loadKnowledgeGraph(report);
        showToast(`图谱重建完成：${report.communities_indexed ?? 0} 个社区摘要`);
    } catch (err) {
        console.error("知识图谱重建失败:", err);
        showToast('知识图谱重建失败');
    } finally {
        ui.graphRebuildBtn.disabled = false;
        ui.graphRebuildBtn.textContent = '重建社区摘要';
    }
}

function renderGraphStatus(stats, rebuildReport = null) {
    if (!ui.graphStatus) return;
    const needsRebuild = Boolean(stats && stats.needs_reclustering);
    const statusLabel = needsRebuild ? '建议重建' : '状态稳定';
    const metrics = `节点 ${stats?.nodes ?? 0} / 边 ${stats?.edges ?? 0}`;
    const rebuildText = rebuildReport
        ? ` | 最近重建：索引 ${rebuildReport.communities_indexed ?? 0} 个社区`
        : '';
    ui.graphStatus.innerHTML = `
        <span style="display:inline-block;padding:2px 8px;border-radius:999px;background:${needsRebuild ? '#fff4e5' : '#e8f5e9'};color:${needsRebuild ? '#a15c00' : '#1b5e20'};font-weight:600;margin-right:8px;">${statusLabel}</span>
        <span>${metrics}${rebuildText}</span>
    `;
}

function renderGraph(data) {
    const svg = document.getElementById('graph-svg');
    if (!svg) return;

    svg.innerHTML = '';

    const width = 780;
    const height = 480;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    const nodes = Array.isArray(data.nodes) ? data.nodes : [];
    const links = Array.isArray(data.links) ? data.links : [];
    if (nodes.length === 0) return;

    const ns = 'http://www.w3.org/2000/svg';
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.max(80, Math.min(width, height) / 2 - 80);
    const positioned = new Map();

    nodes.forEach((node, index) => {
        const angle = (Math.PI * 2 * index) / nodes.length - Math.PI / 2;
        positioned.set(node.id, {
            ...node,
            x: cx + Math.cos(angle) * radius,
            y: cy + Math.sin(angle) * radius,
        });
    });

    links.forEach((link) => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
        const targetId = typeof link.target === 'object' ? link.target.id : link.target;
        const source = positioned.get(sourceId);
        const target = positioned.get(targetId);
        if (!source || !target) return;

        const line = document.createElementNS(ns, 'line');
        line.setAttribute('x1', source.x);
        line.setAttribute('y1', source.y);
        line.setAttribute('x2', target.x);
        line.setAttribute('y2', target.y);
        line.setAttribute('stroke', '#9aa0a6');
        line.setAttribute('stroke-opacity', '0.7');
        line.setAttribute('stroke-width', '2');
        svg.appendChild(line);
    });

    positioned.forEach((node) => {
        const group = document.createElementNS(ns, 'g');

        const circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('cx', node.x);
        circle.setAttribute('cy', node.y);
        circle.setAttribute('r', '8');
        circle.setAttribute('fill', node.group === 'regulatory' ? '#1a73e8' : '#7c4dff');
        group.appendChild(circle);

        const label = document.createElementNS(ns, 'text');
        label.setAttribute('x', node.x + 12);
        label.setAttribute('y', node.y + 4);
        label.setAttribute('font-size', '10');
        label.textContent = node.id;
        group.appendChild(label);

        const title = document.createElementNS(ns, 'title');
        title.textContent = node.id;
        group.appendChild(title);

        svg.appendChild(group);
    });
}

async function handleExport() {
    window.open('/api/v1/studio/export');
}

async function handleGuide() {
    if (ui.guideModal) ui.guideModal.style.display = 'flex';
    const resp = await fetch('/api/v1/study-guide?space_id=industrial');
    const data = await resp.json();
    if (ui.guideSummary) ui.guideSummary.textContent = data.summary;
    if (ui.suggestedQuestions) {
        ui.suggestedQuestions.innerHTML = '';
        data.suggested_questions.forEach(q => {
            const b = document.createElement('button');
            b.className = 'citation-pill'; b.style.cssText = 'width:100%;text-align:left;';
            b.textContent = q;
            b.onclick = () => {
                ui.guideModal.style.display = 'none';
                ui.queryInput.value = q;
                ui.queryInput.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter' }));
            };
            ui.suggestedQuestions.appendChild(b);
        });
    }
}

console.log("✅ COMAC V3.0 Gap D — 流式认知工作台就绪。");
