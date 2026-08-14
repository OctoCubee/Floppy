from quart import Quart, jsonify, request, render_template_string
import state
import config

app = Quart(__name__)

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Floppy Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #1e1f22; --surface: #2b2d31; --surface2: #313338;
      --border: #3f4248; --text: #dbdee1; --muted: #949ba4;
      --accent: #5865f2; --accent-hover: #4752c4;
      --green: #43b581; --red: #f04747; --yellow: #faa61a;
    }
    body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
    .sidebar { position: fixed; top: 0; left: 0; width: 220px; height: 100vh; background: var(--surface); border-right: 1px solid var(--border); padding: 1.5rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; }
    .sidebar h1 { font-size: 1.2rem; font-weight: 700; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
    .nav-item { padding: 0.6rem 0.75rem; border-radius: 8px; cursor: pointer; font-size: 0.9rem; color: var(--muted); transition: all 0.15s; display: flex; align-items: center; gap: 0.6rem; }
    .nav-item:hover { background: var(--surface2); color: var(--text); }
    .nav-item.active { background: var(--accent); color: white; }
    .main { margin-left: 220px; padding: 2rem; max-width: 820px; }
    .page { display: none; }
    .page.active { display: block; }
    .page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }
    .page-header-left h2 { font-size: 1.4rem; font-weight: 700; margin-bottom: 0.25rem; }
    .page-header-left .subtitle { color: var(--muted); font-size: 0.9rem; }
    .card { background: var(--surface); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.25rem; border: 1px solid var(--border); }
    .card-title { font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 1rem; }
    .field { margin-bottom: 1rem; }
    .field:last-child { margin-bottom: 0; }
    label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 0.4rem; font-weight: 500; }
    input, select { width: 100%; padding: 0.6rem 0.85rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.92rem; font-family: inherit; transition: border-color 0.15s; }
    input:focus, select:focus { outline: none; border-color: var(--accent); }
    select option { background: var(--surface2); }
    .hint { font-size: 0.78rem; color: var(--muted); margin-top: 0.35rem; }
    .preview { font-size: 0.85rem; background: var(--surface2); border-radius: 8px; padding: 0.75rem 1rem; margin-top: 0.5rem; border-left: 3px solid var(--accent); color: var(--text); min-height: 2rem; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .btn { background: var(--accent); color: white; border: none; padding: 0.65rem 1.5rem; border-radius: 8px; font-size: 0.92rem; cursor: pointer; font-weight: 600; transition: background 0.15s; white-space: nowrap; }
    .btn:hover { background: var(--accent-hover); }
    .btn.secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
    .btn.secondary:hover { background: var(--border); }
    .btn-row { display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1rem; align-items: center; flex-wrap: wrap; }
    .unsaved-badge { font-size: 0.8rem; color: var(--yellow); font-weight: 600; display: none; align-items: center; gap: 0.4rem; margin-right: auto; }
    .unsaved-badge.visible { display: flex; }
    .toast { position: fixed; bottom: 2rem; right: 2rem; color: white; padding: 0.75rem 1.25rem; border-radius: 8px; display: none; font-size: 0.9rem; font-weight: 600; box-shadow: 0 4px 20px rgba(0,0,0,0.3); z-index: 999; background: var(--green); }
    .toast.error { background: var(--red); }
    .tag { display: inline-block; background: var(--accent); color: white; border-radius: 4px; padding: 0.1rem 0.4rem; font-size: 0.78rem; cursor: pointer; margin: 0.15rem; font-family: monospace; }
    .tag:hover { background: var(--accent-hover); }
    .multi-select { display: flex; flex-direction: column; gap: 0.4rem; max-height: 180px; overflow-y: auto; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 0.5rem; }
    .multi-select label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.88rem; color: var(--text); cursor: pointer; padding: 0.3rem 0.4rem; border-radius: 6px; font-weight: normal; }
    .multi-select label:hover { background: var(--surface2); }
    .multi-select input[type=checkbox] { width: auto; accent-color: var(--accent); }
    .log-list { font-family: monospace; font-size: 0.82rem; line-height: 1.7; padding: 1rem; display: flex; flex-direction: column; gap: 0.15rem; min-height: 120px; }
    .log-line { padding: 0.2rem 0.5rem; border-radius: 4px; color: var(--muted); }
    .log-line:hover { background: var(--surface2); color: var(--text); }
  </style>
</head>
<body>

<div class="sidebar">
  <h1>🐟 Floppy</h1>
  <div class="nav-item active" onclick="showPage('welcome', this)">👋 Welcome & Goodbye</div>
  <div class="nav-item" onclick="showPage('roles', this)">🔖 Join Role</div>
  <div class="nav-item" onclick="showPage('tickets', this)">🎫 Tickets</div>
  <div class="nav-item" onclick="showPage('membercount', this)">📊 Member Count</div>
  <div class="nav-item" onclick="showPage('levelling', this)">⬆️ Levelling</div>
  <div class="nav-item" onclick="showPage('commands', this)">💬 Commands</div>
  <div class="nav-item" onclick="showPage('audit', this)">📋 Audit Log</div>
  <div class="nav-item" onclick="showPage('logs', this)">🖥️ Logs</div>
</div>

<div class="main">

  <!-- WELCOME PAGE -->
  <div class="page active" id="page-welcome">
    <div class="page-header">
      <div class="page-header-left">
        <h2>👋 Welcome & Goodbye</h2>
        <p class="subtitle">Configure join and leave messages for your server.</p>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Welcome Message</div>
      <div class="field">
        <label>Channel</label>
        <select id="welcome_channel" onchange="markDirty()"><option value="">— none —</option></select>
      </div>
      <div class="field">
        <label>Message</label>
        <input id="welcome_message" placeholder="Welcome {mention} to {server}! 🎉" oninput="updatePreview('welcome'); markDirty()">
        <div class="hint">
          Click to insert:
          <span class="tag" onclick="insert('welcome_message','{mention}')"><code>{mention}</code></span>
          <span class="tag" onclick="insert('welcome_message','{name}')"><code>{name}</code></span>
          <span class="tag" onclick="insert('welcome_message','{server}')"><code>{server}</code></span>
        </div>
        <div class="preview" id="preview-welcome"></div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Goodbye Message</div>
      <div class="field">
        <label>Channel</label>
        <select id="goodbye_channel" onchange="markDirty()"><option value="">— none —</option></select>
      </div>
      <div class="field">
        <label>Message</label>
        <input id="goodbye_message" placeholder="Goodbye {mention}, we'll miss you! 👋" oninput="updatePreview('goodbye'); markDirty()">
        <div class="hint">
          Click to insert:
          <span class="tag" onclick="insert('goodbye_message','{mention}')"><code>{mention}</code></span>
          <span class="tag" onclick="insert('goodbye_message','{name}')"><code>{name}</code></span>
          <span class="tag" onclick="insert('goodbye_message','{server}')"><code>{server}</code></span>
        </div>
        <div class="preview" id="preview-goodbye"></div>
      </div>
    </div>
    <div class="btn-row">
      <span class="unsaved-badge" id="unsaved-welcome">⚠️ Unsaved changes</span>
      <button class="btn" onclick="save()">Save Changes</button>
    </div>
  </div>

  <!-- ROLES PAGE -->
  <div class="page" id="page-roles">
    <div class="page-header">
      <div class="page-header-left">
        <h2>🔖 Join Role</h2>
        <p class="subtitle">Automatically assign a role when someone joins.</p>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Auto Role</div>
      <div class="field">
        <label>Role to assign on join</label>
        <select id="join_role" onchange="markDirty()"><option value="">— none —</option></select>
      </div>
      <div class="field">
        <label>Role to swap in at level 10</label>
        <select id="trust_role" onchange="markDirty()"><option value="">— none —</option></select>
        <div class="hint">When a member reaches level 10, the join role is removed and this role is added.</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">🍯 Honeypot</div>
      <div class="field">
        <label>Decoy channel</label>
        <select id="honeypot_channel" onchange="markDirty()"><option value="">— none —</option></select>
        <div class="hint">A channel real members have no reason to post in. The instant anyone sends a message here, they're isolated and everything they posted today anywhere in the server is deleted. Set this channel's permissions so it's hidden from your isolation role, and lock down other channels for that role too.</div>
      </div>
      <div class="field">
        <label>Isolation role to apply</label>
        <select id="honeypot_role" onchange="markDirty()"><option value="">— none —</option></select>
      </div>
      <div class="field">
        <label>Purge window (hours)</label>
        <input id="honeypot_purge_hours" type="number" min="0.01" step="0.25" oninput="markDirty()">
        <div class="hint">How far back to delete the triggering member's messages, server-wide. Default 1.</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">✅ Verify</div>
      <div class="field">
        <label>Verify channel</label>
        <select id="verify_channel" onchange="markDirty()"><option value="">— none —</option></select>
        <div class="hint">Anyone who sends a message here is instantly granted the role below.</div>
      </div>
      <div class="field">
        <label>Role to grant</label>
        <select id="verify_role" onchange="markDirty()"><option value="">— none —</option></select>
      </div>
    </div>
    <div class="btn-row">
      <span class="unsaved-badge" id="unsaved-roles">⚠️ Unsaved changes</span>
      <button class="btn" onclick="save()">Save Changes</button>
    </div>
  </div>

  <!-- TICKETS PAGE -->
  <div class="page" id="page-tickets">
    <div class="page-header">
      <div class="page-header-left">
        <h2>🎫 Tickets</h2>
        <p class="subtitle">Configure the ticket system.</p>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Panel</div>
      <div class="row">
        <div class="field">
          <label>Panel Channel</label>
          <select id="ticket_channel" onchange="markDirty()"><option value="">— none —</option></select>
          <div class="hint">Where the "Open a Ticket" button is posted.</div>
        </div>
        <div class="field">
          <label>Ticket Category</label>
          <select id="ticket_category" onchange="markDirty()"><option value="">— none —</option></select>
          <div class="hint">New ticket channels go under this category.</div>
        </div>
        <div class="field">
          <label>Closed Ticket Category</label>
          <select id="ticket_closed_category" onchange="markDirty()"><option value="">— none —</option></select>
          <div class="hint">Closed tickets are moved here instead of deleted. Leave blank to delete on close.</div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Staff Roles</div>
      <div class="field">
        <label>Roles that can manage tickets</label>
        <div class="multi-select" id="ticket_staff_roles"></div>
        <div class="hint">Selected roles can see, claim, and close tickets.</div>
      </div>
    </div>
    <div class="btn-row">
      <span class="unsaved-badge" id="unsaved-tickets">⚠️ Unsaved changes</span>
      <button class="btn secondary" onclick="repostPanel()">🔄 Update Panel</button>
      <button class="btn" onclick="save()">Save Changes</button>
    </div>
  </div>

  <!-- MEMBER COUNT PAGE -->
  <div class="page" id="page-membercount">
    <div class="page-header">
      <div class="page-header-left">
        <h2>📊 Member Count</h2>
        <p class="subtitle">Display a live member count in a voice channel name.</p>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Counter Channel</div>
      <div class="field">
        <label>Channel to rename</label>
        <select id="member_count_channel" onchange="markDirty()"><option value="">— none —</option></select>
        <div class="hint">Pick any voice channel. Its name will be updated automatically whenever someone joins or leaves (and every 10 minutes).</div>
      </div>
      <div class="field">
        <label>Name template</label>
        <input id="member_count_label" placeholder="👥 Members: {count}" oninput="updateMemberCountPreview(); markDirty()">
        <div class="hint">
          Click to insert: <span class="tag" onclick="insertMemberCount('{count}')"><code>{count}</code></span>
        </div>
        <div class="preview" id="preview-membercount"></div>
      </div>
    </div>
    <div class="btn-row">
      <span class="unsaved-badge" id="unsaved-membercount">⚠️ Unsaved changes</span>
      <button class="btn" onclick="save()">Save Changes</button>
    </div>
  </div>

  <!-- LEVELLING PAGE -->
  <div class="page" id="page-levelling">
    <div class="page-header">
      <div class="page-header-left">
        <h2>⬆️ Levelling</h2>
        <p class="subtitle">Reward active members with XP and level-up announcements.</p>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Level-up Channel</div>
      <div class="field">
        <label>Announce level-ups in</label>
        <select id="level_channel" onchange="markDirty()"><option value="">— same channel as the message —</option></select>
        <div class="hint">When a member levels up, the announcement is sent here. If left blank it posts in whatever channel the message was sent in.</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">How it works</div>
      <p style="font-size:0.88rem;color:var(--muted);line-height:1.6;">
        Members earn <strong style="color:var(--text)">15–25 XP</strong> per message (once per minute, to prevent spam).
        Level thresholds follow the formula <code style="background:var(--surface2);padding:0.1rem 0.4rem;border-radius:4px;">5n² + 50n + 100</code> — so level 1 needs 155 XP, level 2 needs 310 XP, and so on.
        XP is stored in <code style="background:var(--surface2);padding:0.1rem 0.4rem;border-radius:4px;">#floppystorage</code> on Discord — no files or databases on the bot.
        XP is wiped automatically when a member leaves. Members can check their progress with <code style="background:var(--surface2);padding:0.1rem 0.4rem;border-radius:4px;">/rank</code>.
      </p>
    </div>
    <div class="btn-row">
      <span class="unsaved-badge" id="unsaved-levelling">⚠️ Unsaved changes</span>
      <button class="btn" onclick="save()">Save Changes</button>
    </div>
  </div>

  <!-- COMMANDS PAGE -->
  <div class="page" id="page-commands">
    <div class="page-header">
      <div class="page-header-left">
        <h2>💬 Commands</h2>
        <p class="subtitle">Restrict bot commands to a specific channel.</p>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Commands Channel</div>
      <div class="field">
        <label>Restrict commands to</label>
        <select id="commands_channel" onchange="markDirty()"><option value="">— no restriction —</option></select>
        <div class="hint">When set, users can only run bot commands in this channel. Admins are exempt. Any plain message sent here by a non-admin will be automatically deleted.</div>
      </div>
    </div>
    <div class="btn-row">
      <span class="unsaved-badge" id="unsaved-commands">⚠️ Unsaved changes</span>
      <button class="btn" onclick="save()">Save Changes</button>
    </div>
  </div>

  <!-- AUDIT PAGE -->
  <div class="page" id="page-audit">
    <div class="page-header">
      <div class="page-header-left">
        <h2>📋 Audit Log</h2>
        <p class="subtitle">Log all server activity to a channel.</p>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Log Channel</div>
      <div class="field">
        <label>Send logs to</label>
        <select id="audit_log_channel" onchange="markDirty()"><option value="">— none —</option></select>
      </div>
      <div class="hint" style="margin-top:0.5rem;">Logs: message edits/deletes, joins/leaves, role changes, nickname changes, bans, channel changes, voice activity, invites.</div>
    </div>
    <div class="btn-row">
      <span class="unsaved-badge" id="unsaved-audit">⚠️ Unsaved changes</span>
      <button class="btn" onclick="save()">Save Changes</button>
    </div>
  </div>

  <!-- LOGS PAGE -->
  <div class="page" id="page-logs">
    <div class="page-header">
      <div class="page-header-left">
        <h2>🖥️ Bot Logs</h2>
        <p class="subtitle">Last 25 bot events. Auto-refreshes every 5 seconds.</p>
      </div>
    </div>
    <div class="card" style="padding:0;overflow:hidden;">
      <div class="log-list" id="log-list"></div>
    </div>
  </div>

</div>

<div class="toast" id="toast"></div>

<script>
  let guildData = { channels: [], roles: [], categories: [], voice_channels: [] };
  let cfg = {};
  let currentPage = 'welcome';

  function showPage(name, el) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('page-' + name).classList.add('active');
    el.classList.add('active');
    currentPage = name;
  }

  function markDirty() {
    const badge = document.getElementById('unsaved-' + currentPage);
    if (badge) badge.classList.add('visible');
  }

  function clearDirty() {
    document.querySelectorAll('.unsaved-badge').forEach(b => b.classList.remove('visible'));
  }

  function toast(msg, error = false) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast' + (error ? ' error' : '');
    el.style.display = 'block';
    setTimeout(() => el.style.display = 'none', 2500);
  }

  function populateSelect(id, options, savedValue) {
    const el = document.getElementById(id);
    el.innerHTML = '<option value="">— none —</option>';
    for (const o of options) {
      const opt = document.createElement('option');
      opt.value = o.id;
      opt.textContent = o.name;
      if (String(savedValue) === String(o.id)) opt.selected = true;
      el.appendChild(opt);
    }
  }

  function populateStaffRoles(roles, savedValues) {
    const container = document.getElementById('ticket_staff_roles');
    container.innerHTML = '';
    const saved = (savedValues || []).map(String);
    for (const role of roles) {
      const label = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = role.id;
      cb.checked = saved.includes(String(role.id));
      cb.onchange = markDirty;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(role.name));
      container.appendChild(label);
    }
  }

  function updateMemberCountPreview() {
    const msg = document.getElementById('member_count_label').value || '👥 Members: {count}';
    document.getElementById('preview-membercount').textContent = msg.replace(/{count}/g, '42');
  }

  function insertMemberCount(text) {
    const el = document.getElementById('member_count_label');
    const start = el.selectionStart, end = el.selectionEnd;
    el.value = el.value.substring(0, start) + text + el.value.substring(end);
    el.selectionStart = el.selectionEnd = start + text.length;
    el.focus();
    updateMemberCountPreview();
    markDirty();
  }

  function insert(fieldId, text) {
    const el = document.getElementById(fieldId);
    const start = el.selectionStart, end = el.selectionEnd;
    el.value = el.value.substring(0, start) + text + el.value.substring(end);
    el.selectionStart = el.selectionEnd = start + text.length;
    el.focus();
    updatePreview(fieldId.includes('welcome') ? 'welcome' : 'goodbye');
    markDirty();
  }

  function updatePreview(type) {
    const msg = document.getElementById(type + '_message').value;
    document.getElementById('preview-' + type).textContent = msg
      .replace(/{mention}/g, '@YourName')
      .replace(/{name}/g, 'YourName')
      .replace(/{server}/g, 'Social Space');
  }

  async function fetchGuild() {
    try {
      const res = await fetch('/api/guild');
      const data = await res.json();
      if (!data.channels.length) return; // bot not ready yet, try again later
      guildData = data;
      populateSelect('welcome_channel', guildData.channels, cfg.welcome_channel);
      populateSelect('goodbye_channel', guildData.channels, cfg.goodbye_channel);
      populateSelect('audit_log_channel', guildData.channels, cfg.audit_log_channel);
      populateSelect('ticket_channel', guildData.channels, cfg.ticket_channel);
      populateSelect('ticket_category', guildData.categories, cfg.ticket_category);
      populateSelect('ticket_closed_category', guildData.categories, cfg.ticket_closed_category);
      populateSelect('join_role', guildData.roles, cfg.join_role);
      populateSelect('trust_role', guildData.roles, cfg.trust_role);
      populateSelect('honeypot_channel', guildData.channels, cfg.honeypot_channel);
      populateSelect('honeypot_role', guildData.roles, cfg.honeypot_role);
      populateSelect('verify_channel', guildData.channels, cfg.verify_channel);
      populateSelect('verify_role', guildData.roles, cfg.verify_role);
      populateSelect('member_count_channel', guildData.voice_channels, cfg.member_count_channel);
      populateSelect('level_channel', guildData.channels, cfg.level_channel);
      populateSelect('commands_channel', guildData.channels, cfg.commands_channel);
      populateStaffRoles(guildData.roles, cfg.ticket_staff_roles);
    } catch(e) {}
  }

  async function fetchLogs() {
    try {
      const res = await fetch('/api/logs');
      const data = await res.json();
      const list = document.getElementById('log-list');
      list.innerHTML = data.logs.length
        ? data.logs.map(l => `<div class="log-line">${l}</div>`).join('')
        : '<div class="log-line">No logs yet...</div>';
    } catch(e) {}
  }

  async function load() {
    const res = await fetch('/api/config');
    cfg = await res.json();
    document.getElementById('welcome_message').value = cfg.welcome_message ?? '';
    document.getElementById('goodbye_message').value = cfg.goodbye_message ?? '';
    document.getElementById('member_count_label').value = cfg.member_count_label ?? '';
    document.getElementById('honeypot_purge_hours').value = cfg.honeypot_purge_hours ?? 1;
    updatePreview('welcome');
    updatePreview('goodbye');
    updateMemberCountPreview();
    await fetchGuild();
  }

  async function save() {
    const staffRoles = [...document.querySelectorAll('#ticket_staff_roles input:checked')].map(cb => cb.value);
    const body = {
      welcome_channel: document.getElementById('welcome_channel').value || null,
      welcome_message: document.getElementById('welcome_message').value || null,
      goodbye_channel: document.getElementById('goodbye_channel').value || null,
      goodbye_message: document.getElementById('goodbye_message').value || null,
      join_role: document.getElementById('join_role').value || null,
      trust_role: document.getElementById('trust_role').value || null,
      honeypot_channel: document.getElementById('honeypot_channel').value || null,
      honeypot_role: document.getElementById('honeypot_role').value || null,
      honeypot_purge_hours: parseFloat(document.getElementById('honeypot_purge_hours').value) || 1,
      verify_channel: document.getElementById('verify_channel').value || null,
      verify_role: document.getElementById('verify_role').value || null,
      audit_log_channel: document.getElementById('audit_log_channel').value || null,
      ticket_channel: document.getElementById('ticket_channel').value || null,
      ticket_category: document.getElementById('ticket_category').value || null,
      ticket_closed_category: document.getElementById('ticket_closed_category').value || null,
      ticket_staff_roles: staffRoles,
      member_count_channel: document.getElementById('member_count_channel').value || null,
      member_count_label: document.getElementById('member_count_label').value || null,
      level_channel: document.getElementById('level_channel').value || null,
      commands_channel: document.getElementById('commands_channel').value || null,
    };
    const res = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (res.ok) {
      cfg = { ...cfg, ...body };
      clearDirty();
      if (body.member_count_channel) {
        await fetch('/api/sync-member-count', { method: 'POST' });
      }
      toast('✅ Saved!');
    } else {
      toast('❌ Save failed', true);
    }
  }

  async function repostPanel() {
    const res = await fetch('/api/repost-panel', { method: 'POST' });
    if (res.ok) toast('✅ Panel updated!');
    else toast('❌ Failed — is the bot online?', true);
  }

  load();
  fetchLogs();
  setInterval(fetchGuild, 30000);
  setInterval(fetchLogs, 5000);
</script>
</body>
</html>
"""

@app.route("/")
async def index():
    return await render_template_string(PAGE)

@app.route("/api/guild")
async def guild():
    bot = state.bot
    if not bot or not bot.guilds:
        return jsonify({"channels": [], "roles": [], "categories": []})
    g = bot.guilds[0]
    channels = [{"id": str(c.id), "name": f"# {c.name}"} for c in sorted(g.text_channels, key=lambda c: c.position)]
    voice_channels = [{"id": str(c.id), "name": f"🔊 {c.name}"} for c in sorted(g.voice_channels, key=lambda c: c.position)]
    roles = [{"id": str(r.id), "name": r.name} for r in sorted(g.roles, key=lambda r: -r.position) if r.name != "@everyone"]
    categories = [{"id": str(c.id), "name": c.name} for c in sorted(g.categories, key=lambda c: c.position)]
    return jsonify({"channels": channels, "roles": roles, "categories": categories, "voice_channels": voice_channels})

@app.route("/api/config", methods=["GET"])
async def get_config():
    return jsonify(config.load())

@app.route("/api/config", methods=["POST"])
async def set_config():
    data = await request.get_json()
    cfg = config.load()
    old_trust_role = cfg.get("trust_role")
    cfg.update(data)
    config.save(cfg)

    # If the level-10 role was changed, apply it to existing level 10+ members now.
    if data.get("trust_role") and data.get("trust_role") != old_trust_role:
        bot = state.bot
        if bot and bot.guilds:
            import levelling
            for guild in bot.guilds:
                await levelling.backfill_trust_roles(guild)

    return jsonify({"ok": True})

@app.route("/api/sync-member-count", methods=["POST"])
async def sync_member_count():
    bot = state.bot
    if not bot or not bot.guilds:
        return jsonify({"ok": False, "error": "Bot not ready"}), 503
    for guild in bot.guilds:
        await bot.update_member_count(guild)
    return jsonify({"ok": True})

@app.route("/api/logs")
async def get_logs():
    return jsonify({"logs": list(state.logs)})

@app.route("/api/repost-panel", methods=["POST"])
async def repost_panel():
    from tickets import post_ticket_panel
    bot = state.bot
    if not bot:
        return jsonify({"ok": False, "error": "Bot not ready"}), 503
    await post_ticket_panel(bot)
    return jsonify({"ok": True})