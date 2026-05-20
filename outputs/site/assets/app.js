
const DATA = window.MASENTINEL_DATA || { summary: {}, systems: [] };

const state = {
  faultSort: { key: 'severity', dir: 'desc' },
  casePage: 1,
  casesPerPage: 20
};

document.addEventListener('DOMContentLoaded', () => {
  initScrollSpy();
  initFaultTable();
  initTraceGraph();
  initTestcaseExplorer();
});

function allFaults() {
  return DATA.systems.flatMap(system => system.faults || []);
}

function allCases() {
  return DATA.systems.flatMap(system => system.testcases || []);
}

function uniqueValues(rows, key) {
  return [...new Set(rows.map(row => row[key]).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
}

function fillSelect(select, values) {
  if (!select) return;
  const current = select.value;
  while (select.options.length > 1) select.remove(1);
  values.forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = decodeEntities(value);
    select.appendChild(option);
  });
  select.value = values.includes(current) ? current : '';
}

function initFaultTable() {
  const rows = allFaults();
  fillSelect(document.getElementById('fault-severity-filter'), uniqueValues(rows, 'severity'));
  fillSelect(document.getElementById('fault-layer-filter'), uniqueValues(rows, 'layer'));

  ['fault-severity-filter', 'fault-layer-filter'].forEach(id => {
    const element = document.getElementById(id);
    if (element) element.addEventListener('change', renderFaultTable);
  });

  document.querySelectorAll('#fault-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.faultSort.key === key) {
        state.faultSort.dir = state.faultSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.faultSort = { key, dir: 'asc' };
      }
      renderFaultTable();
    });
  });

  renderFaultTable();
}

function renderFaultTable() {
  const tbody = document.getElementById('fault-table-body');
  if (!tbody) return;
  const severity = document.getElementById('fault-severity-filter')?.value || '';
  const layer = document.getElementById('fault-layer-filter')?.value || '';
  let rows = allFaults().filter(row => (!severity || row.severity === severity) && (!layer || row.layer === layer));
  const key = state.faultSort.key;
  const dir = state.faultSort.dir === 'asc' ? 1 : -1;
  rows = rows.slice().sort((a, b) => compareValues(a[key], b[key]) * dir);
  tbody.innerHTML = rows.map((row, index) => faultRowHtml(row, index)).join('') || `<tr><td colspan="8">N/A</td></tr>`;
  tbody.querySelectorAll('tr.fault-row').forEach(row => {
    row.addEventListener('click', () => toggleDetailRow(row.nextElementSibling));
  });
}

function faultRowHtml(row, index) {
  const detailId = `fault-detail-${index}`;
  return `
    <tr class="clickable fault-row" aria-controls="${detailId}">
      <td><code>${row.fault_id || 'N/A'}</code></td>
      <td><code>${row.case_id || 'N/A'}</code></td>
      <td>${row.layer || 'N/A'}</td>
      <td>${row.fault_type || 'N/A'}</td>
      <td><code>${row.failure_code || 'N/A'}</code></td>
      <td>${statusBadge(row.severity || 'unknown')}</td>
      <td>${row.confidence || 'N/A'}</td>
      <td>${row.summary || 'N/A'}</td>
    </tr>
    <tr id="${detailId}" class="detail-row">
      <td colspan="8">
        <div class="detail-panel">
          <div class="detail-content">
            ${detailBlock('root_cause', row.root_cause)}
            ${detailBlock('suggested_fix', row.suggested_fix)}
            ${detailBlock('evidence', row.evidence)}
            ${detailBlock('reproduction', row.reproduction)}
          </div>
        </div>
      </td>
    </tr>
  `;
}

function detailBlock(title, value) {
  return `<div><strong>${title}</strong><pre>${value || 'N/A'}</pre></div>`;
}

function toggleDetailRow(row) {
  if (!row) return;
  row.classList.toggle('open');
}

function compareValues(a, b) {
  const na = Number(a);
  const nb = Number(b);
  if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
  return String(a || '').localeCompare(String(b || ''));
}

function statusBadge(value) {
  const normalized = String(value || 'neutral').toLowerCase();
  let klass = 'neutral';
  if (['passed', 'pass', 'success', 'high'].includes(normalized)) klass = normalized === 'high' ? 'failed' : 'passed';
  if (['failed', 'fail', 'timeout', 'error', 'critical'].includes(normalized)) klass = 'failed';
  if (['medium', 'warning', 'suspected'].includes(normalized)) klass = 'warning';
  return `<span class="status-badge ${klass}">${value || 'N/A'}</span>`;
}

function initTraceGraph() {
  const select = document.getElementById('trace-system-select');
  if (select) {
    select.addEventListener('change', () => renderTraceGraph(select.value));
    renderTraceGraph(select.value || DATA.systems[0]?.system_id);
  } else {
    renderTraceGraph(DATA.systems[0]?.system_id);
  }
}

function renderTraceGraph(systemId) {
  const container = document.getElementById('trace-graph');
  if (!container) return;
  const system = DATA.systems.find(item => item.system_id === systemId) || DATA.systems[0];
  const graph = system?.trace_graph || { nodes: [], edges: [] };
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  if (!nodes.length) {
    container.innerHTML = `<p class="empty-state" style="padding: 18px;">N/A</p>`;
    return;
  }

  const agents = nodes.filter(node => node.type === 'agent');
  const tools = nodes.filter(node => node.type === 'tool');
  const others = nodes.filter(node => node.type !== 'agent' && node.type !== 'tool');
  const leftNodes = agents.length ? agents : nodes;
  const rightNodes = tools.length ? tools.concat(others) : others;
  const width = 1000;
  const height = Math.max(420, Math.max(leftNodes.length, rightNodes.length || 1) * 74 + 80);
  const positions = {};

  leftNodes.forEach((node, i) => {
    positions[node.id] = { x: 170, y: 70 + i * 74, type: node.type || 'agent' };
  });
  rightNodes.forEach((node, i) => {
    positions[node.id] = { x: 720, y: 70 + i * 74, type: node.type || 'tool' };
  });
  nodes.forEach((node, i) => {
    if (!positions[node.id]) {
      positions[node.id] = { x: 445, y: 70 + i * 58, type: node.type || 'unknown' };
    }
  });

  const edgeSvg = edges.map((edge, i) => {
    const source = positions[edge.source];
    const target = positions[edge.target];
    if (!source || !target) return '';
    const midX = (source.x + target.x) / 2;
    const yOffset = source.y === target.y ? 0 : (i % 3 - 1) * 8;
    const path = `M ${source.x + 85} ${source.y} L ${midX} ${source.y + yOffset} L ${midX} ${target.y + yOffset} L ${target.x - 85} ${target.y}`;
    const labelX = midX + 8;
    const labelY = (source.y + target.y) / 2 - 4 + yOffset;
    return `<path class="trace-edge" d="${path}" marker-end="url(#arrow)"></path><text class="trace-label" x="${labelX}" y="${labelY}">${edge.source || ''} → ${edge.target || ''} (${edge.count || 1})</text>`;
  }).join('');

  const nodeSvg = nodes.map(node => {
    const pos = positions[node.id];
    const label = truncateMiddle(node.id || 'N/A', 26);
    if (pos.type === 'tool') {
      return `<ellipse class="trace-node-tool" cx="${pos.x}" cy="${pos.y}" rx="96" ry="25"></ellipse><text class="trace-node-label" x="${pos.x}" y="${pos.y + 4}" text-anchor="middle">${label}</text>`;
    }
    return `<rect class="trace-node-agent" x="${pos.x - 96}" y="${pos.y - 24}" width="192" height="48" rx="9"></rect><text class="trace-node-label" x="${pos.x}" y="${pos.y + 4}" text-anchor="middle">${label}</text>`;
  }).join('');

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trace graph for ${system?.system_id || 'system'}">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z" fill="#798398"></path>
        </marker>
      </defs>
      <text x="80" y="28" class="trace-label">Agents</text>
      <text x="672" y="28" class="trace-label">Tools / Other Nodes</text>
      ${edgeSvg}
      ${nodeSvg}
    </svg>
  `;
}

function initTestcaseExplorer() {
  const rows = allCases();
  fillSelect(document.getElementById('case-type-filter'), uniqueValues(rows, 'type'));
  fillSelect(document.getElementById('case-status-filter'), uniqueValues(rows, 'status'));
  fillSelect(document.getElementById('case-failure-filter'), uniqueValues(rows, 'failure_code'));

  ['case-type-filter', 'case-status-filter', 'case-failure-filter', 'case-search'].forEach(id => {
    const element = document.getElementById(id);
    if (!element) return;
    const eventName = element.tagName === 'INPUT' ? 'input' : 'change';
    element.addEventListener(eventName, () => {
      state.casePage = 1;
      renderCases();
    });
  });

  renderCases();
}

function filteredCases() {
  const type = document.getElementById('case-type-filter')?.value || '';
  const status = document.getElementById('case-status-filter')?.value || '';
  const failure = document.getElementById('case-failure-filter')?.value || '';
  const search = (document.getElementById('case-search')?.value || '').toLowerCase();
  return allCases().filter(row => {
    if (type && row.type !== type) return false;
    if (status && row.status !== status) return false;
    if (failure && row.failure_code !== failure) return false;
    if (!search) return true;
    return [row.system_id, row.case_id, row.type, row.status, row.failure_code, row.description, row.expected, row.actual, row.steps]
      .join(' ')
      .toLowerCase()
      .includes(search);
  });
}

function renderCases() {
  const tbody = document.getElementById('case-table-body');
  if (!tbody) return;
  const rows = filteredCases();
  const totalPages = Math.max(1, Math.ceil(rows.length / state.casesPerPage));
  state.casePage = Math.min(Math.max(state.casePage, 1), totalPages);
  const start = (state.casePage - 1) * state.casesPerPage;
  const pageRows = rows.slice(start, start + state.casesPerPage);
  tbody.innerHTML = pageRows.map((row, index) => caseRowHtml(row, start + index)).join('') || `<tr><td colspan="5">N/A</td></tr>`;
  tbody.querySelectorAll('tr.case-row').forEach(row => {
    row.addEventListener('click', event => {
      if (event.target.tagName === 'BUTTON') return;
      toggleDetailRow(row.nextElementSibling);
    });
  });
  tbody.querySelectorAll('.case-toggle').forEach(button => {
    button.addEventListener('click', event => {
      event.stopPropagation();
      const row = button.closest('tr');
      toggleDetailRow(row?.nextElementSibling);
    });
  });
  renderPagination(totalPages);
}

function caseRowHtml(row, index) {
  const detailId = `case-detail-${index}`;
  return `
    <tr class="clickable case-row" aria-controls="${detailId}">
      <td><code>${row.case_id || 'N/A'}</code><div class="muted-small">${row.system_id || 'N/A'}</div></td>
      <td>${row.type || 'N/A'}</td>
      <td>${statusBadge(row.status || 'N/A')}</td>
      <td><code>${row.failure_code || 'N/A'}</code></td>
      <td class="truncate-cell">${preview(row.description || 'N/A', 180)} <button type="button" class="small-button case-toggle">expand</button></td>
    </tr>
    <tr id="${detailId}" class="detail-row">
      <td colspan="5">
        <div class="detail-panel">
          <div class="case-detail-content">
            ${detailBlock('description', row.description)}
            ${detailBlock('expected', row.expected)}
            ${detailBlock('actual', row.actual)}
            ${detailBlock('steps', row.steps)}
          </div>
        </div>
      </td>
    </tr>
  `;
}

function renderPagination(totalPages) {
  const container = document.getElementById('case-pagination');
  if (!container) return;
  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }
  const buttons = [];
  for (let page = 1; page <= totalPages; page += 1) {
    buttons.push(`<button type="button" class="page-button ${page === state.casePage ? 'active' : ''}" data-page="${page}">${page}</button>`);
  }
  container.innerHTML = buttons.join('');
  container.querySelectorAll('button').forEach(button => {
    button.addEventListener('click', () => {
      state.casePage = Number(button.dataset.page) || 1;
      renderCases();
    });
  });
}

function initScrollSpy() {
  const links = [...document.querySelectorAll('.nav-link')];
  const sections = [...document.querySelectorAll('.observed-section')];
  if (!('IntersectionObserver' in window) || !sections.length) return;
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      links.forEach(link => link.classList.toggle('active', link.getAttribute('href') === `#${entry.target.id}`));
    });
  }, { rootMargin: '-35% 0px -55% 0px', threshold: 0.01 });
  sections.forEach(section => observer.observe(section));
}

function preview(value, maxLength) {
  const text = String(value || 'N/A');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function truncateMiddle(value, maxLength) {
  const text = String(value || 'N/A');
  if (text.length <= maxLength) return text;
  const keep = Math.floor((maxLength - 3) / 2);
  return `${text.slice(0, keep)}...${text.slice(-keep)}`;
}

function decodeEntities(value) {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = String(value || '');
  return textarea.value;
}
