
// ══════════════════════════════════════════════════════════════
// ORÁCULO DE INTELIGENCIA — Application Logic
// ══════════════════════════════════════════════════════════════

// ─── State ───
const state = {
  currentSection: 'dashboard',
  records: [],
  filteredRecords: [],
  currentPage: 1,
  recordsPage: 1,
  perPage: 25,
  searchHistory: [],
  lastKeyword: '',
};

// ─── Navigation ───
document.querySelectorAll('.sidebar-item').forEach(item => {
  item.addEventListener('click', () => {
    navigateTo(item.dataset.section);
  });
});

function navigateTo(section) {
  document.querySelectorAll('.sidebar-item').forEach(n => n.classList.remove('active'));
  document.querySelector(`.sidebar-item[data-section="${section}"]`).classList.add('active');
  document.querySelectorAll('.sec').forEach(s => s.classList.remove('active'));
  const secEl = document.getElementById(`sec-${section}`);
  if (secEl) secEl.classList.add('active');
  state.currentSection = section;
  
  if (section === 'records') renderRecords();
  if (section === 'stats') renderStats();
  if (section === 'history') renderHistory();
  if (section === 'combo') refreshComboStats();
  if (section === 'proxy') refreshProxyStats();
  if (section === 'deploy') {
    fetchDeployStatus();
    // Auto-refresh every 30 seconds
    if (deployRefreshInterval) clearInterval(deployRefreshInterval);
    deployRefreshInterval = setInterval(fetchDeployStatus, 30000);
  } else {
    // Clear refresh when leaving deploy section
    if (deployRefreshInterval) {
      clearInterval(deployRefreshInterval);
      deployRefreshInterval = null;
    }
  }
}

// ─── Notifications ───
function showToast(msg, color) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderColor = color || 'var(--border)';
  t.style.color = color || 'var(--accent2)';
  t.className = 'toast show';
  setTimeout(() => { t.className = 'toast'; }, 3000);
}

// ─── Clock ───
function updateClock() {
  const now = new Date();
  document.getElementById('topTime').textContent = now.toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'});
  document.getElementById('sidebarTime').textContent = now.toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'});
}
setInterval(updateClock, 1000);
updateClock();

// ─── Search Execution ───
async function executeSearch() {
  const input = document.getElementById('searchInput');
  const keyword = input.value.trim();
  const category = document.getElementById('searchCategory').value;
  const useSample = document.getElementById('useSampleData').checked;
  
  if (!keyword) {
    showToast('❌ Ingresa una palabra clave para buscar', 'var(--red)');
    return;
  }
  
  // Update UI
  const btn = document.getElementById('searchBtn');
  btn.classList.add('loading');
  btn.disabled = true;
  document.getElementById('scanBar').classList.add('active');
  document.getElementById('resultsPanel').classList.remove('active');
  
  state.lastKeyword = keyword;
  
  try {
    // Try API first
    let records = [];
    let sources = [];
    let stats = {};
    
    try {
      const resp = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          keyword: keyword,
          categories: category ? [category] : null,
          sample: useSample,
          max_dorks: 5,
        }),
        signal: AbortSignal.timeout(5000),
      });
      
      if (resp.ok) {
        const data = await resp.json();
        if (data.success) {
          records = data.data.records || [];
          sources = data.data.sources || [];
          stats = data.data.stats || {};
        }
      }
    } catch (e) {
      // API unavailable — use local sample data
      console.log('API unavailable, using local data');
    }
    
    // If no records from API, generate locally
    if (records.length === 0) {
      records = generateSampleRecords(keyword, 30 + Math.floor(Math.random() * 40));
      sources = ['local_generator', 'sample_data'];
      
      const byType = {};
      const bySeverity = {};
      records.forEach(r => {
        byType[r.record_type] = (byType[r.record_type] || 0) + 1;
        bySeverity[r.severity] = (bySeverity[r.severity] || 0) + 1;
      });
      stats = { by_type: byType, by_severity: bySeverity };
    }
    
    // Store and display
    state.records = records;
    state.filteredRecords = [...records];
    state.currentPage = 1;
    
    // Add to search history
    state.searchHistory.unshift({
      keyword: keyword,
      timestamp: new Date().toISOString(),
      total: records.length,
    });
    
    // Show results
    document.getElementById('resultsKeyword').innerHTML = `🔍 <strong>"${escapeHtml(keyword)}"</strong>`;
    document.getElementById('resultsCount').textContent = `${records.length} registros`;
    document.getElementById('resultsTime').textContent = `· ${new Date().toLocaleTimeString()}`;
    
    renderResultsPage();
    document.getElementById('resultsPanel').classList.add('active');
    
    // Update sidebar badges
    document.getElementById('sidebarSearchCount').textContent = state.searchHistory.length;
    
    // Update dashboard KPIs
    updateDashboardKPIs();
    
    // Chat notification
    const notif = document.getElementById('chatNotif');
    notif.textContent = '1';
    notif.style.display = 'block';
    
    showToast(`✅ ${records.length} registros encontrados para "${keyword}"`, 'var(--green)');
    
  } catch (err) {
    console.error('Search error:', err);
    showToast('❌ Error en la búsqueda: ' + err.message, 'var(--red)');
  } finally {
    btn.classList.remove('loading');
    btn.disabled = false;
    document.getElementById('scanBar').classList.remove('active');
  }
}

// ─── Sample Data Generator (local) ───
function generateSampleRecords(keyword, count) {
  const domains = [
    `${keyword.toLowerCase().replace(/\\s/g,'')}.com`, 'gmail.com', 'yahoo.com', 
    'hotmail.com', 'outlook.com', 'aol.com', keyword.toLowerCase().replace(/\\s/g,'')+'.net',
    'verizon.net', 'att.net', 'sbcglobal.net', 'protonmail.com', 'icloud.com',
  ];
  const types = ['email:pass', 'email:pass', 'email:pass', 'api_key', 'ip:port', 'hash', 'config'];
  const severities = ['critical', 'high', 'medium', 'low', 'info'];
  const severitiesW = [5, 20, 35, 25, 15];
  const sources = ['pastebin', 'github', 'shodan', 'public_directory', 'telegram', 'darkweb_forum', 'leak_site'];
  
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function weightedPick(arr, weights) {
    const total = weights.reduce((a,b) => a+b, 0);
    let r = Math.random() * total;
    for (let i = 0; i < arr.length; i++) {
      r -= weights[i];
      if (r <= 0) return arr[i];
    }
    return arr[arr.length - 1];
  }
  function genPass() {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&*';
    let p = '';
    for (let i = 0; i < 8 + Math.floor(Math.random() * 14); i++) p += chars[Math.floor(Math.random() * chars.length)];
    return p;
  }
  
  const records = [];
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 365);
  
  for (let i = 0; i < count; i++) {
    const domain = pick(domains);
    const username = `user${1000 + i}`;
    const email = `${username}@${domain}`;
    const password = genPass();
    const type = pick(types);
    const severity = weightedPick(severities, severitiesW);
    const source = pick(sources);
    
    const recDate = new Date(startDate.getTime() + Math.random() * 365 * 24 * 60 * 60 * 1000);
    
    records.push({
      id: Math.random().toString(36).substring(2, 10),
      keyword: keyword,
      source_url: `https://${source.toLowerCase() === 'pastebin' ? 'pastebin.com' : source === 'github' ? 'github.com' : 'example.com'}/${Math.random().toString(36).substring(2, 10)}`,
      source_type: source,
      record_type: type,
      content_preview: type === 'email:pass' ? `${email}:${password.substring(0, 10)}***` : 
                       type === 'api_key' ? `API Key: sk-${Math.random().toString(36).substring(2, 18)}` :
                       type === 'ip:port' ? `192.168.${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}:${Math.floor(Math.random()*60000+1024)}` :
                       type === 'hash' ? `${Math.random().toString(36).substring(2, 34)}` : `Config entry for ${domain}`,       discovered_at: recDate.toISOString(),
       discovered_date: recDate.toISOString().split('T')[0],
      severity: severity,
      domain: domain,
      email: email,
      username: username,
      password: password,
      hash_value: '',
      ip_address: `192.168.${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}`,
      port: String(Math.floor(Math.random()*60000 + 1024)),
      extra_data: { source_confidence: Math.round(Math.random() * 100) / 100 },
    });
  }
  
  return records;
}

// ─── Results Rendering ───
function renderResultsPage() {
  const start = (state.currentPage - 1) * state.perPage;
  const end = start + state.perPage;
  const pageRecords = state.filteredRecords.slice(start, end);
  
  const tbody = document.getElementById('resultsBody');
  if (pageRecords.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">🔍 No hay resultados con estos filtros</td></tr>';
  } else {
    tbody.innerHTML = pageRecords.map(r => renderRecordRow(r)).join('');
  }
  
  // Pagination
  const totalPages = Math.max(1, Math.ceil(state.filteredRecords.length / state.perPage));
  document.getElementById('pageInfo').textContent = `Página ${state.currentPage} de ${totalPages} (${state.filteredRecords.length} registros)`;
  document.getElementById('prevPage').disabled = state.currentPage <= 1;
  document.getElementById('nextPage').disabled = state.currentPage >= totalPages;
}

function changePage(dir) {
  const totalPages = Math.max(1, Math.ceil(state.filteredRecords.length / state.perPage));
  if (dir === 'prev' && state.currentPage > 1) state.currentPage--;
  if (dir === 'next' && state.currentPage < totalPages) state.currentPage++;
  renderResultsPage();
}

function filterResults(filter, btn) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  
  if (filter === 'all') {
    state.filteredRecords = [...state.records];
  } else if (filter === 'critical' || filter === 'high') {
    state.filteredRecords = state.records.filter(r => r.severity === filter);
  } else {
    state.filteredRecords = state.records.filter(r => r.record_type === filter);
  }
  state.currentPage = 1;
  renderResultsPage();
}

function renderRecordRow(r) {
  const sevClass = `sev-${r.severity}`;
  const typeClass = r.record_type === 'email:pass' ? 'email' : 
                    r.record_type === 'api_key' ? 'api' :
                    r.record_type === 'ip:port' ? 'ip' :
                    r.record_type === 'hash' ? 'hash' : 'config';  const sevLabel = escapeHtml(r.severity.charAt(0).toUpperCase() + r.severity.slice(1));
  const dateStr = escapeHtml(r.discovered_date || r.discovered_at?.split('T')[0] || '—');
  const email = r.email || r.username || '—';
  const domain = r.domain || '—';
  const preview = escapeHtml(r.content_preview?.substring(0, 80) || '—');
  const source = r.source_type || '—';
  
  return `<tr>
    <td><span class="${sevClass}">● ${sevLabel}</span></td>
    <td><span class="type-badge ${typeClass}">${r.record_type}</span></td>
    <td class="email-cell">${escapeHtml(email)}</td>
    <td class="domain">${escapeHtml(domain)}</td>
    <td class="preview" title="${escapeHtml(r.content_preview || '')}">${preview}</td>
    <td class="source-cell">${escapeHtml(source)}</td>
    <td class="date-cell">${dateStr}</td>
  </tr>`;
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ─── Export ───
function exportResults() {
  const data = state.filteredRecords.length > 0 ? state.filteredRecords : state.records;
  if (data.length === 0) { showToast('❌ No hay datos para exportar', 'var(--red)'); return; }
  
  const csv = ['severidad,tipo,email,dominio,contenido,fuente,fecha'];
  data.forEach(r => {     csv.push(`"${r.severity}","${r.record_type}","${r.email||''}","${r.domain||''}","${(r.content_preview||'').replace(/"/g,'""')}","${r.source_type||''}","${r.discovered_date||''}"`);
  });
  
  const blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `oraculo_${state.lastKeyword}_${new Date().toISOString().split('T')[0]}.csv`;
  link.click();
  showToast(`📥 Exportados ${data.length} registros a CSV`, 'var(--accent2)');
}

// ─── Records Section ───
function queryRecords() {
  const keyword = document.getElementById('filterKeyword').value.trim().toLowerCase();
  const domain = document.getElementById('filterDomain').value.trim().toLowerCase();
  const type = document.getElementById('filterType').value;
  const severity = document.getElementById('filterSeverity').value;
  
  let filtered = [...state.records];
  
  if (keyword) filtered = filtered.filter(r => 
    r.keyword?.toLowerCase().includes(keyword) || 
    r.email?.toLowerCase().includes(keyword) ||
    r.domain?.toLowerCase().includes(keyword)
  );
  if (domain) filtered = filtered.filter(r => r.domain?.toLowerCase().includes(domain));
  if (type) filtered = filtered.filter(r => r.record_type === type);
  if (severity) filtered = filtered.filter(r => r.severity === severity);
  
  state.filteredRecords = filtered;
  state.recordsPage = 1;
  renderRecords();
}

function renderRecords() {
  const start = (state.recordsPage - 1) * state.perPage;
  const end = start + state.perPage;
  const pageRecords = state.filteredRecords.slice(start, end);
  
  const tbody = document.getElementById('recordsBody');
  if (pageRecords.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">📭 No hay registros con estos filtros</td></tr>';
  } else {
    tbody.innerHTML = pageRecords.map(r => renderRecordRow(r)).join('');
  }
  
  document.getElementById('recordsTotal').textContent = `(${state.filteredRecords.length})`;
  
  // Pagination
  const totalPages = Math.max(1, Math.ceil(state.filteredRecords.length / state.perPage));
  let pagHtml = `<button onclick="changeRecordsPage('prev')" ${state.recordsPage <= 1 ? 'disabled' : ''}>◀ Anterior</button>
    <span class="info">Página ${state.recordsPage} de ${totalPages} (${state.filteredRecords.length} registros)</span>
    <button onclick="changeRecordsPage('next')" ${state.recordsPage >= totalPages ? 'disabled' : ''}>Siguiente ▶</button>`;
  document.getElementById('recordsPagination').innerHTML = pagHtml;
}

function changeRecordsPage(dir) {
  const totalPages = Math.max(1, Math.ceil(state.filteredRecords.length / state.perPage));
  if (dir === 'prev' && state.recordsPage > 1) state.recordsPage--;
  if (dir === 'next' && state.recordsPage < totalPages) state.recordsPage++;
  renderRecords();
}

// ─── Stats ───
function renderStats() {
  const records = state.records;
  
  // KPIs
  document.getElementById('statsTotal').textContent = records.length;
  
  const keywords = new Set(records.map(r => r.keyword).filter(Boolean));
  document.getElementById('statsKeywords').textContent = keywords.size;
  
  const critical = records.filter(r => r.severity === 'critical').length;
  document.getElementById('statsCritical').textContent = critical;
  
  const sources = new Set(records.map(r => r.source_type).filter(Boolean));
  document.getElementById('statsSources').textContent = sources.size;
  
  // By type
  const byType = {};
  records.forEach(r => { byType[r.record_type] = (byType[r.record_type] || 0) + 1; });
  document.getElementById('statsByType').innerHTML = Object.entries(byType)
    .sort((a,b) => b[1] - a[1])
    .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl accent">${v}</span></div>`)
    .join('') || '<div class="empty-state" style="padding:10px"><p>Sin datos</p></div>';
  
  // By severity
  const bySev = {};
  records.forEach(r => { bySev[r.severity] = (bySev[r.severity] || 0) + 1; });
  const sevColors = { critical: 'red', high: 'accent', medium: 'accent', low: 'accent', info: 'accent' };
  document.getElementById('statsBySeverity').innerHTML = Object.entries(bySev)
    .sort((a,b) => b[1] - a[1])
    .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl ${sevColors[k] || 'accent'}">${v}</span></div>`)
    .join('') || '<div class="empty-state" style="padding:10px"><p>Sin datos</p></div>';
  
  // By domain
  const byDomain = {};
  records.forEach(r => { if (r.domain) byDomain[r.domain] = (byDomain[r.domain] || 0) + 1; });
  document.getElementById('statsByDomain').innerHTML = Object.entries(byDomain)
    .sort((a,b) => b[1] - a[1])
    .slice(0, 10)
    .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl">${v}</span></div>`)
    .join('') || '<div class="empty-state" style="padding:10px"><p>Sin datos</p></div>';
  
  // Dates
  const dates = {};
  records.forEach(r => {     const d = r.discovered_date?.substring(0, 7); // YYYY-MM
    if (d) dates[d] = (dates[d] || 0) + 1; 
  });
  document.getElementById('statsDates').innerHTML = Object.entries(dates)
    .sort((a,b) => a[0].localeCompare(b[0]))
    .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl accent">${v} registros</span></div>`)
    .join('') || '<div class="empty-state" style="padding:10px"><p>Sin datos</p></div>';
}

// ─── History ───
function renderHistory() {
  if (state.searchHistory.length === 0) {
    document.getElementById('historyList').innerHTML = '<div class="empty-state" style="padding:10px"><p>Aún no hay búsquedas registradas</p></div>';
    document.getElementById('historyStats').innerHTML = '<div class="empty-state" style="padding:10px"><p>Datos disponibles después de varias búsquedas</p></div>';
    return;
  }
  
  document.getElementById('historyList').innerHTML = state.searchHistory.map(h => {
    const time = new Date(h.timestamp).toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'});
    return `<div class="history-item">
      <span class="kw">🔍 ${escapeHtml(h.keyword)}</span>
      <span class="cnt">${h.total} registros</span>
      <span class="ts">${time}</span>
    </div>`;
  }).join('');
  
  // Stats
  const totalRecords = state.searchHistory.reduce((a, h) => a + h.total, 0);
  const avgRecords = Math.round(totalRecords / state.searchHistory.length);
  document.getElementById('historyStats').innerHTML = `
    <div class="stat-row"><span class="lb">Total búsquedas</span><span class="vl accent">${state.searchHistory.length}</span></div>
    <div class="stat-row"><span class="lb">Total registros</span><span class="vl">${totalRecords}</span></div>
    <div class="stat-row"><span class="lb">Promedio por búsqueda</span><span class="vl">${avgRecords}</span></div>
  `;
}

// ─── Dashboard KPIs ───
function updateDashboardKPIs() {
  const records = state.records;
  const keywords = new Set(records.map(r => r.keyword).filter(Boolean));
  const sources = new Set(records.map(r => r.source_type).filter(Boolean));
  const critical = records.filter(r => r.severity === 'critical').length;
  
  animateValue('kpiTotal', records.length);
  animateValue('kpiKeywords', keywords.size);
  animateValue('kpiCritical', critical);
  animateValue('kpiSources', sources.size);
  animateValue('kpiSearches', state.searchHistory.length);
  
  // Sidebar badges
  document.getElementById('sidebarRecordsCount').textContent = records.length;
  
  // Charts
  renderDashboardCharts(records);
}

function animateValue(id, val) {
  const el = document.getElementById(id);
  if (!el) return;
  const current = parseInt(el.textContent) || 0;
  if (current === val) return;
  
  let start = current;
  const step = Math.max(1, Math.ceil(Math.abs(val - current) / 30));
  const dir = val > current ? 1 : -1;
  
  function tick() {
    start += step * dir;
    if ((dir > 0 && start >= val) || (dir < 0 && start <= val)) {
      el.textContent = val;
      return;
    }
    el.textContent = start;
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function renderDashboardCharts(records) {
  if (records.length === 0) return;
  
  // By type bar chart
  const byType = {};
  records.forEach(r => { byType[r.record_type] = (byType[r.record_type] || 0) + 1; });
  const typeEntries = Object.entries(byType).sort((a,b) => b[1] - a[1]);
  const maxType = Math.max(...typeEntries.map(([,v]) => v), 1);
  
  const typeColors = {
    'email:pass': 'var(--red)', 'api_key': 'var(--orange)', 
    'ip:port': 'var(--blue)', 'hash': 'var(--purple)', 'config': 'var(--yellow)'
  };
  
  document.getElementById('chartByType').innerHTML = 
    '<div class="chart-bar">' + 
    typeEntries.map(([k, v]) => 
      `<div class="bar" style="height:${(v/maxType)*150}px;background:${typeColors[k] || 'var(--accent)'}">
        <div class="tooltip">${k}: ${v}</div>
        <div class="bar-label">${k}</div>
      </div>`
    ).join('') + '</div>';
  
  // By severity donut
  const bySev = {};
  records.forEach(r => { bySev[r.severity] = (bySev[r.severity] || 0) + 1; });
  const sevTotal = Object.values(bySev).reduce((a, b) => a + b, 0);
  
  const sevColors = {
    'critical': '#e17055', 'high': '#e67e22', 
    'medium': '#fdcb6e', 'low': '#0984e3', 'info': '#8888aa'
  };
  
  // Build conic gradient
  let gradParts = [];
  let currentDeg = 0;
  const sevOrder = ['critical', 'high', 'medium', 'low', 'info'];
  sevOrder.forEach(sev => {
    if (bySev[sev]) {
      const pct = (bySev[sev] / sevTotal) * 100;
      const deg = (bySev[sev] / sevTotal) * 360;
      gradParts.push(`${sevColors[sev]} ${currentDeg}deg ${currentDeg + deg}deg`);
      currentDeg += deg;
    }
  });
  
  const donutHtml = `
    <div class="donut-container">
      <div class="donut" style="background:conic-gradient(${gradParts.join(', ')})">
        <div class="donut-center">
          <div class="big">${sevTotal}</div>
          <div class="small">total</div>
        </div>
      </div>
      <div class="donut-legend">
        ${sevOrder.filter(s => bySev[s]).map(s => 
          `<div class="donut-legend-item">
            <span class="dot" style="background:${sevColors[s]}"></span>
            <span>${s}</span>
            <span class="pct">${bySev[s]} (${Math.round(bySev[s]/sevTotal*100)}%)</span>
          </div>`
        ).join('')}
      </div>
    </div>`;
  document.getElementById('chartBySeverity').innerHTML = donutHtml;
}

// ─── Chat ───
let chatOpen = false;

function toggleChat() {
  chatOpen = !chatOpen;
  document.getElementById('chatPanel').classList.toggle('open', chatOpen);
  document.getElementById('chatNotif').style.display = 'none';
  if (chatOpen) setTimeout(() => document.getElementById('chatInput').focus(), 200);
}

function chatAddMsg(text, cls, time) {
  const msgs = document.getElementById('chatMsgs');
  const t = time || new Date().toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'});
  msgs.innerHTML += `<div class="msg ${cls}">${text}<span class="time">${t}</span></div>`;
  msgs.scrollTop = msgs.scrollHeight;
}

function chatShowTyping() {
  const msgs = document.getElementById('chatMsgs');
  msgs.innerHTML += '<div class="typing" id="chatTyping"><span></span><span></span><span></span></div>';
  msgs.scrollTop = msgs.scrollHeight;
}

function chatHideTyping() {
  const el = document.getElementById('chatTyping');
  if (el) el.remove();
}

function chatSendFromInput() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  chatSend(text);
}

function chatSend(text) {
  if (!text || !text.trim()) return;
  chatAddMsg(escapeHtml(text), 'user');
  chatShowTyping();
  
  setTimeout(() => {
    chatHideTyping();
    const response = chatGenerateResponse(text);
    chatAddMsg(response, 'bot');
  }, 400 + Math.random() * 400);
}

function chatGenerateResponse(msg) {
  const ml = msg.toLowerCase().trim();
  
  // Buscar comando
  if (ml.startsWith('buscar ')) {
    const kw = ml.replace('buscar ', '').trim();
    if (kw) {
      document.getElementById('searchInput').value = kw;
      setTimeout(() => { 
        navigateTo('search'); 
        executeSearch(); 
      }, 500);
      return `🔍 Iniciando búsqueda para **"${escapeHtml(kw)}"**... Los resultados se mostrarán en el panel de búsqueda.`;
    }
  }
  
  // Estadísticas
  if (ml.includes('cuantos') || ml.includes('estadísticas') || ml.includes('cuántos')) {
    const total = state.records.length;
    const keywords = new Set(state.records.map(r => r.keyword).filter(Boolean)).size;
    const critical = state.records.filter(r => r.severity === 'critical').length;
    return `📊 **Estadísticas del Oráculo:**\n\n• Registros totales: **${total}**\n• Palabras clave: **${keywords}**\n• Registros críticos: **${critical}**\n• Búsquedas realizadas: **${state.searchHistory.length}**`;
  }
  
  // Resumen
  if (ml.includes('resumen') || ml.includes('general') || ml.includes('panorama')) {
    return `📋 **Resumen del Oráculo**\n\n🔄 Búsquedas: ${state.searchHistory.length}\n📊 Registros: ${state.records.length}\n🔴 Críticos: ${state.records.filter(r => r.severity === 'critical').length}\n\n_Usa el panel de búsqueda para obtener más datos._`;
  }
  
  // Última búsqueda
  if (ml.includes('última') || ml.includes('ultima') || ml.includes('último') || ml.includes('ultimo')) {
    if (state.lastKeyword) {
      return `🔍 Última búsqueda: **"${escapeHtml(state.lastKeyword)}"** — ${state.records.length} registros encontrados.`;
    }
    return '⚠️ Aún no has realizado ninguna búsqueda.';
  }
  
  // Comandos / Ayuda
  if (ml.includes('ayuda') || ml.includes('comandos') || ml.includes('qué puedes') || ml.includes('que puedes')) {
    return (
      '🤖 **Comandos disponibles:**\n\n' +
      '🔍 `buscar <keyword>` — Inicia búsqueda de inteligencia\n' +
      '📊 `¿Cuántos registros?` — Estadísticas del sistema\n' +
      '📋 `resumen` — Panorama general\n' +
      '🔍 `última búsqueda` — Info de la última búsqueda\n' +
      '❓ `ayuda` — Esta ayuda\n\n' +
      '_También puedes usar los chips rápidos abajo._'
    );
  }
  
  // Default
  return '🤔 No entendí tu mensaje. Prueba con:\n\n• `buscar comcast` — Buscar inteligencia\n• `¿Cuántos registros?` — Estadísticas\n• `resumen` — Panorama general\n• `ayuda` — Comandos disponibles';
}

// ─── Deploy Status ───
let deployRefreshInterval = null;

async function fetchDeployStatus() {
  try {
    const resp = await fetch('/api/deploy/status', {
      signal: AbortSignal.timeout(5000),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = await resp.json();
    if (!json.success) throw new Error(json.error || 'API error');
    renderDeployStatus(json.data);
    return json.data;
  } catch (err) {
    console.error('Deploy status error:', err);
    document.getElementById('deployRailwayInfo').innerHTML = 
      `<div class="empty-state" style="padding:5px"><p>⚠️ No se puede conectar con el servidor: ${escapeHtml(err.message)}</p></div>`;
    document.getElementById('sidebarDeployStatus').textContent = 'Offline';
    document.getElementById('sidebarDeployStatus').className = 'badge badge-red';
    return null;
  }
}

function renderDeployStatus(d) {
  if (!d) return;
  
  // ── KPI Cards ──
  const health = d.health || {};
  document.getElementById('deployUptime').textContent = health.uptime_str || '—';
  
  const workers = health.workers || {};
  const workerCount = workers.worker_count || '—';
  document.getElementById('deployWorkers').textContent = workerCount;
  
  const env = d.env_vars || {};
  const configuredCount = Object.values(env).filter(v => v === true).length;
  animateValue('deployApisConfigured', configuredCount);
  
  document.getElementById('deployCpu').textContent = health.cpu_percent != null ? `${health.cpu_percent}%` : '—';
  
  const mem = health.memory || {};
  document.getElementById('deployMemory').textContent = mem.rss_mb != null && mem.rss_mb !== 'N/A' ? `${mem.rss_mb} MB` : '—';

  // ── Sidebar badge ──
  const badge = document.getElementById('sidebarDeployStatus');
  const deployInfo2 = d.deploy || {};
  let platform = deployInfo2.detected_platform || 'local';
  
  if (platform === 'render') {
    badge.textContent = 'Render';
    badge.className = 'badge badge-green';
  } else if (platform === 'railway') {
    badge.textContent = 'Railway';
    badge.className = 'badge badge-green';
  } else if (platform === 'fly') {
    badge.textContent = 'Fly.io';
    badge.className = 'badge badge-green';
  } else {
    badge.textContent = 'Local';
    badge.className = 'badge';
  }
  
  // ── Connection Info (Render / Railway / Local) ──
  const deployInfo = d.deploy || {};
  platform = deployInfo.detected_platform || 'local';  // re-assign OK (let)
  
  let connHtml = '';
  
  if (platform === 'render') {
    const r = deployInfo.render || {};
    connHtml = `
      <div class="stat-row"><span class="lb">🌐 URL Pública</span><span class="vl green">${escapeHtml(r.public_url)}</span></div>
      <div class="stat-row"><span class="lb">🏷️ Servicio</span><span class="vl">${escapeHtml(r.service_name)}</span></div>
      <div class="stat-row"><span class="lb">🌍 Región</span><span class="vl">${escapeHtml(r.region)}</span></div>
      <div class="stat-row"><span class="lb">🌿 Rama</span><span class="vl">${escapeHtml(r.git_branch)}</span></div>
      <div class="stat-row"><span class="lb">📦 Commit</span><span class="vl" style="font-size:8px;font-family:var(--mono)">${escapeHtml(r.git_commit_sha?.substring(0, 12) || '—')}</span></div>
      <div class="stat-row"><span class="lb">🆔 Deploy ID</span><span class="vl" style="font-size:8px;font-family:var(--mono)">${escapeHtml(r.deploy_id?.substring(0, 20) || '—')}</span></div>
      <div class="stat-row"><span class="lb">⏱️ Iniciado</span><span class="vl">${escapeHtml(formatISODate(d.started_at))}</span></div>
      <div class="stat-row"><span class="lb">🔌 Servidor</span><span class="vl green">✅ Render — siempre activo (con pings)</span></div>
    `;
  } else if (platform === 'railway') {
    const rw = deployInfo.railway || {};
    connHtml = `
      <div class="stat-row"><span class="lb">🌐 URL Pública</span><span class="vl green">${escapeHtml(rw.public_url)}</span></div>
      <div class="stat-row"><span class="lb">🏷️ Servicio</span><span class="vl">${escapeHtml(rw.service_name)}</span></div>
      <div class="stat-row"><span class="lb">🌍 Región</span><span class="vl">${escapeHtml(rw.region)}</span></div>
      <div class="stat-row"><span class="lb">🌿 Rama</span><span class="vl">${escapeHtml(rw.git_branch)}</span></div>
      <div class="stat-row"><span class="lb">📦 Commit</span><span class="vl" style="font-size:8px;font-family:var(--mono)">${escapeHtml(rw.git_commit_sha?.substring(0, 12) || '—')}</span></div>
      <div class="stat-row"><span class="lb">⏱️ Iniciado</span><span class="vl">${escapeHtml(formatISODate(d.started_at))}</span></div>
      <div class="stat-row"><span class="lb">🔌 Servidor</span><span class="vl green">✅ Conectado y respondiendo</span></div>
    `;
  } else if (platform === 'fly') {
    const f = deployInfo.fly || {};
    connHtml = `
      <div class="stat-row"><span class="lb">🌐 App</span><span class="vl green">${escapeHtml(f.app_name)}</span></div>
      <div class="stat-row"><span class="lb">🌍 Región</span><span class="vl">${escapeHtml(f.region)}</span></div>
      <div class="stat-row"><span class="lb">🔌 Servidor</span><span class="vl green">✅ Fly.io — siempre activo</span></div>
    `;
  } else {
    connHtml = `
      <div class="stat-row"><span class="lb">🌐 Entorno</span><span class="vl warn" style="color:var(--yellow)">Desarrollo Local</span></div>
      <div class="stat-row"><span class="lb">💻 Host</span><span class="vl">${escapeHtml(d.platform?.hostname || '—')}</span></div>
      <div class="stat-row"><span class="lb">🔌 Servidor</span><span class="vl green">✅ Funcionando correctamente</span></div>
      <div class="stat-row"><span class="lb">💡 Sugerencia</span><span class="vl" style="color:var(--text3);font-size:9px">Despliega en Render.app para acceso 24/7</span></div>
    `;
  }
  // Add server time and started at
  document.getElementById('deployRailwayInfo').innerHTML = connHtml;
  
  // ── Healthcheck ──
  let hcHtml = '';
  const latency = d.healthcheck_latency_ms || {};
  const overallOk = health.api_server?.status === 'passing' && health.engine_initialized;
  
  hcHtml = `
    <div class="stat-row">
      <span class="lb">🩺 Healthcheck</span>
      <span class="vl ${overallOk ? 'green' : 'red'}">${overallOk ? '✅ Pasando' : '❌ Fallando'}</span>
    </div>
    <div class="stat-row">
      <span class="lb">⏱️ Stats endpoint</span>
      <span class="vl accent">${latency.stats_endpoint_ms || '—'} ms</span>
    </div>
    <div class="stat-row">
      <span class="lb">🔍 Query index</span>
      <span class="vl accent">${latency.query_index_ms || '—'} ms</span>
    </div>
    <div class="stat-row">
      <span class="lb">🧠 Motor Inicializado</span>
      <span class="vl ${health.engine_initialized ? 'green' : 'red'}">${health.engine_initialized ? '✅ Sí' : '❌ No'}</span>
    </div>
    <div class="stat-row">
      <span class="lb">🗄️ Modo Índice</span>
      <span class="vl accent">${health.index_mode === 'elasticsearch' ? '🔍 Elasticsearch' : '💾 En Memoria'}</span>
    </div>
    <div class="stat-row">
      <span class="lb">🕐 Uptime</span>
      <span class="vl">${health.uptime_str || '—'}</span>
    </div>
  `;
  document.getElementById('deployHealthcheck').innerHTML = hcHtml;
  
  // ── Environment Variables ──
  let envHtml = '';
  const envConfig = {
    shodan: { label: 'Shodan', icon: '🔍' },
    hunter: { label: 'Hunter.io', icon: '📧' },
    hibp: { label: 'HaveIBeenPwned', icon: '🔒' },
    virustotal: { label: 'VirusTotal', icon: '🦠' },
    censys_token: { label: 'Censys', icon: '🌐' },
    es_hosts: { label: 'Elasticsearch', icon: '🗄️' },
    tor_proxy: { label: 'Proxy Tor', icon: '🧅' },
  };
  
  Object.entries(envConfig).forEach(([key, cfg]) => {
    const val = env[key];
    const configured = val === true || (key === 'tor_proxy' && val === 'true');
    envHtml += `
      <div class="stat-row">
        <span class="lb">${cfg.icon} ${cfg.label}</span>
        <span class="vl ${configured ? 'green' : 'red'}">${configured ? '✅ Configurada' : '❌ No configurada'}</span>
      </div>
    `;
  });
  document.getElementById('deployEnvVars').innerHTML = envHtml;
  
  // ── Workers & Performance ──
  const perf = health.memory || {};
  let perfHtml = `
    <div class="stat-row">
      <span class="lb">⚙️ Gunicorn Workers</span>
      <span class="vl accent">${workers.worker_count}</span>
    </div>
    <div class="stat-row">
      <span class="lb">🧵 Worker Class</span>
      <span class="vl">${workers.worker_class}</span>
    </div>
    <div class="stat-row">
      <span class="lb">🖥️ CPUs Disponibles</span>
      <span class="vl">${d.platform?.cpus || '—'}</span>
    </div>
    <div class="stat-row">
      <span class="lb">💾 RSS Memory</span>
      <span class="vl">${perf.rss_mb != null && perf.rss_mb !== 'N/A' ? perf.rss_mb + ' MB' : '—'}</span>
    </div>
    <div class="stat-row">
      <span class="lb">🧠 VMS Memory</span>
      <span class="vl">${perf.vms_mb != null && perf.vms_mb !== 'N/A' ? perf.vms_mb + ' MB' : '—'}</span>
    </div>
    <div class="stat-row">
      <span class="lb">📊 CPU Usage</span>
      <span class="vl">${health.cpu_percent != null ? health.cpu_percent + '%' : '—'}</span>
    </div>
  `;
  if (perf.system_total_mb) {
    const sysPct = perf.system_percent || 0;
    perfHtml += `
      <div class="stat-row">
        <span class="lb">🖥️ RAM Sistema</span>
        <span class="vl">${perf.system_used_mb || perf.system_total_mb - (perf.system_available_mb || 0)} / ${perf.system_total_mb} MB (${sysPct}%)</span>
      </div>
    `;
  }
  document.getElementById('deployWorkersInfo').innerHTML = perfHtml;
  
  // ── Platform ──
  const plat = d.platform || {};
  document.getElementById('deployPlatform').innerHTML = `
    <div class="stat-row"><span class="lb">🐍 Python</span><span class="vl accent">${escapeHtml(plat.python_version)}</span></div>
    <div class="stat-row"><span class="lb">💻 Sistema</span><span class="vl">${escapeHtml(plat.system)} ${escapeHtml(plat.release)}</span></div>
    <div class="stat-row"><span class="lb">🏗️ Arquitectura</span><span class="vl">${escapeHtml(plat.machine)}</span></div>
    <div class="stat-row"><span class="lb">🆔 Hostname</span><span class="vl" style="font-size:8px;font-family:var(--mono)">${escapeHtml(plat.hostname)}</span></div>
    <div class="stat-row"><span class="lb">🕒 Servidor</span><span class="vl">${escapeHtml(formatISODate(d.server_time))}</span></div>
  `;
  
  // ── Quick Actions ──
  const actionsContainer = document.getElementById('deployActions');
  
  // Build platform-specific dashboard/logs URLs
  let dashboardUrl = 'https://dashboard.render.com';
  let dashboardLabel = '📊 Dashboard Render';
  let logsUrl = 'https://dashboard.render.com';
  let logsLabel = '📋 Logs en Vivo';
  
  if (platform === 'render') {
    const rInfo = deployInfo.render || {};
    const serviceSlug = rInfo.service_name || 'oraculo-inteligencia';
    dashboardUrl = `https://dashboard.render.com/web/${rInfo.service_id || ''}`;
    logsUrl = dashboardUrl;
    dashboardLabel = '📊 Dashboard Render';
    logsLabel = '📋 Logs de Render';
  } else if (platform === 'railway') {
    const rwInfo = deployInfo.railway || {};
    const projectId = rwInfo.project_id || '';
    const serviceId = rwInfo.service_id || '';
    dashboardUrl = `https://railway.app/project/${projectId}/service/${serviceId}`;
    logsUrl = dashboardUrl;
    dashboardLabel = '📊 Dashboard Railway';
    logsLabel = '📋 Logs Railway';
  }
  
  actionsContainer.innerHTML = `
    <a href="${dashboardUrl}" target="_blank" class="action-btn" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:9px 16px;border-radius:8px;font-size:11px;cursor:pointer;transition:all 0.2s;text-decoration:none;display:inline-flex;align-items:center;gap:6px;" 
       onmouseover="this.style.borderColor='var(--accent)';this.style.background='var(--bg4)'" 
       onmouseout="this.style.borderColor='var(--border)';this.style.background='var(--bg3)'">
      ${dashboardLabel}
    </a>
    <a href="${logsUrl}" target="_blank" class="action-btn" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:9px 16px;border-radius:8px;font-size:11px;cursor:pointer;transition:all 0.2s;text-decoration:none;display:inline-flex;align-items:center;gap:6px;"
       onmouseover="this.style.borderColor='var(--accent2)';this.style.background='var(--bg4)'" 
       onmouseout="this.style.borderColor='var(--border)';this.style.background='var(--bg3)'">
      ${logsLabel}
    </a>
    <button onclick="refreshDeployStatus()" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:9px 16px;border-radius:8px;font-size:11px;cursor:pointer;transition:all 0.2s;display:inline-flex;align-items:center;gap:6px;"
            onmouseover="this.style.borderColor='var(--accent)';this.style.background='var(--bg4)'" 
            onmouseout="this.style.borderColor='var(--border)';this.style.background='var(--bg3)'">
      🔄 Refrescar Estado
    </button>
    <button onclick="testHealthcheck()" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:9px 16px;border-radius:8px;font-size:11px;cursor:pointer;transition:all 0.2s;display:inline-flex;align-items:center;gap:6px;"
            onmouseover="this.style.borderColor='var(--green)';this.style.background='var(--bg4)'" 
            onmouseout="this.style.borderColor='var(--border)';this.style.background='var(--bg3)'">
      🩺 Probar Healthcheck
    </button>
  `;
}

async function refreshDeployStatus() {
  showToast('🔄 Refrescando estado del despliegue...', 'var(--accent2)');
  await fetchDeployStatus();
  showToast('✅ Estado actualizado', 'var(--green)');
}

async function testHealthcheck() {
  try {
    const start = performance.now();
    const resp = await fetch('/api/stats', { signal: AbortSignal.timeout(5000) });
    const latency = Math.round(performance.now() - start);
    
    if (resp.ok) {
      showToast(`🩺 Healthcheck OK · ${latency}ms respuesta`, 'var(--green)');
    } else {
      showToast(`⚠️ Healthcheck respondió HTTP ${resp.status}`, 'var(--yellow)');
    }
  } catch (err) {
    showToast(`❌ Healthcheck falló: ${escapeHtml(err.message)}`, 'var(--red)');
  }
}

function formatISODate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('es-ES', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  } catch (e) {
    return iso;
  }
}


// ─── Combo Intelligence ───
let comboData = [];

async function executeComboLeech() {
  const keyword = document.getElementById('comboKeyword').value.trim();
  if (!keyword) { showToast('❌ Ingresa una palabra clave', 'var(--red)'); return; }
  
  const sources = [];
  if (document.getElementById('comboSourcePaste').checked) sources.push('paste');
  if (document.getElementById('comboSourceTelegram').checked) sources.push('telegram');
  if (document.getElementById('comboSourceDiscord').checked) sources.push('discord');
  if (document.getElementById('comboSourceForum').checked) sources.push('forum');
  if (document.getElementById('comboSourceDorking').checked) sources.push('dorking');
  const validate = document.getElementById('comboValidate').checked;
  
  const btn = document.getElementById('comboBtn');
  const spinner = document.getElementById('comboSpinner');
  const scanBar = document.getElementById('comboScanBar');
  btn.disabled = true;
  spinner.style.display = 'inline-block';
  scanBar.classList.add('active');
  document.getElementById('comboResults').classList.remove('active');
  
  try {
    const resp = await fetch('/api/combo/leech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword, sources, validate, max_per_source: 20 }),
      signal: AbortSignal.timeout(30000),
    });
    
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = await resp.json();
    if (!json.success) throw new Error(json.error || 'API error');
    
    renderComboResults(json.data, keyword);
    showToast(`✅ ${json.data.total} combos encontrados para "${keyword}"`, 'var(--green)');
  } catch (err) {
    console.error('Combo leech error:', err);
    showToast('❌ Error: ' + err.message, 'var(--red)');
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    scanBar.classList.remove('active');
  }
}

function renderComboResults(data, keyword) {
  comboData = data.combos || [];
  
  document.getElementById('comboResultsKeyword').innerHTML = `🔐 <strong>"${escapeHtml(keyword)}"</strong>`;
  document.getElementById('comboResultsCount').textContent = `${data.total} combos`;
  document.getElementById('comboResultsTime').textContent = `· ${data.took_seconds || '—'}s`;
  
  animateValue('comboValidCount', data.valid_count || 0);
  animateValue('comboInvalidCount', data.invalid_count || 0);
  animateValue('comboUnknownCount', (data.total || 0) - (data.valid_count || 0) - (data.invalid_count || 0));
  document.getElementById('comboSourcesCount').textContent = (data.sources || []).join(', ') || '—';
  document.getElementById('comboTimeCount').textContent = (data.took_seconds || '—') + 's';
  
  const tbody = document.getElementById('comboBody');
  if (comboData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">🔍 No se encontraron combos</td></tr>';
  } else {
    tbody.innerHTML = comboData.map(c => {
      const q = c.quality || 'unknown';
      const statusIcon = q === 'valid' ? '✅' : (q === 'invalid' ? '❌' : '❓');
      const pwHidden = c.password ? c.password.substring(0, 10) + '***' : '—';
      return `<tr>
        <td>${statusIcon}</td>
        <td class="email-cell">${escapeHtml(c.email || c.username || '—')}</td>
        <td style="font-family:var(--mono);font-size:9px;color:var(--text2)">${escapeHtml(pwHidden)}</td>
        <td class="domain">${escapeHtml(c.domain || '—')}</td>
        <td class="source-cell">${escapeHtml(c.source_type || '—')}</td>
        <td>${q}</td>
      </tr>`;
    }).join('');
  }
  
  document.getElementById('comboResults').classList.add('active');
  document.getElementById('sidebarComboCount').textContent = data.total || 0;
  
  // Stats
  const bySource = data.stats?.by_source || {};
  document.getElementById('comboBySource').innerHTML = Object.entries(bySource)
    .sort((a,b) => b[1] - a[1])
    .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl accent">${v}</span></div>`)
    .join('') || '<div class="empty-state" style="padding:5px"><p>Sin datos</p></div>';
  
  const byDomain = data.stats?.by_domain || {};
  document.getElementById('comboByDomain').innerHTML = Object.entries(byDomain)
    .sort((a,b) => b[1] - a[1])
    .slice(0, 10)
    .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl">${v}</span></div>`)
    .join('') || '<div class="empty-state" style="padding:5px"><p>Sin datos</p></div>';
}

async function refreshComboStats() {
  try {
    const resp = await fetch('/api/combo/stats', { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) return;
    const json = await resp.json();
    if (!json.success) return;
    const s = json.data;
    document.getElementById('comboEngineStats').innerHTML = `
      <div class="stat-row"><span class="lb">📦 Combinaciones indexadas</span><span class="vl accent">${s.total_combos_indexed || 0}</span></div>
      <div class="stat-row"><span class="lb">🔐 Validadas</span><span class="vl">${s.total_validated || 0}</span></div>
      <div class="stat-row"><span class="lb">📡 Fuentes usadas</span><span class="vl">${(s.sources_used || []).join(', ') || 'ninguna'}</span></div>
      <div class="stat-row"><span class="lb">🔄 Último leech</span><span class="vl green">${s.last_leech ? escapeHtml(s.last_leech.keyword) + ' — ' + s.last_leech.total + ' combos' : '—'}</span></div>
      <div class="stat-row"><span class="lb">🧵 Proxies vivos</span><span class="vl">${s.proxies_alive || 0}/${s.proxies_available || 0}</span></div>
      ${s.oracle_stats ? `<div class="stat-row"><span class="lb">🗄️ Total en Oracle</span><span class="vl accent">${s.oracle_stats.total_records || 0}</span></div>` : ''}
    `;
    document.getElementById('comboTotalLabel').textContent = `(${s.total_combos_indexed || 0} combos indexados)`;
    document.getElementById('sidebarComboCount').textContent = s.total_combos_indexed || 0;
  } catch (e) {
    document.getElementById('comboEngineStats').innerHTML = `<div class="empty-state" style="padding:5px"><p>⚠️ Motor no disponible</p></div>`;
  }
}

async function exportCombo(fmt) {
  const keyword = document.getElementById('comboKeyword').value.trim();
  try {
    const url = `/api/combo/export/${fmt}${keyword ? '?keyword=' + encodeURIComponent(keyword) : ''}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `combos_${keyword || 'all'}.${fmt}`;
    link.click();
    showToast(`📥 Exportados a ${fmt.toUpperCase()}`, 'var(--accent2)');    } catch (e) {
    showToast('❌ Error de exportación: ' + (e.message || e), 'var(--red)');
  }
}


// ─── Proxy Intelligence ───
let proxyInited = false;

async function refreshProxyStats() {
  try {
    const resp = await fetch('/api/proxy/stats', { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) return;
    const json = await resp.json();
    if (!json.success) return;
    renderProxyStats(json.data);
  } catch (e) {
    document.getElementById('proxyPoolStats').innerHTML = `<div class="empty-state" style="padding:5px"><p>⚠️ ProxyEngine no disponible</p></div>`;
  }
}

function renderProxyStats(data) {
  if (!data || !data.pool) return;
  const pool = data.pool;
  
  animateValue('proxyTotal', pool.total || 0);
  animateValue('proxyAlive', pool.alive || 0);
  animateValue('proxyDead', pool.dead || 0);
  animateValue('proxyUntested', pool.untested || 0);
  document.getElementById('proxyMode').textContent = data.mode || 'auto';
  document.getElementById('sidebarProxyCount').textContent = pool.alive || 0;
  document.getElementById('proxyModeSelect').value = data.mode || 'auto';
  
  // Pool stats
  let pHtml = `
    <div class="stat-row"><span class="lb">🧪 Vivos</span><span class="vl green">${pool.alive || 0}</span></div>
    <div class="stat-row"><span class="lb">💀 Muertos</span><span class="vl red">${pool.dead || 0}</span></div>
    <div class="stat-row"><span class="lb">❓ Sin testear</span><span class="vl warn" style="color:var(--yellow)">${pool.untested || 0}</span></div>
    <div class="stat-row"><span class="lb">📦 Total en pool</span><span class="vl accent">${pool.total || 0}</span></div>
    <div class="stat-row"><span class="lb">🌐 Proxyless</span><span class="vl ${pool.proxyless_available ? 'green' : 'red'}">${pool.proxyless_available ? '✅ Disponible' : '❌ No'}</span></div>
  
    <div class="stat-row"><span class="lb">📡 Fuentes scraping</span><span class="vl accent">${data.scrape_sources || 31} disponibles</span></div>
  `;
  if (pool.by_source && Object.keys(pool.by_source).length > 0) {
    pHtml += '<div class="stat-row" style="border-top:1px solid var(--border);margin-top:4px;padding-top:6px"><span class="lb"><strong>Por fuente:</strong></span><span class="vl"></span></div>';
    Object.entries(pool.by_source).slice(0, 10).forEach(([k, v]) => {
      pHtml += `<div class="stat-row" style="font-size:8px;padding:2px 0"><span class="lb">  ${k}</span><span class="vl accent">${v}</span></div>`;
    });
  }
  document.getElementById('proxyPoolStats').innerHTML = pHtml;
}

async function executeProxyScrape() {
  const btn = document.getElementById('proxyScrapeBtn');
  const spinner = document.getElementById('proxyScrapeSpinner');
  btn.disabled = true;
  spinner.style.display = 'inline-block';
  
  try {
    const resp = await fetch('/api/proxy/scrape', {
      method: 'POST',
      signal: AbortSignal.timeout(60000),
    });
    const json = await resp.json();
    if (json.success) {
      const bySource = json.data.by_source || {};
      const sourceKeys = Object.keys(bySource);
      showToast(`🕸️ ${json.data.total} proxies scrapeados de ${sourceKeys.length} fuentes`, 'var(--green)');
      refreshProxyStats();

      const totalAvail = json.data.sources_total || 31;
      let srcHtml = `<div class="stat-row" style="color:var(--text3);font-size:9px;border:none;padding:2px 0">
        <span class="lb">📡 <strong>${sourceKeys.length}</strong> activas de <strong>${totalAvail}</strong> disponibles</span>
      </div>`;
      if (sourceKeys.length > 0) {
        srcHtml += Object.entries(bySource).sort((a,b) => b[1] - a[1])
          .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl accent">${v}</span></div>`)
          .join('');
      } else {
        srcHtml += '<div class="empty-state" style="padding:5px"><p>Sin fuentes</p></div>';
      }
      document.getElementById('proxySources').innerHTML = srcHtml;
    } else {
      showToast('❌ Error: ' + (json.error || 'desconocido'), 'var(--red)');
    }
  } catch (e) {
    showToast('❌ Error de scrape: ' + e.message, 'var(--red)');
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
  }
}

async function executeProxyTest() {
  try {
    showToast('🧪 Testeando proxies... esto puede tomar tiempo', 'var(--yellow)');
    const resp = await fetch('/api/proxy/test', {
      method: 'POST',
      signal: AbortSignal.timeout(120000),
    });
    const json = await resp.json();
    if (json.success) {
      const s = json.data;
      showToast(`✅ Test completo: ${s.alive} vivos, ${s.dead} muertos, ${s.untested} sin testear`, 'var(--green)');
      refreshProxyStats();
    }
  } catch (e) {
    showToast('❌ Error: ' + e.message, 'var(--red)');
  }
}

async function changeProxyMode() {
  const mode = document.getElementById('proxyModeSelect').value;
  try {
    const resp = await fetch('/api/proxy/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    const json = await resp.json();
    if (json.success) {
      document.getElementById('proxyMode').textContent = mode;
      showToast(`🔄 Modo cambiado a: ${mode}`, 'var(--accent2)');
    }
  } catch (e) {
    showToast('❌ Error: ' + e.message, 'var(--red)');
  }
}

async function addManualProxies() {
  const text = document.getElementById('proxyManualInput').value.trim();
  if (!text) { showToast('❌ Ingresa proxies primero', 'var(--red)'); return; }
  try {
    const resp = await fetch('/api/proxy/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proxies: text }),
    });
    const json = await resp.json();
    if (json.success) {
      showToast(`✅ ${json.data.added} proxies agregados (total: ${json.data.total})`, 'var(--green)');
      document.getElementById('proxyManualInput').value = '';
      refreshProxyStats();
    }
  } catch (e) {
    showToast('❌ Error: ' + e.message, 'var(--red)');
  }
}

async function clearProxies() {
  try {
    const resp = await fetch('/api/proxy/clear', { method: 'POST' });
    await resp.json();
    showToast('🗑️ Pool de proxies limpiado', 'var(--yellow)');
    refreshProxyStats();
  } catch (e) {
    showToast('❌ Error: ' + e.message, 'var(--red)');
  }
}

async function detectVpn() {
  try {
    const resp = await fetch('/api/proxy/vpn', { signal: AbortSignal.timeout(10000) });
    const json = await resp.json();
    if (json.success) {
      const v = json.data;
      document.getElementById('proxyVpnInfo').innerHTML = `
        <div class="stat-row"><span class="lb">🌐 IP</span><span class="vl" style="font-family:var(--mono)">${v.ip || '—'}</span></div>
        <div class="stat-row"><span class="lb">🌍 País</span><span class="vl">${v.country || '—'}</span></div>
        <div class="stat-row"><span class="lb">🏢 ISP</span><span class="vl">${v.isp || '—'}</span></div>
        <div class="stat-row"><span class="lb">🔒 VPN</span><span class="vl ${v.vpn ? 'red' : 'green'}">${v.vpn ? '❌ Detectada' : '✅ No detectada'}</span></div>
        <div class="stat-row"><span class="lb">🖥️ Hosting</span><span class="vl">${v.hosting ? '✅ Sí' : '❌ No'}</span></div>
      `;
    }
  } catch (e) {
    document.getElementById('proxyVpnInfo').innerHTML = `<div class="stat-row"><span class="lb">❌ Error</span><span class="vl red">${escapeHtml(e.message)}</span></div>`;
  }
}

// ─── Auto-Poblar Pool (scrape + test en cadena) ───

let autoPopulateRunning = false;

async function executeAutoPopulate() {
  if (autoPopulateRunning) return;
  autoPopulateRunning = true;

  const btn = document.getElementById('autoPopulateBtn');
  const spinner = document.getElementById('autoPopulateSpinner');
  const label = document.getElementById('autoPopulateLabel');

  btn.disabled = true;
  spinner.style.display = 'inline-block';
  label.textContent = '\u{1F578}\u{FE0F} Scrapeando...';

  try {
    const resp = await fetch('/api/proxy/autopopulate', {
      method: 'POST',
      signal: AbortSignal.timeout(180000),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status + ' - Server error');
    const json = await resp.json();

    if (json.success) {
      const d = json.data;
      const scraped = d.scrape?.total_scraped || 0;
      const alive = d.test?.alive || 0;
      const dead = d.test?.dead || 0;
      const sources = d.scrape?.sources_count || 0;
      const took = d.took_seconds || 0;

      label.textContent = `\u2705 ${scraped} scrapeados \u00b7 ${alive} vivos \u00b7 ${took}s`;
      showToast(`\u26A1 Pool auto-poblado: ${scraped} proxies de ${sources} fuentes, ${alive} vivos, ${dead} muertos (${took}s)`, 'var(--green)');

      setTimeout(refreshProxyStats, 500);
    } else {
      label.textContent = '\u274C Error';
      showToast('\u274C Error: ' + (json.error || 'desconocido'), 'var(--red)');
    }
  } catch (e) {
    label.textContent = '\u274C Error';
    showToast('\u274C Error de auto-poblado: ' + e.message, 'var(--red)');
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    autoPopulateRunning = false;
    setTimeout(() => {
      if (!autoPopulateRunning) label.textContent = '\u26A1 Auto-poblar Pool';
    }, 5000);
  }
}

// ─── Dump Finder ───
let dumpData = [];

async function executeDumpSearch() {
  const keyword = document.getElementById('dumpKeyword').value.trim();
  if (!keyword) { showToast('❌ Ingresa una palabra clave', 'var(--red)'); return; }
  
  const year = document.getElementById('dumpYear').value;
  const month = document.getElementById('dumpMonth').value;
  const saveToDisk = document.getElementById('dumpSaveDisk').checked;
  
  const btn = document.getElementById('dumpBtn');
  const spinner = document.getElementById('dumpSpinner');
  const scanBar = document.getElementById('dumpScanBar');
  btn.disabled = true;
  spinner.style.display = 'inline-block';
  scanBar.classList.add('active');
  document.getElementById('dumpResults').classList.remove('active');
  
  try {
    const body = {
      keyword,
      year: year ? parseInt(year) : null,
      month: month ? parseInt(month) : null,
      max_dorks: 15,
      max_fetches: 10,
      save_to_disk: saveToDisk,
    };
    
    const resp = await fetch('/api/dump/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120000),
    });
    
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = await resp.json();
    if (!json.success) throw new Error(json.error || 'API error');
    
    renderDumpResults(json.data, keyword);
    const total = json.data.filtered_combos_count || 0;
    showToast(`✅ ${total} combos encontrados para "${keyword}"`, 'var(--green)');
  } catch (err) {
    console.error('Dump search error:', err);
    showToast('❌ Error: ' + err.message, 'var(--red)');
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    scanBar.classList.remove('active');
  }
}

function renderDumpResults(data, keyword) {
  dumpData = data.combos_sample || [];
  
  // Header
  document.getElementById('dumpResultsKeyword').innerHTML = `🗄️ <strong>"${escapeHtml(keyword)}"</strong>`;
  document.getElementById('dumpResultsCount').textContent = `${data.filtered_combos_count || 0} combos filtrados`;
  document.getElementById('dumpResultsTime').textContent = `· ${data.took_seconds || '—'}s`;
  
  // KPIs
  animateValue('dumpDorksCount', data.dorks_executed || 0);
  animateValue('dumpUrlsCount', data.urls_found || 0);
  animateValue('dumpFetchedCount', data.urls_fetched || 0);
  animateValue('dumpCombosCount', data.filtered_combos_count || 0);
  document.getElementById('dumpTookCount').textContent = (data.took_seconds || '—') + 's';
  
  // Sidebar badge
  document.getElementById('sidebarDumpCount').textContent = data.filtered_combos_count || 0;
  
  // Top URLs
  const urls = data.top_urls || [];
  const urlsContainer = document.getElementById('dumpUrlsList');
  if (urls.length === 0) {
    urlsContainer.innerHTML = '<div class="empty-state" style="padding:5px"><p>No se encontraron URLs</p></div>';
  } else {
    urlsContainer.innerHTML = urls.map((u, i) => {
      const maxUrl = 80;
      const displayUrl = u.url.length > maxUrl ? u.url.substring(0, maxUrl) + '...' : u.url;
      return `<div class="stat-row" style="font-size:9px">
        <span style="color:var(--text3);width:20px">${i+1}.</span>
        <span class="lb" style="max-width:100%;overflow:hidden;text-overflow:ellipsis;font-family:var(--mono);font-size:8px;color:var(--accent2)" title="${escapeHtml(u.url)}">${escapeHtml(displayUrl)}</span>
        <span class="vl" style="font-size:7px;color:var(--text3)">${escapeHtml(u.source || '')}</span>
      </div>`;
    }).join('');
  }
  
  // Combos table
  const tbody = document.getElementById('dumpBody');
  if (dumpData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">🔍 No se encontraron combos con los filtros actuales</td></tr>';
  } else {
    tbody.innerHTML = dumpData.map(c => {
      const pwHidden = c.password ? (c.password.length > 15 ? c.password.substring(0, 12) + '***' : c.password) : '—';
      return `<tr>
        <td class="email-cell">${escapeHtml(c.email || '—')}</td>
        <td style="font-family:var(--mono);font-size:9px;color:var(--text2)">${escapeHtml(pwHidden)}</td>
        <td class="domain">${escapeHtml(c.domain || '—')}</td>
        <td class="source-cell">${escapeHtml(c.source || c.source_type || '—')}</td>
        <td class="date-cell">${escapeHtml(c.date || c.discovered_date || '—')}</td>
      </tr>`;
    }).join('');
  }
  
  document.getElementById('dumpResults').classList.add('active');
  
  // By source
  const bySource = data.stats?.by_source || {};
  document.getElementById('dumpBySource').innerHTML = Object.entries(bySource)
    .sort((a,b) => b[1] - a[1])
    .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl accent">${v}</span></div>`)
    .join('') || '<div class="empty-state" style="padding:5px"><p>Sin datos</p></div>';
  
  // By domain
  const byDomain = data.stats?.by_domain || {};
  document.getElementById('dumpByDomain').innerHTML = Object.entries(byDomain)
    .sort((a,b) => b[1] - a[1])
    .slice(0, 10)
    .map(([k,v]) => `<div class="stat-row"><span class="lb">${k}</span><span class="vl">${v}</span></div>`)
    .join('') || '<div class="empty-state" style="padding:5px"><p>Sin datos</p></div>';
  
  // Saved files
  const files = data.files_saved?.files_created || [];
  const savedContainer = document.getElementById('dumpSavedFiles');
  if (files.length > 0) {
    savedContainer.innerHTML = files.map(f => {
      const relativePath = f.replace(/.*\\data\\/, 'data/').replace(/\\/g, '/');
      return `<div class="stat-row" style="font-size:8px">
        <span class="lb" style="font-family:var(--mono);color:var(--green)">📄</span>
        <span class="vl" style="font-size:8px;font-family:var(--mono);color:var(--text2)">${escapeHtml(relativePath)}</span>
      </div>`;
    }).join('');
    savedContainer.innerHTML += `<div class="stat-row"><span class="lb">Total guardados</span><span class="vl accent">${data.files_saved?.total_saved || 0}</span></div>`;
  } else {
    savedContainer.innerHTML = '<div class="empty-state" style="padding:5px"><p>No se guardaron archivos (desactivado o sin resultados)</p></div>';
  }
}

function exportDumpResults() {
  if (dumpData.length === 0) { showToast('❌ No hay datos para exportar', 'var(--red)'); return; }
  
  const csv = ['email,password,dominio,fuente,fecha'];
  dumpData.forEach(c => {
    csv.push(`"${c.email || ''}","${c.password || ''}","${c.domain || ''}","${c.source || c.source_type || ''}","${c.date || c.discovered_date || ''}"`);
  });
  
  const blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  const kw = document.getElementById('dumpKeyword').value.trim() || 'dump';
  link.download = `dump_${kw}_${new Date().toISOString().split('T')[0]}.csv`;
  link.click();
  showToast(`📥 Exportados ${dumpData.length} combos a CSV (solo muestra)`, 'var(--accent2)');
}

async function exportDumpAllTxt() {
  const keyword = document.getElementById('dumpKeyword').value.trim();
  if (!keyword) { showToast('❌ Ingresa una palabra clave', 'var(--red)'); return; }
  const now = new Date();
  const ts = now.getFullYear() + '-' +
    String(now.getMonth() + 1).padStart(2, '0') + '-' +
    String(now.getDate()).padStart(2, '0') + '_' +
    String(now.getHours()).padStart(2, '0') + '-' +
    String(now.getMinutes()).padStart(2, '0') + '-' +
    String(now.getSeconds()).padStart(2, '0');
  const filename = `dump_${keyword}_${ts}.txt`;
  showToast(`📥 Exportando todos los combos a TXT...`, 'var(--yellow)');
  await exportDumpFile('txt', filename);
}

async function exportDumpFile(fmt, customFilename) {
  const keyword = document.getElementById('dumpKeyword').value.trim();
  if (!keyword) { showToast('❌ Ingresa una palabra clave para exportar', 'var(--red)'); return; }
  
  showToast(`🔄 Exportando todos los combos a ${fmt.toUpperCase()}...`, 'var(--yellow)');
  
  try {
    const year = document.getElementById('dumpYear').value;
    const month = document.getElementById('dumpMonth').value;
    
    let url = `/api/dump/export?keyword=${encodeURIComponent(keyword)}&fmt=${fmt}`;
    if (year) url += `&year=${year}`;
    if (month) url += `&month=${month}`;
    
    const resp = await fetch(url, { signal: AbortSignal.timeout(120000) });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    
    const blob = await resp.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = customFilename || `dump_${keyword}_${fmt}.${fmt}`;
    link.click();
    showToast(`📥 Dump completo exportado a ${fmt.toUpperCase()}`, 'var(--green)');
  } catch (err) {
    showToast('❌ Error de exportación: ' + err.message, 'var(--red)');
  }
}


// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
  updateDashboardKPIs();
  updateClock();
  
  // Load from localStorage
  try {
    const saved = JSON.parse(localStorage.getItem('oraculo_state'));
    if (saved) {
      state.records = saved.records || [];
      state.searchHistory = saved.searchHistory || [];
      state.filteredRecords = [...state.records];
      updateDashboardKPIs();
      document.getElementById('sidebarSearchCount').textContent = state.searchHistory.length;
      document.getElementById('sidebarRecordsCount').textContent = state.records.length;
    }
  } catch (e) {}
  
  // Save state periodically
  setInterval(() => {
    try {
      localStorage.setItem('oraculo_state', JSON.stringify({
        records: state.records.slice(-500),
        searchHistory: state.searchHistory.slice(-50),
      }));
    } catch (e) {}
  }, 10000);
});
