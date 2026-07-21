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

    async research(query, opts) {
      return this.post('/api/research/report', {
        query,
        collection_name: opts.collection || 'documents',
        limit: opts.limit || 10,
        model: opts.model || 'claude-sonnet-4-20250514',
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

      const selects = ['uploadCollection', 'searchCollection', 'researchCollection', 'docFilterCollection'];
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
  async function runResearch() {
    const query = els.researchQuery.value.trim();
    if (!query) { toast('Enter a research topic', 'error'); return; }

    const container = els.researchResults;
    const status = els.researchStatus;
    const statusText = els.researchStatusText;
    const btn = els.researchBtn;

    btn.disabled = true;
    status.classList.remove('hidden');
    statusText.textContent = 'Searching documents and generating report…';
    container.innerHTML = '';

    try {
      const report = await API.research(query, {
        collection: els.researchCollection.value,
        limit: parseInt(els.researchLimit.value) || 10,
        model: els.researchModel.value,
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
          <button class="btn btn-sm copy-btn" data-md="${escapeHtml(md)}" title="Copy as Markdown">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
            </svg>
            Copy Markdown
          </button>
        </div>
        ${report.summary ? `<div class="report-summary">${escapeHtml(report.summary).replace(/\n/g, '<br/>')}</div>` : ''}
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
      copyBtn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(copyBtn.dataset.md);
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

  // ── Initialization ────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    // DOM refs
    els = {
      toast: document.getElementById('toast'),
      navStatus: document.getElementById('navStatus'),
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
      researchStatus: document.getElementById('researchStatus'),
      researchStatusText: document.getElementById('researchStatusText'),
      researchResults: document.getElementById('researchResults'),
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

    // Refresh docs
    els.refreshDocs.addEventListener('click', () => {
      loadCollections();
      loadDocuments();
    });

    // Filter docs by collection
    els.docFilterCollection?.addEventListener('change', loadDocuments);

    // Load initial data
    loadCollections();
    loadDocuments();
  });

})();
