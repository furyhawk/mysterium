/* ── Mysterium Frontend ─────────────────────────────────────────────
   Vanilla JS SPA — no framework build step required.
   Three tabs: Upload, Search, Research.
   Communicates with the FastAPI backend which proxies to verity-rag.
*/

(function () {
  'use strict';

  // ── State ─────────────────────────────────────────────────────────
  const state = {
    collections: ['documents'],
    docs: [],
  };

  // Markdown content store: button element → markdown string.
  // Avoids HTML data-attribute encoding issues with large reports.
  const markdownStore = new WeakMap();

  // ── DOM refs (populated on DOMContentLoaded) ─────────────────────
  let els = {};

  // ── API helpers ────────────────────────────────────────────────────
  const API = {
    async get(path) {
      const res = await fetch(path);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `GET ${path} failed (${res.status})`);
      }
      return res.json();
    },

    async post(path, body) {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `POST ${path} failed (${res.status})`);
      }
      return res.json();
    },

    async upload(file, collection) {
      const form = new FormData();
      form.append('file', file);
      form.append('collection_name', collection);
      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        body: form,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Upload failed (${res.status})`);
      }
      return res.json();
    },

    async deleteDocument(id) {
      const res = await fetch(`/api/documents/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`Delete failed (${res.status})`);
      return res.json();
    },

    async search(query, opts) {
      return this.post('/api/documents/search', {
        query,
        collection_name: opts.collection || 'documents',
        limit: opts.limit || 5,
        min_score: 0.0,
        use_reranker: opts.rerank || false,
      });
    },

    async ask(question, opts) {
      return this.post('/api/research/ask', {
        question,
        collection_name: opts.collection || 'documents',
        limit: opts.limit || 5,
      });
    },
  };

  // ── UI Helpers ────────────────────────────────────────────────────
  function toast(msg, type) {
    const t = els.toast;
    t.textContent = msg;
    t.className = 'toast' + (type ? ' ' + type : '');
    setTimeout(() => t.classList.add('hidden'), 3500);
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function statusClass(status) {
    const s = (status || '').toLowerCase();
    if (s === 'completed' || s === 'ready') return 'completed';
    if (s === 'processing' || s === 'pending') return 'processing';
    if (s === 'failed' || s === 'error') return 'failed';
    return 'pending';
  }

  function fileIcon(filename) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    switch (ext) {
      case 'pdf': return '📄';
      case 'docx': return '📝';
      case 'txt': return '📃';
      case 'md': return '📑';
      default: return '📎';
    }
  }

  function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  }

  // ── Tab Switching ─────────────────────────────────────────────────
  function switchTab(name) {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  }

  // ── Collections ───────────────────────────────────────────────────
  async function loadCollections() {
    try {
      const data = await API.get('/api/documents/collections');
      const names = data.items.map(c => c.name);
      state.collections = names.length ? names : ['documents'];

      const selects = ['uploadCollection', 'searchCollection', 'researchCollection', 'chatCollection', 'docFilterCollection'];
      selects.forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        const current = sel.value;
        sel.innerHTML = state.collections.map(n =>
          `<option value="${escapeHtml(n)}"${n === current ? ' selected' : ''}>${escapeHtml(n)}</option>`
        ).join('');
        if (state.collections.includes(current)) sel.value = current;
      });
    } catch (e) {
      console.warn('Failed to load collections:', e);
    }
  }

  // ── Upload ────────────────────────────────────────────────────────
  async function handleUpload(files) {
    const progress = els.uploadProgress;
    const results = els.uploadResults;
    progress.classList.remove('hidden');
    progress.innerHTML = '';
    results.innerHTML = '';

    for (const file of files) {
      const item = document.createElement('div');
      item.className = 'upload-progress-item';
      item.innerHTML = `<span class="status-dot loading"></span> ${escapeHtml(file.name)} (${formatSize(file.size)})`;
      progress.appendChild(item);

      try {
        const res = await API.upload(file, els.uploadCollection.value);
        item.innerHTML = `<span class="status-dot success"></span> ✅ ${escapeHtml(file.name)} — ${res.status || 'uploaded'}`;
      } catch (e) {
        item.innerHTML = `<span class="status-dot error"></span> ❌ ${escapeHtml(file.name)} — ${escapeHtml(e.message)}`;
      }
    }

    setTimeout(() => progress.classList.add('hidden'), 4000);
    loadDocuments();
  }

  // ── Documents ─────────────────────────────────────────────────────
  async function loadDocuments() {
    const container = els.docList;
    try {
      const params = new URLSearchParams({ page: '1', per_page: '50' });
      const col = els.docFilterCollection?.value;
      if (col) params.set('collection_name', col);

      const data = await API.get('/api/documents?' + params.toString());
      state.docs = data.items || [];

      if (!state.docs.length) {
        container.innerHTML = '<div class="empty-state">No documents uploaded yet.</div>';
        return;
      }

      container.innerHTML = state.docs.map(d => `
        <div class="doc-item">
          <span class="doc-icon">${fileIcon(d.filename)}</span>
          <div class="doc-info">
            <div class="doc-name">${escapeHtml(d.filename)}</div>
            <div class="doc-meta">
              <span>${formatSize(d.filesize)}</span>
              <span>${escapeHtml(d.collection_name)}</span>
              <span>${d.chunk_count || 0} chunks</span>
              <span>${d.created_at ? new Date(d.created_at).toLocaleDateString() : ''}</span>
            </div>
          </div>
          <span class="doc-status ${statusClass(d.status)}">${escapeHtml(d.status)}</span>
          <button class="doc-delete" data-id="${escapeHtml(d.id)}" title="Delete">🗑</button>
        </div>
      `).join('');

      // Delete handlers
      container.querySelectorAll('.doc-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
          if (!confirm('Delete this document?')) return;
          try {
            await API.deleteDocument(btn.dataset.id);
            toast('Document deleted', 'success');
            loadDocuments();
          } catch (e) {
            toast(e.message, 'error');
          }
        });
      });

      // Update status indicator
      const counts = {};
      state.docs.forEach(d => { counts[d.status] = (counts[d.status] || 0) + 1; });
      const parts = Object.entries(counts).map(([k, v]) => `${v} ${k}`);
      els.navStatus.textContent = parts.join(' · ') || '';

    } catch (e) {
      container.innerHTML = `<div class="error-state">Failed to load documents: ${escapeHtml(e.message)}</div>`;
    }
  }

  // ── Search ────────────────────────────────────────────────────────
  async function runSearch() {
    const query = els.searchQuery.value.trim();
    if (!query) { toast('Enter a search query', 'error'); return; }

    const container = els.searchResults;
    container.innerHTML = '<div class="empty-state">Searching…</div>';

    try {
      const data = await API.search(query, {
        collection: els.searchCollection.value,
        limit: parseInt(els.searchLimit.value) || 5,
        rerank: els.searchRerank.checked,
      });

      const results = data.results || [];
      if (!results.length) {
        container.innerHTML = '<div class="empty-state">No results found. Try a different query or collection.</div>';
        return;
      }

      container.innerHTML = results.map((r, i) => `
        <div class="search-result-item">
          <div class="search-result-header">
            <span class="search-result-source">
              ${escapeHtml(r.metadata?.filename || r.parent_doc_id || `Result ${i + 1}`)}
            </span>
            <span class="search-result-score">Score: ${(r.score * 100).toFixed(1)}%</span>
          </div>
          <div class="search-result-content">${escapeHtml(r.content)}</div>
          <div class="search-result-meta">
            ${r.metadata?.page ? `<span>Page ${r.metadata.page}</span>` : ''}
            ${r.metadata?.chunk_index !== undefined ? `<span>Chunk ${r.metadata.chunk_index}</span>` : ''}
          </div>
        </div>
      `).join('');
    } catch (e) {
      container.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
    }
  }

  // ── Research ──────────────────────────────────────────────────────
  // Streams Server-Sent Events from POST /api/research/report/stream and
  // resolves with the final report. `handlers.onPhase(evt)` is called for
  // each live progress phase as it arrives.
  async function streamReport(payload, handlers) {
    const res = await fetch('/api/research/report/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Stream failed (${res.status})`);
    }
    if (!res.body) throw new Error('Streaming is not supported by this browser');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let report = null;

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep;
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = raw.split('\n').find(l => l.startsWith('data:'));
        if (!dataLine) continue;

        let evt;
        try {
          evt = JSON.parse(dataLine.slice(5).trim());
        } catch {
          continue;
        }

        if (evt.type === 'phase') {
          handlers.onPhase && handlers.onPhase(evt);
        } else if (evt.type === 'report') {
          report = evt.report;
        } else if (evt.type === 'error') {
          throw new Error(evt.message || 'Report generation failed');
        }
      }
    }

    if (!report) throw new Error('Stream ended without a report.');
    return report;
  }

  // Appends a completed/current step to the live progress log, collapsing
  // consecutive repeats of the same tool so long search loops don't spam it.
  function addResearchStep(evt) {
    const log = els.researchStepLog;
    if (!log) return;
    const prev = log.lastElementChild;
    if (prev && prev.dataset.tool === evt.tool) return;
    const step = document.createElement('div');
    step.className = 'research-step';
    step.dataset.tool = evt.tool;
    step.textContent = evt.message;
    log.appendChild(step);
    log.scrollTop = log.scrollHeight;
  }

  async function runResearch() {
    const query = els.researchQuery.value.trim();
    if (!query) { toast('Enter a research topic', 'error'); return; }

    const container = els.researchResults;
    const status = els.researchStatus;
    const statusText = els.researchStatusText;
    const stepLog = els.researchStepLog;
    const btn = els.researchBtn;

    btn.disabled = true;
    status.classList.remove('hidden');
    statusText.textContent = 'Preparing the research agent…';
    stepLog.innerHTML = '';
    container.innerHTML = '';

    try {
      const report = await streamReport({
        query,
        collection_name: els.researchCollection.value,
        limit: parseInt(els.researchLimit.value) || 10,
        model: els.researchModel.value,
        use_web: els.researchUseWeb.checked,
        use_web_fetch: els.researchUseWebFetch.checked,
        use_web_fetch_local: els.researchUseWebFetchLocal.checked,
      }, {
        onPhase: (evt) => {
          statusText.textContent = evt.message;
          addResearchStep(evt);
        },
      });

      status.classList.add('hidden');
      renderReport(report, container);

    } catch (e) {
      status.classList.add('hidden');
      container.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
    } finally {
      btn.disabled = false;
    }
  }

  function renderReport(report, container) {
    if (!report || !report.title) {
      container.innerHTML = '<div class="error-state">Failed to generate report — empty response.</div>';
      return;
    }

    const findings = (report.key_findings || []).map(f => `<li>${escapeHtml(f)}</li>`).join('');
    const images = (report.images || []).map(im => `
      <figure class="report-image">
        <img src="/api/images/${encodeURIComponent(im.image_id)}"
             alt="${escapeHtml(im.description || 'Report image')}" loading="lazy" />
        ${im.description ? `<figcaption>${escapeHtml(im.description)}${im.page_num != null ? ` — p.${im.page_num}` : ''}</figcaption>` : ''}
      </figure>
    `).join('');
    const gaps = (report.gaps || []).map(g => `<li>${escapeHtml(g)}</li>`).join('');
    const sources = (report.sources || []).map(s => `
      <div class="report-source">
        <div class="report-source-title">${escapeHtml(s.title)}</div>
        <div class="report-source-relevance">${escapeHtml(s.relevance)}</div>
        <div class="report-source-excerpt">"${escapeHtml(s.excerpt)}"</div>
      </div>
    `).join('');
    const sections = (report.sections || []).map(sec => `
      <div class="report-section">
        <h3>${escapeHtml(sec.heading)}</h3>
        <p>${escapeHtml(sec.content).replace(/\n/g, '<br/>')}</p>
        ${sec.sources?.length ? `<p style="font-size:0.8rem;color:var(--text-muted);margin-top:6px">Sources: ${sec.sources.map(s => escapeHtml(s)).join(', ')}</p>` : ''}
      </div>
    `).join('');

    const md = reportToMarkdown(report);

    container.innerHTML = `
      <div class="research-report">
        <div class="report-toolbar">
          <span class="report-title">${escapeHtml(report.title)}</span>
          <button class="btn btn-sm copy-btn" title="Copy as Markdown">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
            </svg>
            Copy Markdown
          </button>
        </div>
        ${report.summary ? `<div class="report-summary">${escapeHtml(report.summary).replace(/\n/g, '<br/>')}</div>` : ''}
        ${images ? `<h3 style="margin-bottom:8px">🖼️ Images</h3><div class="report-images">${images}</div>` : ''}
        ${findings ? `<h3 style="margin-bottom:8px">🔑 Key Findings</h3><ul class="report-findings">${findings}</ul>` : ''}
        ${sections}
        ${gaps ? `<h3 style="margin-bottom:8px">⚠️ Knowledge Gaps</h3><ul class="report-gaps">${gaps}</ul>` : ''}
        ${sources ? `<h3 style="margin-bottom:8px">📚 Sources</h3><div class="report-sources">${sources}</div>` : ''}
        ${report.generated_at ? `<p style="font-size:0.78rem;color:var(--text-muted);margin-top:16px">Generated: ${new Date(report.generated_at).toLocaleString()}</p>` : ''}
      </div>
    `;

    // Copy-to-clipboard handler
    const copyBtn = container.querySelector('.copy-btn');
    if (copyBtn) {
      markdownStore.set(copyBtn, md);
      copyBtn.addEventListener('click', async () => {
        const text = markdownStore.get(copyBtn);
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          copyBtn.textContent = '✓ Copied!';
          setTimeout(() => {
            copyBtn.innerHTML = ''
              + '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
              + '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>'
              + '<path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>'
              + '</svg> Copy Markdown';
          }, 2000);
        } catch {
          toast('Failed to copy — browser may not support clipboard API', 'error');
        }
      });
    }
  }

  function reportToMarkdown(report) {
    const lines = [];

    // Title
    if (report.title) lines.push(`# ${report.title}\n`);

    // Summary
    if (report.summary) {
      lines.push('## Summary\n');
      lines.push(report.summary + '\n');
    }

    // Images
    if (report.images?.length) {
      lines.push('## Images\n');
      report.images.forEach(im => {
        const src = im.url || `/api/images/${encodeURIComponent(im.image_id)}`;
        lines.push(`![${im.description || 'Image'}](${src})`);
        if (im.page_num != null) lines.push(`*Page ${im.page_num}*`);
        lines.push('');
      });
    }

    // Key findings
    if (report.key_findings?.length) {
      lines.push('## Key Findings\n');
      report.key_findings.forEach(f => lines.push(`- ${f}`));
      lines.push('');
    }

    // Sections
    if (report.sections?.length) {
      report.sections.forEach(sec => {
        lines.push(`## ${sec.heading}\n`);
        lines.push(sec.content + '\n');
        if (sec.sources?.length) {
          lines.push(`*Sources: ${sec.sources.join(', ')}*\n`);
        }
      });
    }

    // Knowledge gaps
    if (report.gaps?.length) {
      lines.push('## Knowledge Gaps\n');
      report.gaps.forEach(g => lines.push(`- ${g}`));
      lines.push('');
    }

    // Sources
    if (report.sources?.length) {
      lines.push('## Sources\n');
      report.sources.forEach(s => {
        lines.push(`### ${s.title}`);
        lines.push(`*${s.relevance}*`);
        lines.push(`> ${s.excerpt}`);
        lines.push('');
      });
    }

    // Timestamp
    if (report.generated_at) {
      const d = new Date(report.generated_at);
      lines.push(`---\n*Generated: ${d.toLocaleString()}*`);
    }

    return lines.join('\n');
  }

  // ── Chat ─────────────────────────────────────────────────────────
  // Multi-turn agentic Q&A grounded in the RAG store. The client owns the
  // conversation: `chatState.messages` is the full history sent to the backend
  // each turn (minus the new message), and each assistant turn appends a
  // streamed bubble with a collapsible "Sources" list.
  const chatState = {
    messages: [],  // [{role, content}] — history sent to the backend
    busy: false,
  };

  function chatScrollToBottom() {
    const m = els.chatMessages;
    if (m) m.scrollTop = m.scrollHeight;
  }

  function hideChatEmpty() {
    const el = document.getElementById('chatEmpty');
    if (el) el.classList.add('hidden');
  }

  // Appends a user message bubble.
  function addChatMessage(role, content) {
    hideChatEmpty();
    const wrap = document.createElement('div');
    wrap.className = 'chat-msg ' + role;
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    const contentEl = document.createElement('div');
    contentEl.className = 'chat-bubble-content';
    contentEl.textContent = content;
    bubble.appendChild(contentEl);
    wrap.appendChild(bubble);
    els.chatMessages.appendChild(wrap);
    chatScrollToBottom();
  }

  // Creates an empty assistant bubble and returns its content element so the
  // streaming tokens can be appended into it.
  function createAssistantBubble() {
    hideChatEmpty();
    const wrap = document.createElement('div');
    wrap.className = 'chat-msg assistant';
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    const contentEl = document.createElement('div');
    contentEl.className = 'chat-bubble-content';
    bubble.appendChild(contentEl);
    wrap.appendChild(bubble);
    els.chatMessages.appendChild(wrap);
    chatScrollToBottom();
    return contentEl;
  }

  // Live "agent is working" indicator showing the current tool phase.
  function showChatTyping(message) {
    hideChatEmpty();
    removeChatTyping();
    const el = document.createElement('div');
    el.className = 'chat-msg assistant';
    el.id = 'chatTyping';
    el.innerHTML =
      '<div class="chat-bubble chat-typing">'
      + '<span class="chat-typing-dots"><i></i><i></i><i></i></span>'
      + '<span class="chat-typing-text"></span>'
      + '</div>';
    el.querySelector('.chat-typing-text').textContent = message;
    els.chatMessages.appendChild(el);
    chatScrollToBottom();
  }

  function updateChatTyping(message) {
    const el = document.getElementById('chatTyping');
    if (el) el.querySelector('.chat-typing-text').textContent = message;
  }

  function removeChatTyping() {
    const el = document.getElementById('chatTyping');
    if (el) el.remove();
  }

  // Renders the collapsible list of RAG sources under an assistant bubble.
  function renderChatSources(contentEl, sources) {
    const details = document.createElement('details');
    details.className = 'chat-sources';
    const summary = document.createElement('summary');
    summary.textContent = `📚 Sources (${sources.length})`;
    details.appendChild(summary);

    const list = document.createElement('div');
    list.className = 'chat-sources-list';
    sources.forEach(s => {
      const item = document.createElement('div');
      item.className = 'chat-source';
      const header = document.createElement('div');
      header.className = 'chat-source-header';
      const name = document.createElement('span');
      name.className = 'chat-source-name';
      name.textContent = s.filename || 'Unknown source';
      const score = document.createElement('span');
      score.className = 'chat-source-score';
      score.textContent = `Score: ${((s.score || 0) * 100).toFixed(1)}%`;
      header.appendChild(name);
      header.appendChild(score);
      const excerpt = document.createElement('div');
      excerpt.className = 'chat-source-excerpt';
      excerpt.textContent = s.content || '';
      item.appendChild(header);
      item.appendChild(excerpt);
      list.appendChild(item);
    });
    details.appendChild(list);
    if (contentEl.parentElement) contentEl.parentElement.appendChild(details);
  }

  // Renders the RAG document images an assistant message references as a
  // thumbnail strip under the bubble. Clicking an image opens a lightbox.
  function renderChatImages(contentEl, images) {
    const strip = document.createElement('div');
    strip.className = 'chat-images';
    images.forEach(im => {
      const figure = document.createElement('figure');
      figure.className = 'chat-image';
      const img = document.createElement('img');
      img.src = '/api/images/' + encodeURIComponent(im.image_id);
      img.alt = im.description || 'Document image';
      img.loading = 'lazy';
      img.addEventListener('error', () => figure.remove());
      img.addEventListener('click', () => showChatImageLightbox(im));
      figure.appendChild(img);
      if (im.description) {
        const cap = document.createElement('figcaption');
        cap.textContent = im.description
          + (im.page_num != null ? ` — p.${im.page_num}` : '');
        figure.appendChild(cap);
      }
      strip.appendChild(figure);
    });
    if (contentEl.parentElement && strip.children.length) {
      contentEl.parentElement.appendChild(strip);
    }
  }

  // Lightbox overlay for a clicked RAG image; click anywhere to dismiss.
  function showChatImageLightbox(im) {
    const overlay = document.createElement('div');
    overlay.className = 'chat-lightbox';
    const img = document.createElement('img');
    img.src = '/api/images/' + encodeURIComponent(im.image_id);
    img.alt = im.description || 'Document image';
    const cap = document.createElement('div');
    cap.className = 'chat-lightbox-caption';
    cap.textContent = im.description || '';
    overlay.appendChild(img);
    overlay.appendChild(cap);
    overlay.addEventListener('click', () => overlay.remove());
    document.body.appendChild(overlay);
  }

  // ── Markdown rendering (self-contained, XSS-safe) ─────────────────
  // Renders the CommonMark subset the assistant produces (headings, lists,
  // code, bold/italic, links, images, blockquotes, tables) into HTML.
  // All input is HTML-escaped first and link/image URLs are sanitized, so
  // model output can never inject raw markup or script.
  function mdEscape(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function mdSanitizeUrl(url) {
    const u = (url || '').trim();
    if (!u) return '';
    // Allow fragments, relative paths (incl. /api/images/...), http(s), mailto.
    if (/^(#|\/|\.\/|\.\.\/)/.test(u)) return u;
    if (/^https?:\/\//i.test(u)) return u;
    if (/^mailto:/i.test(u)) return u;
    return '';
  }

  function mdInline(text) {
    let t = text;
    // Inline code (protect first so other rules don't touch it)
    t = t.replace(/`([^`\n]+)`/g, (m, code) => '<code>' + code + '</code>');
    // Images ![alt](url)
    t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, url) => {
      const src = mdSanitizeUrl(url);
      if (!src) return m;
      return '<img src="' + src + '" alt="'
        + alt.replace(/"/g, '&quot;') + '" loading="lazy" />';
    });
    // Links [text](url)
    t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
      const href = mdSanitizeUrl(url);
      if (!href) return m;
      return '<a href="' + href + '" target="_blank" rel="noopener noreferrer">'
        + label + '</a>';
    });
    // Bold
    t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Strikethrough
    t = t.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    // Italic — only when not mid-word (avoids things like a*b*c)
    t = t.replace(/(^|[\s(])\*([^*\s][^*]*?)\*([\s).,!?;:]|$)/g, '$1<em>$2</em>$3');
    t = t.replace(/(^|[\s(])_([^_\s][^_]*?)_([\s).,!?;:]|$)/g, '$1<em>$2</em>$3');
    return t;
  }

  function isTableRow(line) {
    return /^\s*\|.*\|\s*$/.test(line) && line.indexOf('|') !== -1;
  }

  function isTableDelimiter(line) {
    return /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$/.test(line);
  }

  function tableRowCells(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '')
      .split('|').map(c => c.trim());
  }

  function renderMarkdown(md) {
    if (!md) return '';
    const escaped = mdEscape(md);

    // Protect fenced code blocks so block/inline rules never touch them.
    const codeBlocks = [];
    const text = escaped.replace(/```[^\n]*\n([\s\S]*?)```/g, (m, code) => {
      codeBlocks.push(code);
      return '\u0000CODE\u0000' + (codeBlocks.length - 1) + '\u0000';
    });

    const lines = text.split('\n');
    const html = [];
    let i = 0;

    const isBlank = (l) => l.trim() === '';
    // After escaping, '>' became '&gt;'.
    const quoteRe = /^\s*&gt;\s?/;
    const hRe = /^(#{1,6})\s+(.*)$/;
    const ulRe = /^\s*[-*+]\s+/;
    const olRe = /^\s*\d+\.\s+/;
    const hrRe = /^\s*([-*_])\s*(\1\s*){2,}\s*$/;
    const isCodePlaceholder = (l) => /^\u0000CODE\u0000\d+\u0000$/.test(l);
    const isTableStart = (l, n) => isTableRow(l) && n + 1 < lines.length
      && isTableDelimiter(lines[n + 1]);

    while (i < lines.length) {
      const line = lines[i];

      // Fenced code block
      if (isCodePlaceholder(line)) {
        const idx = Number(line.match(/\u0000CODE\u0000(\d+)\u0000/)[1]);
        html.push('<pre><code>' + codeBlocks[idx] + '</code></pre>');
        i++;
        continue;
      }

      // Heading
      const h = line.match(hRe);
      if (h) {
        const level = h[1].length;
        html.push(`<h${level}>` + mdInline(h[2]) + `</h${level}>`);
        i++;
        continue;
      }

      // Horizontal rule
      if (hrRe.test(line)) {
        html.push('<hr/>');
        i++;
        continue;
      }

      // Blockquote (consecutive "> " lines)
      if (quoteRe.test(line)) {
        const quote = [];
        while (i < lines.length && quoteRe.test(lines[i])) {
          quote.push(lines[i].replace(quoteRe, ''));
          i++;
        }
        html.push('<blockquote>' + mdInline(quote.join('\n')) + '</blockquote>');
        continue;
      }

      // Table (a pipe row followed by a delimiter row)
      if (isTableStart(line, i)) {
        const header = tableRowCells(line);
        i += 2;
        const rows = [];
        while (i < lines.length && isTableRow(lines[i]) && lines[i].trim() !== '') {
          rows.push('<tr>' + tableRowCells(lines[i])
            .map(c => '<td>' + mdInline(c) + '</td>').join('') + '</tr>');
          i++;
        }
        html.push(
          '<table><thead><tr>'
          + header.map(c => '<th>' + mdInline(c) + '</th>').join('')
          + '</tr></thead><tbody>' + rows.join('') + '</tbody></table>'
        );
        continue;
      }

      // Unordered list
      if (ulRe.test(line)) {
        const items = [];
        while (i < lines.length && ulRe.test(lines[i])) {
          items.push('<li>' + mdInline(lines[i].replace(ulRe, '')) + '</li>');
          i++;
        }
        html.push('<ul>' + items.join('') + '</ul>');
        continue;
      }

      // Ordered list
      if (olRe.test(line)) {
        const items = [];
        while (i < lines.length && olRe.test(lines[i])) {
          items.push('<li>' + mdInline(lines[i].replace(olRe, '')) + '</li>');
          i++;
        }
        html.push('<ol>' + items.join('') + '</ol>');
        continue;
      }

      // Paragraph: gather until a blank line or a new block start
      if (!isBlank(line)) {
        const para = [];
        while (
          i < lines.length
          && !isBlank(lines[i])
          && !hRe.test(lines[i])
          && !ulRe.test(lines[i])
          && !olRe.test(lines[i])
          && !quoteRe.test(lines[i])
          && !hrRe.test(lines[i])
          && !isCodePlaceholder(lines[i])
          && !isTableStart(lines[i], i)
        ) {
          para.push(lines[i]);
          i++;
        }
        html.push('<p>' + mdInline(para.join('<br/>')) + '</p>');
        continue;
      }

      i++; // blank line
    }

    return html.join('\n');
  }

  // Streams Server-Sent Events from POST /api/chat/stream and resolves with
  // the final assistant message. `handlers.onPhase(evt)` / `onToken(text)` are
  // called live as phases and text tokens arrive.
  async function streamChat(payload, handlers) {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Stream failed (${res.status})`);
    }
    if (!res.body) throw new Error('Streaming is not supported by this browser');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let final = null;

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep;
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = raw.split('\n').find(l => l.startsWith('data:'));
        if (!dataLine) continue;

        let evt;
        try {
          evt = JSON.parse(dataLine.slice(5).trim());
        } catch {
          continue;
        }

        if (evt.type === 'phase') {
          handlers.onPhase && handlers.onPhase(evt);
        } else if (evt.type === 'token') {
          handlers.onToken && handlers.onToken(evt.text);
        } else if (evt.type === 'message') {
          final = evt.message;
        } else if (evt.type === 'error') {
          throw new Error(evt.message || 'Chat failed');
        }
      }
    }

    if (!final) throw new Error('Stream ended without a message.');
    return final;
  }

  async function sendChat() {
    const text = els.chatInput.value.trim();
    if (!text || chatState.busy) return;

    // Commit the user message to history + UI.
    chatState.messages.push({ role: 'user', content: text });
    addChatMessage('user', text);
    els.chatInput.value = '';
    autoGrowChatInput();
    els.chatSendBtn.disabled = true;
    chatState.busy = true;

    const contentEl = createAssistantBubble();
    let full = '';
    showChatTyping('Thinking…');

    try {
      const final = await streamChat({
        message: text,
        // History excludes the new message — the backend appends it.
        messages: chatState.messages.slice(0, -1),
        collection_name: els.chatCollection.value,
        limit: parseInt(els.chatLimit.value) || 5,
        model: els.chatModel.value,
        use_web: els.chatUseWeb.checked,
        use_web_fetch: els.chatUseWebFetch.checked,
        use_web_fetch_local: els.chatUseWebFetchLocal.checked,
      }, {
        onPhase: (evt) => updateChatTyping(evt.message),
        onToken: (t) => {
          // The first token means the answer has started — drop the
          // typing/working indicator so only the streaming bubble remains.
          if (!full) removeChatTyping();
          full += t;
          contentEl.innerHTML = renderMarkdown(full);
          chatScrollToBottom();
        },
      });

      removeChatTyping();
      // Defensive: if no tokens streamed (edge case), use the final content.
      if (!full) full = final.content || '';
      contentEl.innerHTML = renderMarkdown(full);
      if (final.images && final.images.length) {
        renderChatImages(contentEl, final.images);
      }
      if (final.sources && final.sources.length) {
        renderChatSources(contentEl, final.sources);
      }
      chatState.messages.push({
        role: 'assistant',
        content: final.content || full,
      });
      chatScrollToBottom();
    } catch (e) {
      removeChatTyping();
      contentEl.textContent = '⚠️ ' + e.message;
      contentEl.classList.add('chat-error');
    } finally {
      chatState.busy = false;
      els.chatSendBtn.disabled = false;
      els.chatInput.focus();
      chatScrollToBottom();
    }
  }

  function clearChat() {
    chatState.messages = [];
    els.chatMessages.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'chat-empty';
    empty.id = 'chatEmpty';
    empty.innerHTML =
      '<div class="chat-empty-icon">💬</div>'
      + '<p>Ask a question about your documents.</p>'
      + '<p class="chat-empty-hint">e.g. "What are the key findings in the quarterly report?"</p>';
    els.chatMessages.appendChild(empty);
    els.chatInput.focus();
    autoGrowChatInput();
  }

  function autoGrowChatInput() {
    els.chatInput.style.height = 'auto';
    els.chatInput.style.height = Math.min(els.chatInput.scrollHeight, 160) + 'px';
  }

  // ── Initialization ────────────────────────────────────────────────
  async function loadVersion() {
    try {
      const data = await API.get('/api/version');
      const version = data?.version;
      if (version && els.appVersion) {
        els.appVersion.textContent = `v${version}`;
      }
    } catch (e) {
      console.warn('Failed to load version:', e);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    // DOM refs
    els = {
      toast: document.getElementById('toast'),
      navStatus: document.getElementById('navStatus'),
      appVersion: document.getElementById('appVersion'),
      uploadZone: document.getElementById('uploadZone'),
      fileInput: document.getElementById('fileInput'),
      uploadCollection: document.getElementById('uploadCollection'),
      uploadProgress: document.getElementById('uploadProgress'),
      uploadResults: document.getElementById('uploadResults'),
      docList: document.getElementById('docList'),
      docFilterCollection: document.getElementById('docFilterCollection'),
      refreshDocs: document.getElementById('refreshDocs'),
      searchQuery: document.getElementById('searchQuery'),
      searchBtn: document.getElementById('searchBtn'),
      searchCollection: document.getElementById('searchCollection'),
      searchLimit: document.getElementById('searchLimit'),
      searchRerank: document.getElementById('searchRerank'),
      searchResults: document.getElementById('searchResults'),
      researchQuery: document.getElementById('researchQuery'),
      researchBtn: document.getElementById('researchBtn'),
      researchCollection: document.getElementById('researchCollection'),
      researchLimit: document.getElementById('researchLimit'),
      researchModel: document.getElementById('researchModel'),
      researchUseWeb: document.getElementById('researchUseWeb'),
      researchUseWebFetch: document.getElementById('researchUseWebFetch'),
      researchUseWebFetchLocal: document.getElementById('researchUseWebFetchLocal'),
      researchStatus: document.getElementById('researchStatus'),
      researchStatusText: document.getElementById('researchStatusText'),
      researchStepLog: document.getElementById('researchStepLog'),
      researchResults: document.getElementById('researchResults'),
      chatCollection: document.getElementById('chatCollection'),
      chatLimit: document.getElementById('chatLimit'),
      chatModel: document.getElementById('chatModel'),
      chatUseWeb: document.getElementById('chatUseWeb'),
      chatUseWebFetch: document.getElementById('chatUseWebFetch'),
      chatUseWebFetchLocal: document.getElementById('chatUseWebFetchLocal'),
      chatClear: document.getElementById('chatClear'),
      chatMessages: document.getElementById('chatMessages'),
      chatInput: document.getElementById('chatInput'),
      chatSendBtn: document.getElementById('chatSendBtn'),
      chatEmpty: document.getElementById('chatEmpty'),
    };

    // Tab switching
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Upload zone: click to select
    els.uploadZone.addEventListener('click', () => els.fileInput.click());

    // Upload zone: drag & drop
    els.uploadZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      els.uploadZone.classList.add('dragover');
    });

    els.uploadZone.addEventListener('dragleave', () => {
      els.uploadZone.classList.remove('dragover');
    });

    els.uploadZone.addEventListener('drop', (e) => {
      e.preventDefault();
      els.uploadZone.classList.remove('dragover');
      if (e.dataTransfer.files.length) {
        handleUpload(e.dataTransfer.files);
      }
    });

    // File input change
    els.fileInput.addEventListener('change', () => {
      if (els.fileInput.files.length) {
        handleUpload(els.fileInput.files);
        els.fileInput.value = '';
      }
    });

    // Search
    els.searchBtn.addEventListener('click', runSearch);
    els.searchQuery.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runSearch();
    });

    // Research
    els.researchBtn.addEventListener('click', runResearch);
    els.researchQuery.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runResearch();
    });

    // Chat
    els.chatSendBtn.addEventListener('click', sendChat);
    els.chatInput.addEventListener('keydown', (e) => {
      // Enter sends; Shift+Enter inserts a newline.
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChat();
      }
    });
    els.chatInput.addEventListener('input', autoGrowChatInput);
    els.chatClear.addEventListener('click', clearChat);

    // Refresh docs
    els.refreshDocs.addEventListener('click', () => {
      loadCollections();
      loadDocuments();
    });

    // Filter docs by collection
    els.docFilterCollection?.addEventListener('change', loadDocuments);

    // Load initial data
    loadVersion();
    loadCollections();
    loadDocuments();
  });

})();
