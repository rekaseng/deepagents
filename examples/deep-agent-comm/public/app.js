const feed = document.getElementById('feed')
const form = document.getElementById('goal-form')
const input = document.getElementById('goal-input')
const sendBtn = document.getElementById('send-btn')

const chatView = document.getElementById('chat-view')
const catalogView = document.getElementById('catalog-view')
const catalogBody = document.getElementById('catalog-body')
const filtersEl = document.getElementById('filters')
const hoverZone = document.getElementById('hover-zone')
const hoverTrigger = document.getElementById('hover-trigger')

const EMPTY_STATE_HTML = `
  <div class="empty-state">
    <div class="empty-logo">◆</div>
    <p>Give the agent a goal.</p>
    <span>It plans, calls tools, and reports back.</span>
  </div>`

// ---- helpers ----
function el(tag, cls, html) {
  const e = document.createElement(tag)
  if (cls) e.className = cls
  if (html !== undefined) e.innerHTML = html
  return e
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

function clearEmpty() {
  const es = feed.querySelector('.empty-state')
  if (es) es.remove()
}

function scrollDown() { feed.scrollTop = feed.scrollHeight }

// =====================================================================
// Catalog data — mirrors docs/03-communication-layer.md
// status: ready (✅ built) | partial (◐) | planned (🔲/⭕) | withheld (🚫)
// =====================================================================
const STATUS = {
  ready:    { label: 'Ready',       cls: 'st-ready' },
  partial:  { label: 'In progress', cls: 'st-partial' },
  planned:  { label: 'Planned',     cls: 'st-planned' },
  withheld: { label: 'Withheld',    cls: 'st-withheld' },
}

function item(name, desc, status, extra = {}) {
  return { name, desc, status, ...extra }
}

const TOOL_CATALOG = [
  {
    tier: 'Tier 1 — Gmail core (P0)',
    note: 'Transport: Gmail REST API (OAuth2). Draft-only is enforced by the absence of gmail_send.',
    groups: [
      {
        name: 'Read',
        items: [
          item('gmail_search', 'Full Gmail query syntax: from:, is:unread, has:attachment, newer_than:…', 'ready'),
          item('gmail_list_unread', 'Narrow: most-recent unread only (advertises its narrowness)', 'ready'),
          item('gmail_get_message', 'Full body + HTML body + attachment metadata by Message-ID; download=true materializes sheets', 'ready'),
          item('gmail_get_thread', 'Whole conversation, ordered — native threadId', 'ready'),
          item('gmail_get_attachment', 'Download any attachment type by filename', 'ready'),
        ],
      },
      {
        name: 'Write (drafts only)',
        items: [
          item('gmail_create_draft', 'Reply / new draft; cc[] = reply-all; inReplyTo threads; attachmentPaths[]', 'ready'),
          item('gmail_forward_draft', 'Forward draft carrying original body + attachments', 'ready'),
          item('gmail_update_draft', 'In-place draft edit (native drafts.update)', 'ready'),
          item('gmail_list_drafts', 'List drafts as first-class objects', 'ready'),
          item('gmail_delete_draft', 'Delete a draft', 'ready'),
        ],
      },
      {
        name: 'Organize',
        items: [
          item('gmail_organize', 'mark_read/unread, star/unstar, mark_important/unmark_important, archive, trash, restore', 'ready'),
          item('gmail_label', 'Apply/remove a label by name (auto-creates on apply)', 'ready'),
          item('gmail_manage_labels', 'List / create / delete labels', 'ready'),
          item('gmail_mark_read', 'Shortcut used by triggers', 'ready'),
        ],
      },
      {
        name: 'Sync',
        items: [
          item('gmail_history', 'Incremental changes since a historyId cursor', 'ready'),
          item('gmail_watch', 'Start/stop Pub/Sub push on INBOX', 'partial', { note: 'needs Cloud Pub/Sub topic' }),
        ],
      },
      {
        name: 'Settings (need gmail.settings.* scopes + re-consent)',
        items: [
          item('gmail_filters', 'List / create / delete server-side filters', 'ready'),
          item('gmail_vacation', 'Get / set vacation auto-responder', 'ready'),
          item('gmail_sendas', 'List aliases / update signature', 'ready'),
          item('gmail_forwarding', 'List forwarding addresses', 'ready'),
          item('gmail_imap_pop', 'Get/toggle IMAP & POP access', 'ready'),
          item('gmail_delegates', 'List delegates', 'partial', { note: 'Workspace-only (personal Gmail not supported)' }),
        ],
      },
    ],
  },
  {
    tier: 'Tier 2 — Content / data work (P1)',
    note: 'What the agent does with email content. Heavy/risky work runs in the sandbox via a sub-agent.',
    groups: [
      {
        name: null,
        items: [
          item('excel_read', 'Parse .xlsx/.csv → rows (cap 100)', 'ready', { tags: ['sandbox: in-process v1'] }),
          item('excel_write', 'Build .xlsx from rows', 'ready', { tags: ['sandbox: sub-agent'] }),
          item('chart_generate', 'Data → chart PNG (QuickChart)', 'ready', { tags: ['sandbox: sub-agent'] }),
          item('sql_query', 'Single read-only SELECT vs demo DB', 'ready', { tags: ['guarded'] }),
          item('run_code', 'Run JS in child-process sandbox (fs-locked)', 'ready', { tags: ['sub-agent only'], note: 'not registered on the main agent — least privilege' }),
          item('spawn_subagent', 'Delegate to isolated least-privilege sub-agent', 'ready'),
          item('pdf_read', 'Extract text/tables from PDF', 'planned', { tags: ['sandbox'], note: '.xlsx/.csv only in v1' }),
          item('http_request', 'Call external REST API', 'planned', { tags: ['allow-listed'] }),
        ],
      },
    ],
  },
  {
    tier: 'Tier 3 — Extensibility & utility',
    groups: [
      {
        name: null,
        items: [
          item('web_fetch', "Fetch a URL's content", 'ready'),
          item('calculator', 'Math', 'ready'),
          item('echo', 'Pipeline test', 'ready'),
          item('mcp_*', 'Dynamically discovered external tools via MCP', 'planned', { note: 'Phase 5b' }),
        ],
      },
    ],
  },
  {
    tier: 'Tier 4 — Other channels (P2, later)',
    note: 'Same Channel interface, different backend — the Gmail IMAP→API migration proved the swap touches only L0.',
    groups: [
      {
        name: null,
        items: [
          item('teams_*', 'Microsoft Teams channel', 'planned'),
          item('slack_*', 'Slack channel', 'planned'),
          item('messenger_*', 'Messenger channel', 'planned'),
        ],
      },
    ],
  },
  {
    tier: 'Withheld by guardrail',
    groups: [
      {
        name: null,
        items: [
          item('gmail_send', 'Draft-only policy: nothing auto-sends. Enforced by this tool not existing.', 'withheld'),
          item('gmail permanent delete', 'Destructive — permanently deleting messages is withheld (trash + restore only).', 'withheld'),
        ],
      },
    ],
  },
]

const SKILL_CATALOG = [
  {
    tier: 'Tier 1 — Email triage & response (P0)',
    groups: [
      {
        name: null,
        items: [
          item('summarize-thread', 'TL;DR a thread', 'ready', { tags: ['intent: summarize', 'uses: gmail_get_thread, gmail_create_draft'] }),
          item('draft-reply', 'Contextual reply draft', 'ready', { tags: ['intent: compose', 'uses: gmail_get_thread, gmail_create_draft'] }),
          item('clarify', 'Fallback when intent unclear → asks the sender', 'ready', { tags: ['intent: clarify', 'uses: gmail_create_draft'] }),
          item('triage-inbox', 'Classify/label/flag unread', 'planned', { tags: ['intent: triage', 'uses: gmail_search, gmail_organize'] }),
          item('extract-action-items', 'Pull tasks/dates/asks from a thread', 'planned', { tags: ['intent: extract', 'uses: gmail_get_thread'] }),
        ],
      },
    ],
  },
  {
    tier: 'Tier 2 — Data tasks from email (P1)',
    note: 'The "wow" features — need the sandbox + sub-agent.',
    groups: [
      {
        name: null,
        items: [
          item('excel-to-chart', 'Attached sheet → chart PNG → reply draft (flagship, proven end-to-end)', 'ready', { tags: ['intent: visualize', 'sub-agent'] }),
          item('excel-analyze', 'Read sheet, answer questions about the data', 'ready', { tags: ['intent: analyze', 'sub-agent'] }),
          item('data-query', 'NL question → read-only SQL → plain-English reply', 'ready', { tags: ['intent: data-query'] }),
          item('excel-generate', 'Build a new spreadsheet from a request', 'planned', { tags: ['intent: generate', 'sub-agent'] }),
          item('report-build', 'Gather data + build formatted excel/pdf, attach', 'planned', { tags: ['intent: report', 'sub-agent'] }),
        ],
      },
    ],
  },
  {
    tier: 'Tier 3 — Integration & proactive',
    groups: [
      {
        name: null,
        items: [
          item('inbox-digest', '(schedule 08:00) Summarize unread → digest draft', 'ready', { tags: ['intent: digest'] }),
          item('unanswered-nudge', '(schedule 17:30) Flag stale unread → nudge draft', 'ready', { tags: ['intent: followup'], note: 'inline in triggers/schedule.ts, not a skill file' }),
          item('mcp-fetch', 'Pull/push to an external system via MCP', 'planned', { tags: ['intent: integrate'], note: 'Phase 5b' }),
        ],
      },
    ],
  },
]

// live registry state (merged into the catalog as green "live" dots)
let liveTools = new Set()
let liveSkills = new Set()
let liveToolMeta = []
let liveSkillMeta = []

let activeTab = 'tools'
let activeFilter = 'all'

// current chat session — null until the first run creates one
let currentSessionId = null

function catalogItems(cat) {
  return cat.flatMap(t => t.groups.flatMap(g => g.items))
}

function liveExtras(cat, meta) {
  const known = new Set(catalogItems(cat).map(i => i.name))
  return meta
    .filter(m => !known.has(m.name))
    .map(m => item(m.name, m.description || '', 'ready', { note: 'registered at runtime — not in the catalog doc' }))
}

// ---- catalog render ----
function renderCatalogCard(it, isLive) {
  const card = el('div', 'card')
  const head = el('div', 'card-head')
  head.append(el('span', 'card-name', escapeHtml(it.name)))
  if (isLive) {
    const dot = el('span', 'live-dot')
    dot.title = 'registered live in the runtime'
    head.append(dot)
  }
  const st = STATUS[it.status]
  head.append(el('span', `chip-status ${st.cls}`, st.label))
  card.append(head)
  if (it.desc) card.append(el('div', 'card-desc', escapeHtml(it.desc)))
  if (it.tags && it.tags.length) {
    const tg = el('div', 'tags')
    it.tags.forEach(t => tg.append(el('span', 'tag', escapeHtml(t))))
    card.append(tg)
  }
  if (it.note) card.append(el('div', 'card-note', escapeHtml(it.note)))
  return card
}

function renderCatalog() {
  document.querySelectorAll('.tab').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === activeTab))

  const data = activeTab === 'tools' ? TOOL_CATALOG : SKILL_CATALOG
  const liveSet = activeTab === 'tools' ? liveTools : liveSkills
  const liveMeta = activeTab === 'tools' ? liveToolMeta : liveSkillMeta
  const extras = liveExtras(data, liveMeta)

  // filter chips with counts
  const all = [...catalogItems(data), ...extras]
  const counts = { all: all.length, ready: 0, partial: 0, planned: 0, withheld: 0 }
  all.forEach(i => counts[i.status]++)

  filtersEl.innerHTML = ''
  const chips = [
    ['all', 'All'], ['ready', 'Ready'], ['partial', 'In progress'],
    ['planned', 'Planned'], ['withheld', 'Withheld'],
  ]
  chips.forEach(([key, label]) => {
    if (key !== 'all' && counts[key] === 0) return
    const c = el('button', 'chip' + (activeFilter === key ? ' active' : ''),
      `${label}<span>${counts[key]}</span>`)
    c.onclick = () => { activeFilter = key; renderCatalog() }
    filtersEl.append(c)
  })

  // body
  const match = i => activeFilter === 'all' || i.status === activeFilter
  catalogBody.innerHTML = ''

  data.forEach(tierData => {
    const groups = tierData.groups
      .map(g => ({ ...g, items: g.items.filter(match) }))
      .filter(g => g.items.length)
    if (!groups.length) return

    const sec = el('section', 'tier')
    sec.append(el('h3', '', escapeHtml(tierData.tier)))
    if (tierData.note) sec.append(el('p', 'tier-note', escapeHtml(tierData.note)))
    groups.forEach(g => {
      if (g.name) sec.append(el('div', 'group-name', escapeHtml(g.name)))
      const grid = el('div', 'cards')
      g.items.forEach(i => grid.append(renderCatalogCard(i, liveSet.has(i.name))))
      sec.append(grid)
    })
    catalogBody.append(sec)
  })

  const extraItems = extras.filter(match)
  if (extraItems.length) {
    const sec = el('section', 'tier')
    sec.append(el('h3', '', 'Also registered at runtime'))
    const grid = el('div', 'cards')
    extraItems.forEach(i => grid.append(renderCatalogCard(i, true)))
    sec.append(grid)
    catalogBody.append(sec)
  }

  if (activeTab === 'skills' && activeFilter === 'all') {
    catalogBody.append(el('p', 'flagship',
      '★ Flagship flow proven end-to-end: email an excel → <b>excel-to-chart</b> → sandboxed sub-agent (excel_read → chart_generate) → reply draft with chart.png attached.'))
  }
}

function updateFlyoutCounts() {
  const stat = cat => {
    const items = catalogItems(cat)
    return `${items.filter(i => i.status === 'ready').length}/${items.length} ready`
  }
  document.getElementById('fly-tools-count').textContent = stat(TOOL_CATALOG)
  document.getElementById('fly-skills-count').textContent = stat(SKILL_CATALOG)
}

// ---- view switching ----
function showChat() {
  catalogView.classList.add('hidden')
  chatView.classList.remove('hidden')
}

function showCatalog(tab) {
  activeTab = tab
  activeFilter = 'all'
  chatView.classList.add('hidden')
  catalogView.classList.remove('hidden')
  hoverZone.classList.remove('open')
  renderCatalog()
}

// ---- chat render ----
function addUserMsg(text) {
  clearEmpty()
  const m = el('div', 'msg user')
  m.append(el('div', 'role', 'you'), el('div', 'bubble', escapeHtml(text)))
  feed.append(m)
  scrollDown()
}

function addThinking() {
  const m = el('div', 'msg agent')
  m.id = 'thinking'
  m.append(
    el('div', 'role', 'agent'),
    el('div', 'bubble', '<div class="thinking"><span></span><span></span><span></span></div>')
  )
  feed.append(m)
  scrollDown()
  return m
}

function renderStep(step) {
  const s = el('div', 'step')
  const head = el('div', 'step-head')
  head.append(el('span', `pill ${step.type}`, step.type))

  if (step.type === 'tool') {
    const name = step.input?.tool ?? '?'
    head.append(el('span', '', escapeHtml(name)))
    const ok = step.output?.success
    head.append(el('span', ok ? 'ok' : 'fail', ok ? '✓' : '✗'))
    s.append(head)
    s.append(el('pre', '', escapeHtml(JSON.stringify(step.input?.args ?? {}, null, 2))))
    s.append(el('pre', '', escapeHtml(JSON.stringify(step.output ?? {}, null, 2))))
  } else if (step.type === 'skill') {
    const names = (step.input?.matched ?? []).join(', ')
    head.append(el('span', '', escapeHtml(names)))
    s.append(head)
  } else {
    head.append(el('span', '', 'final answer'))
    s.append(head)
  }
  return s
}

function addAgentMsg(result, steps) {
  const m = el('div', 'msg agent')
  m.append(el('div', 'role', 'agent'))
  m.append(el('div', 'bubble', escapeHtml(result)))

  const traceSteps = (steps || []).filter(s => s.type === 'tool' || s.type === 'skill')
  if (traceSteps.length) {
    const toolCount = traceSteps.filter(s => s.type === 'tool').length
    const skillCount = traceSteps.filter(s => s.type === 'skill').length
    const parts = []
    if (skillCount) parts.push(`${skillCount} skill`)
    if (toolCount) parts.push(`${toolCount} tool call${toolCount > 1 ? 's' : ''}`)
    const trace = el('details', 'trace')
    trace.append(el('summary', '', parts.join(' · ')))
    traceSteps.forEach(s => trace.append(renderStep(s)))
    m.append(trace)
  }
  feed.append(m)
  scrollDown()
}

function addError(msg) {
  const m = el('div', 'msg agent')
  m.append(el('div', 'role', 'error'))
  const b = el('div', 'bubble')
  b.style.borderColor = 'var(--red)'
  b.style.color = 'var(--red)'
  b.textContent = msg
  m.append(b)
  feed.append(m)
  scrollDown()
}

// ---- run ----
async function runGoal(goal) {
  addUserMsg(goal)
  const thinking = addThinking()
  sendBtn.disabled = true

  try {
    const res = await fetch('/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, sessionId: currentSessionId }),
    })
    thinking.remove()
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      addError(err.error || `Request failed (${res.status})`)
    } else {
      const data = await res.json()
      currentSessionId = data.sessionId || currentSessionId
      addAgentMsg(data.result, data.steps)
      loadSessions()
    }
  } catch (e) {
    thinking.remove()
    addError(String(e))
  } finally {
    sendBtn.disabled = false
  }
}

// ---- sidebar data ----
async function loadTools() {
  try {
    liveToolMeta = await (await fetch('/tools')).json()
    liveTools = new Set(liveToolMeta.map(t => t.name))
  } catch {}
  updateFlyoutCounts()
  if (!catalogView.classList.contains('hidden')) renderCatalog()
}

async function loadSkills() {
  try {
    liveSkillMeta = await (await fetch('/skills')).json()
    liveSkills = new Set(liveSkillMeta.map(s => s.name))
  } catch {}
  updateFlyoutCounts()
  if (!catalogView.classList.contains('hidden')) renderCatalog()
}

function markActiveSession() {
  document.querySelectorAll('#history-list li').forEach(li =>
    li.classList.toggle('active', li.dataset.id === currentSessionId))
}

async function loadSessions() {
  try {
    const sessions = await (await fetch('/sessions')).json()
    const ul = document.getElementById('history-list')
    ul.innerHTML = ''
    sessions.forEach(s => {
      const li = el('li')
      li.dataset.id = s.id
      li.append(el('div', 'h-goal', escapeHtml(s.title)))
      const meta = s.turns > 1
        ? `${new Date(s.updated_at).toLocaleString()} · ${s.turns} turns`
        : new Date(s.updated_at).toLocaleString()
      li.append(el('div', 'h-time', meta))
      li.onclick = () => openSession(s.id)
      ul.append(li)
    })
    markActiveSession()
  } catch {}
}

async function openSession(id) {
  try {
    const turns = await (await fetch('/sessions/' + id)).json()
    currentSessionId = id
    feed.innerHTML = ''
    turns.forEach(t => {
      addUserMsg(t.goal)
      addAgentMsg(t.result, t.steps)
    })
    if (!turns.length) feed.innerHTML = EMPTY_STATE_HTML
    showChat()
    markActiveSession()
  } catch {}
}

function newChat() {
  currentSessionId = null
  feed.innerHTML = EMPTY_STATE_HTML
  markActiveSession()
  showChat()
  input.focus()
}

// ---- events ----
form.addEventListener('submit', e => {
  e.preventDefault()
  const goal = input.value.trim()
  if (!goal) return
  input.value = ''
  input.style.height = 'auto'
  runGoal(goal)
})

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    form.requestSubmit()
  }
})

input.addEventListener('input', () => {
  input.style.height = 'auto'
  input.style.height = Math.min(input.scrollHeight, 200) + 'px'
})

document.getElementById('new-chat').addEventListener('click', newChat)
document.getElementById('brand').addEventListener('click', showChat)
document.getElementById('back-chat').addEventListener('click', showChat)

document.querySelectorAll('.flyout-item').forEach(b =>
  b.addEventListener('click', () => showCatalog(b.dataset.tab)))

document.querySelectorAll('.tab').forEach(b =>
  b.addEventListener('click', () => {
    activeTab = b.dataset.tab
    activeFilter = 'all'
    renderCatalog()
  }))

// hover zone also works on click/touch
hoverTrigger.addEventListener('click', () => hoverZone.classList.toggle('open'))
document.addEventListener('click', e => {
  if (!hoverZone.contains(e.target)) hoverZone.classList.remove('open')
})

// ---- init ----
loadTools()
loadSkills()
loadSessions()
updateFlyoutCounts()
