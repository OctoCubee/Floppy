from quart import Quart, Response, jsonify, request
import state
import config

app = Quart(__name__)

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Floppy Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      color-scheme: dark;
      --bg: #17181c; --panel: #1e2025; --raised: #26282e; --hover: #2d3037;
      --border: #2f323a; --border-strong: #41454f;
      --text: #e8e9ed; --muted: #9a9fab; --faint: #6c7280;
      --accent: #6d7cff; --accent-hover: #8290ff; --accent-soft: rgba(109,124,255,.14);
      --green: #3ec28f; --red: #ef5b5b; --amber: #f0b44c;
      --radius: 10px;
    }
    @media (prefers-color-scheme: light) {
      :root {
        color-scheme: light;
        --bg: #f4f5f7; --panel: #ffffff; --raised: #f0f1f4; --hover: #e7e9ee;
        --border: #e1e3e8; --border-strong: #c9ccd4;
        --text: #1b1d22; --muted: #5d6270; --faint: #8b909c;
        --accent: #4f5ef0; --accent-hover: #3f4ed8; --accent-soft: rgba(79,94,240,.1);
      }
    }
    html { scroll-behavior: smooth; }
    body { font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; font-size: 15px; line-height: 1.45; background: var(--bg); color: var(--text); min-height: 100vh; }
    button, input, select { font: inherit; color: inherit; }
    :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

    /* ---- layout ---- */
    .shell { display: grid; grid-template-columns: 248px minmax(0, 1fr); min-height: 100vh; }
    .sidebar { position: sticky; top: 0; height: 100vh; background: var(--panel); border-right: 1px solid var(--border); padding: 1.25rem .75rem; display: flex; flex-direction: column; overflow-y: auto; }
    .brand { display: flex; align-items: center; gap: .65rem; padding: 0 .5rem 1.25rem; font-weight: 700; font-size: 1.1rem; }
    .brand-mark { width: 32px; height: 32px; border-radius: 9px; background: var(--accent); color: #fff; display: grid; place-items: center; font-size: 1rem; }
    .nav-group { margin-bottom: 1rem; }
    .nav-label { font-size: .7rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--faint); padding: 0 .6rem .35rem; }
    .nav-item { display: flex; align-items: center; gap: .6rem; width: 100%; padding: .5rem .6rem; border: 0; background: none; border-radius: 7px; color: var(--muted); cursor: pointer; text-align: left; font-size: .92rem; }
    .nav-item:hover { background: var(--hover); color: var(--text); }
    .nav-item[aria-current="page"] { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
    .nav-item svg { width: 17px; height: 17px; flex: none; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .status { margin-top: auto; padding: .75rem .6rem 0; border-top: 1px solid var(--border); font-size: .82rem; color: var(--muted); display: flex; align-items: center; gap: .55rem; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); flex: none; }
    .dot.on { background: var(--green); box-shadow: 0 0 0 3px rgba(62,194,143,.18); }
    .status-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    .main { padding: 2.25rem 2.5rem 7rem; max-width: 860px; width: 100%; }
    .page { display: none; }
    .page.active { display: block; animation: fade .15s ease; }
    @keyframes fade { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
    .page-head { margin-bottom: 1.5rem; }
    .page-head h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -.01em; }
    .page-head p { color: var(--muted); margin-top: .2rem; }

    /* ---- cards & settings ---- */
    .card { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 1.25rem; }
    .card-head { padding: 1rem 1.25rem; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
    .card-head h2 { font-size: .95rem; font-weight: 600; }
    .card-head p { font-size: .82rem; color: var(--muted); margin-top: .1rem; }
    .setting { display: grid; grid-template-columns: minmax(0, 1fr) minmax(220px, 300px); gap: .5rem 2rem; padding: 1rem 1.25rem; align-items: start; }
    .setting + .setting { border-top: 1px solid var(--border); }
    .setting.stack { grid-template-columns: 1fr; }
    .setting-title { font-weight: 550; font-size: .93rem; }
    .setting-desc { font-size: .83rem; color: var(--muted); margin-top: .15rem; }

    input[type=text], input[type=number], select {
      width: 100%; padding: .55rem .75rem; background: var(--bg); border: 1px solid var(--border-strong); border-radius: 8px; transition: border-color .12s, box-shadow .12s;
    }
    input:hover, select:hover { border-color: var(--faint); }
    input:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
    select { appearance: none; padding-right: 2.1rem; cursor: pointer;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239a9fab' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
      background-repeat: no-repeat; background-position: right .75rem center; }
    select option { background: var(--panel); color: var(--text); }
    .unit { display: flex; align-items: center; gap: .6rem; color: var(--muted); font-size: .85rem; }
    .unit input { max-width: 110px; }

    /* ---- message editor ---- */
    .tokens { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; margin-top: .55rem; font-size: .8rem; color: var(--muted); }
    .token { border: 1px solid var(--border-strong); background: var(--raised); color: var(--text); border-radius: 6px; padding: .15rem .5rem; cursor: pointer; font-family: ui-monospace, Consolas, monospace; font-size: .78rem; }
    .token:hover { border-color: var(--accent); color: var(--accent); }
    .discord { margin-top: .85rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: .8rem 1rem; display: flex; gap: .8rem; }
    .discord .av { width: 38px; height: 38px; border-radius: 50%; background: var(--accent); color: #fff; display: grid; place-items: center; font-weight: 700; flex: none; }
    .discord .who { font-weight: 600; font-size: .92rem; }
    .discord .badge { background: var(--accent); color: #fff; font-size: .62rem; font-weight: 700; padding: .05rem .3rem; border-radius: 3px; margin-left: .35rem; vertical-align: 1px; }
    .discord .body { font-size: .92rem; overflow-wrap: anywhere; min-height: 1.3em; }
    .mention { background: var(--accent-soft); color: var(--accent); border-radius: 3px; padding: 0 .2rem; }
    .preview-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--faint); margin-top: .85rem; }

    /* ---- multi picker ---- */
    .picker { border: 1px solid var(--border-strong); border-radius: 8px; background: var(--bg); overflow: hidden; }
    .picker-search { border: 0 !important; border-bottom: 1px solid var(--border) !important; border-radius: 0 !important; box-shadow: none !important; }
    .picker-list { max-height: 190px; overflow-y: auto; padding: .25rem; }
    .picker-list label { display: flex; align-items: center; gap: .6rem; padding: .4rem .55rem; border-radius: 6px; cursor: pointer; font-size: .9rem; }
    .picker-list label:hover { background: var(--hover); }
    .picker-list input { accent-color: var(--accent); width: 16px; height: 16px; }
    .picker-foot { font-size: .75rem; color: var(--faint); padding: .35rem .7rem; border-top: 1px solid var(--border); }
    .empty { padding: .75rem; color: var(--faint); font-size: .85rem; }

    /* ---- buttons / misc ---- */
    .btn { border: 1px solid transparent; background: var(--accent); color: #fff; padding: .5rem 1.1rem; border-radius: 8px; font-weight: 600; cursor: pointer; transition: background .12s; white-space: nowrap; }
    .btn:hover:not(:disabled) { background: var(--accent-hover); }
    .btn:disabled { opacity: .45; cursor: not-allowed; }
    .btn.ghost { background: transparent; color: var(--text); border-color: var(--border-strong); }
    .btn.ghost:hover:not(:disabled) { background: var(--hover); }
    .btn.small { padding: .35rem .8rem; font-size: .85rem; }
    code { background: var(--raised); border-radius: 4px; padding: .05rem .35rem; font-size: .85em; }
    .facts { list-style: none; padding: 1rem 1.25rem; display: grid; gap: .6rem; color: var(--muted); font-size: .9rem; }
    .facts strong { color: var(--text); font-weight: 600; }

    .logs { padding: .5rem; font-family: ui-monospace, Consolas, monospace; font-size: .82rem; }
    .log-line { padding: .35rem .6rem; border-radius: 6px; color: var(--muted); overflow-wrap: anywhere; }
    .log-line:nth-child(odd) { background: var(--raised); }

    /* ---- save bar & toast ---- */
    .savebar { position: fixed; left: calc(248px + (100vw - 248px) / 2); bottom: 1.25rem; transform: translate(-50%, 140%); transition: transform .2s ease; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 12px; padding: .6rem .6rem .6rem 1.1rem; display: flex; align-items: center; gap: 1.25rem; box-shadow: 0 10px 40px rgba(0,0,0,.35); z-index: 20; max-width: calc(100vw - 2rem); }
    .savebar.show { transform: translate(-50%, 0); }
    .savebar span { font-size: .9rem; display: flex; align-items: center; gap: .5rem; }
    .savebar .dot { background: var(--amber); }
    .savebar .actions { display: flex; gap: .5rem; }
    .toast { position: fixed; top: 1.25rem; right: 1.25rem; background: var(--panel); border: 1px solid var(--border-strong); border-left: 3px solid var(--green); padding: .7rem 1rem; border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,.35); font-size: .9rem; opacity: 0; transform: translateY(-8px); pointer-events: none; transition: all .18s; z-index: 30; }
    .toast.show { opacity: 1; transform: none; }
    .toast.error { border-left-color: var(--red); }

    /* ---- mobile ---- */
    @media (max-width: 820px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { position: sticky; z-index: 10; height: auto; flex-direction: row; align-items: center; gap: .25rem; padding: .5rem; border-right: 0; border-bottom: 1px solid var(--border); overflow-x: auto; }
      .brand { padding: 0 .5rem 0 .25rem; }
      .brand span:last-child, .nav-label, .status { display: none; }
      .nav-group { display: flex; margin: 0; gap: .15rem; }
      .nav-item { width: auto; white-space: nowrap; }
      .main { padding: 1.25rem 1rem 7rem; }
      .setting { grid-template-columns: 1fr; }
      .savebar { left: 50%; }
    }
  </style>
</head>
<body>
<div class="shell">

  <nav class="sidebar" aria-label="Sections">
    <div class="brand"><span class="brand-mark">F</span><span>Floppy</span></div>

    <div class="nav-group">
      <div class="nav-label">General</div>
      <button class="nav-item" data-page="welcome"><svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>Welcome &amp; goodbye</button>
      <button class="nav-item" data-page="roles"><svg viewBox="0 0 24 24"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/></svg>Roles</button>
    </div>
    <div class="nav-group">
      <div class="nav-label">Moderation</div>
      <button class="nav-item" data-page="honeypot"><svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>Honeypot</button>
      <button class="nav-item" data-page="media"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/></svg>Media only</button>
      <button class="nav-item" data-page="audit"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/></svg>Audit log</button>
    </div>
    <div class="nav-group">
      <div class="nav-label">Features</div>
      <button class="nav-item" data-page="tickets"><svg viewBox="0 0 24 24"><path d="M2 9a3 3 0 0 1 0 6v3a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1v-3a3 3 0 0 1 0-6V6a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1z"/></svg>Tickets</button>
      <button class="nav-item" data-page="levelling"><svg viewBox="0 0 24 24"><path d="m3 17 6-6 4 4 8-8M15 7h6v6"/></svg>Levelling</button>
      <button class="nav-item" data-page="membercount"><svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>Member count</button>
      <button class="nav-item" data-page="commands"><svg viewBox="0 0 24 24"><path d="m4 17 6-6-6-6M12 19h8"/></svg>Commands</button>
    </div>
    <div class="nav-group">
      <div class="nav-label">Bot</div>
      <button class="nav-item" data-page="logs"><svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>Live logs</button>
    </div>

    <div class="status"><span class="dot" id="status-dot"></span><span class="status-text" id="status-text">Connecting…</span></div>
  </nav>

  <main class="main">

    <!-- WELCOME -->
    <section class="page" id="page-welcome">
      <div class="page-head"><h1>Welcome &amp; goodbye</h1><p>Greet new members and say farewell when they leave.</p></div>

      <div class="card">
        <div class="card-head"><div><h2>Welcome message</h2></div></div>
        <div class="setting">
          <div><div class="setting-title">Channel</div><div class="setting-desc">Where the welcome is posted.</div></div>
          <select id="welcome_channel" data-src="channels"></select>
        </div>
        <div class="setting stack">
          <div><div class="setting-title">Message</div></div>
          <div>
            <input type="text" id="welcome_message" data-preview="welcome" placeholder="Welcome {mention} to {server}! 🎉">
            <div class="tokens">Insert
              <button type="button" class="token" data-target="welcome_message" data-token="{mention}">{mention}</button>
              <button type="button" class="token" data-target="welcome_message" data-token="{name}">{name}</button>
              <button type="button" class="token" data-target="welcome_message" data-token="{server}">{server}</button>
            </div>
            <div class="preview-label">Preview</div>
            <div class="discord"><div class="av">F</div><div><div class="who">Floppy<span class="badge">BOT</span></div><div class="body" id="preview-welcome"></div></div></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div><h2>Goodbye message</h2></div></div>
        <div class="setting">
          <div><div class="setting-title">Channel</div><div class="setting-desc">Where the goodbye is posted.</div></div>
          <select id="goodbye_channel" data-src="channels"></select>
        </div>
        <div class="setting stack">
          <div><div class="setting-title">Message</div></div>
          <div>
            <input type="text" id="goodbye_message" data-preview="goodbye" placeholder="Goodbye {mention}, we'll miss you! 👋">
            <div class="tokens">Insert
              <button type="button" class="token" data-target="goodbye_message" data-token="{mention}">{mention}</button>
              <button type="button" class="token" data-target="goodbye_message" data-token="{name}">{name}</button>
              <button type="button" class="token" data-target="goodbye_message" data-token="{server}">{server}</button>
            </div>
            <div class="preview-label">Preview</div>
            <div class="discord"><div class="av">F</div><div><div class="who">Floppy<span class="badge">BOT</span></div><div class="body" id="preview-goodbye"></div></div></div>
          </div>
        </div>
      </div>
    </section>

    <!-- ROLES -->
    <section class="page" id="page-roles">
      <div class="page-head"><h1>Roles</h1><p>Automatic role handling for new and established members.</p></div>
      <div class="card">
        <div class="setting">
          <div><div class="setting-title">Join role</div><div class="setting-desc">Given to everyone as soon as they join.</div></div>
          <select id="join_role" data-src="roles"></select>
        </div>
        <div class="setting">
          <div><div class="setting-title">Level 10 role</div><div class="setting-desc">At level 10 the join role is removed and this role is added instead.</div></div>
          <select id="trust_role" data-src="roles"></select>
        </div>
      </div>
    </section>

    <!-- HONEYPOT -->
    <section class="page" id="page-honeypot">
      <div class="page-head"><h1>Honeypot</h1><p>Catch spam accounts with a channel real members never post in.</p></div>
      <div class="card">
        <div class="setting">
          <div><div class="setting-title">Decoy channel</div><div class="setting-desc">The moment anyone posts here they get the isolation role and their recent messages are deleted. Hide this channel from the isolation role and lock that role out of everything else.</div></div>
          <select id="honeypot_channel" data-src="channels"></select>
        </div>
        <div class="setting">
          <div><div class="setting-title">Isolation role</div><div class="setting-desc">Applied to whoever triggers the honeypot.</div></div>
          <select id="honeypot_role" data-src="roles"></select>
        </div>
        <div class="setting">
          <div><div class="setting-title">Purge window</div><div class="setting-desc">How far back to delete that member's messages, server-wide.</div></div>
          <div class="unit"><input type="number" id="honeypot_purge_hours" min="0.01" step="0.25"> hours</div>
        </div>
      </div>
    </section>

    <!-- MEDIA -->
    <section class="page" id="page-media">
      <div class="page-head"><h1>Media only</h1><p>Keep picture and video channels free of chatter.</p></div>
      <div class="card">
        <div class="setting">
          <div><div class="setting-title">Media channels</div><div class="setting-desc">Every post needs an image or video attached; text alongside it is fine. Text-only messages and GIFs are deleted.</div></div>
          <div class="picker" id="media_channels" data-src="channels"></div>
        </div>
      </div>
    </section>

    <!-- AUDIT -->
    <section class="page" id="page-audit">
      <div class="page-head"><h1>Audit log</h1><p>A record of what happens in your server.</p></div>
      <div class="card">
        <div class="setting">
          <div><div class="setting-title">Log channel</div><div class="setting-desc">Message edits and deletes, joins and leaves, role and nickname changes, bans, channel changes, voice activity and invites.</div></div>
          <select id="audit_log_channel" data-src="channels"></select>
        </div>
      </div>
    </section>

    <!-- TICKETS -->
    <section class="page" id="page-tickets">
      <div class="page-head"><h1>Tickets</h1><p>Private support channels opened with a button.</p></div>
      <div class="card">
        <div class="card-head">
          <div><h2>Panel</h2><p>After changing the panel channel, save and then update the panel.</p></div>
          <button class="btn ghost small" id="repost">Update panel</button>
        </div>
        <div class="setting">
          <div><div class="setting-title">Panel channel</div><div class="setting-desc">Where the “Open a ticket” button lives.</div></div>
          <select id="ticket_channel" data-src="channels"></select>
        </div>
        <div class="setting">
          <div><div class="setting-title">Ticket category</div><div class="setting-desc">New ticket channels are created under this category.</div></div>
          <select id="ticket_category" data-src="categories"></select>
        </div>
        <div class="setting">
          <div><div class="setting-title">Closed category</div><div class="setting-desc">Closed tickets move here. Leave empty to delete them instead.</div></div>
          <select id="ticket_closed_category" data-src="categories"></select>
        </div>
      </div>
      <div class="card">
        <div class="setting">
          <div><div class="setting-title">Staff roles</div><div class="setting-desc">These roles can see, claim and close tickets.</div></div>
          <div class="picker" id="ticket_staff_roles" data-src="roles"></div>
        </div>
      </div>
    </section>

    <!-- LEVELLING -->
    <section class="page" id="page-levelling">
      <div class="page-head"><h1>Levelling</h1><p>Reward active members with XP and level-ups.</p></div>
      <div class="card">
        <div class="setting">
          <div><div class="setting-title">Level-up channel</div><div class="setting-desc">Where level-ups are announced. Empty means the channel the message was sent in.</div></div>
          <select id="level_channel" data-src="channels" data-empty="Same channel as the message"></select>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><div><h2>How it works</h2></div></div>
        <ul class="facts">
          <li><strong>15–25 XP</strong> per message, at most once a minute.</li>
          <li>Each level needs <code>5n² + 50n + 100</code> XP, so level 1 takes 155 and level 2 takes 310.</li>
          <li>XP lives in <code>#floppystorage</code> on Discord; the bot keeps no database.</li>
          <li>XP is wiped when a member leaves. Members check progress with <code>/rank</code>.</li>
        </ul>
      </div>
    </section>

    <!-- MEMBER COUNT -->
    <section class="page" id="page-membercount">
      <div class="page-head"><h1>Member count</h1><p>Show a live member count in a voice channel name.</p></div>
      <div class="card">
        <div class="setting">
          <div><div class="setting-title">Channel to rename</div><div class="setting-desc">Any voice channel. Updated on every join and leave, and every 10 minutes.</div></div>
          <select id="member_count_channel" data-src="voice_channels"></select>
        </div>
        <div class="setting stack">
          <div><div class="setting-title">Name template</div></div>
          <div>
            <input type="text" id="member_count_label" data-preview="membercount" placeholder="👥 Members: {count}">
            <div class="tokens">Insert
              <button type="button" class="token" data-target="member_count_label" data-token="{count}">{count}</button>
            </div>
            <div class="preview-label">Preview</div>
            <div class="discord"><div class="body" id="preview-membercount"></div></div>
          </div>
        </div>
      </div>
    </section>

    <!-- COMMANDS -->
    <section class="page" id="page-commands">
      <div class="page-head"><h1>Commands</h1><p>Keep bot commands out of general chat.</p></div>
      <div class="card">
        <div class="setting">
          <div><div class="setting-title">Commands channel</div><div class="setting-desc">When set, commands only work here and other messages sent here by non-admins are deleted. Admins are exempt.</div></div>
          <select id="commands_channel" data-src="channels" data-empty="No restriction"></select>
        </div>
      </div>
    </section>

    <!-- LOGS -->
    <section class="page" id="page-logs">
      <div class="page-head"><h1>Live logs</h1><p>The bot's last 25 events, refreshed every 5 seconds.</p></div>
      <div class="card"><div class="logs" id="log-list"></div></div>
    </section>

  </main>
</div>

<div class="savebar" id="savebar" role="status">
  <span><i class="dot"></i>You have unsaved changes</span>
  <div class="actions">
    <button class="btn ghost small" id="discard">Discard</button>
    <button class="btn small" id="save">Save changes</button>
  </div>
</div>
<div class="toast" id="toast" role="alert"></div>

<script>
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  const TEXT_FIELDS = ['welcome_message', 'goodbye_message', 'member_count_label'];
  const SELECTS = [...document.querySelectorAll('select[data-src]')];
  const PICKERS = [...document.querySelectorAll('.picker[data-src]')];

  let guildData = { name: '', channels: [], roles: [], categories: [], voice_channels: [] };
  let cfg = {};
  let dirty = false;
  let ready = false;   // guild data loaded; saving earlier would wipe every selection

  /* ---- navigation ---- */
  function showPage(name) {
    if (!$('page-' + name)) name = 'welcome';
    document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + name));
    document.querySelectorAll('.nav-item').forEach(n => {
      if (n.dataset.page === name) n.setAttribute('aria-current', 'page');
      else n.removeAttribute('aria-current');
    });
    history.replaceState(null, '', '#' + name);
    window.scrollTo(0, 0);
  }
  document.querySelectorAll('.nav-item').forEach(n => n.addEventListener('click', () => showPage(n.dataset.page)));

  /* ---- dirty state ---- */
  function setDirty(v) {
    dirty = v;
    $('savebar').classList.toggle('show', v);
  }
  const edited = (e) => { if (e.target.closest('main') && !e.target.classList.contains('picker-search')) setDirty(true); };
  document.addEventListener('input', edited);
  document.addEventListener('change', edited);
  window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

  function toast(msg, error = false) {
    const el = $('toast');
    el.textContent = msg;
    el.className = 'toast show' + (error ? ' error' : '');
    clearTimeout(toast.t);
    toast.t = setTimeout(() => el.classList.remove('show'), 2600);
  }

  /* ---- controls ---- */
  function fillSelect(el, options, saved) {
    const empty = el.dataset.empty || 'None';
    el.innerHTML = `<option value="">${esc(empty)}</option>` +
      options.map(o => `<option value="${esc(o.id)}">${esc(o.name)}</option>`).join('');
    el.value = saved == null ? '' : String(saved);
  }

  function fillPicker(el, options, saved) {
    const selected = new Set((saved || []).map(String));
    el.innerHTML =
      `<input type="text" class="picker-search" placeholder="Search…" aria-label="Search">` +
      `<div class="picker-list">` +
      (options.length ? options.map(o =>
        `<label data-name="${esc(o.name.toLowerCase())}"><input type="checkbox" value="${esc(o.id)}"${selected.has(String(o.id)) ? ' checked' : ''}>${esc(o.name)}</label>`
      ).join('') : '<div class="empty">Nothing to show yet.</div>') +
      `</div><div class="picker-foot"></div>`;
    updatePickerCount(el);
  }

  function updatePickerCount(el) {
    const n = el.querySelectorAll('input[type=checkbox]:checked').length;
    el.querySelector('.picker-foot').textContent = n ? `${n} selected` : 'None selected';
  }

  PICKERS.forEach(el => {
    el.addEventListener('input', (e) => {
      if (e.target.classList.contains('picker-search')) {
        const q = e.target.value.trim().toLowerCase();
        el.querySelectorAll('.picker-list label').forEach(l => { l.hidden = q && !l.dataset.name.includes(q); });
      } else {
        updatePickerCount(el);
      }
    });
  });

  const pickerValues = (id) => [...$(id).querySelectorAll('input[type=checkbox]:checked')].map(cb => cb.value);

  /* ---- message previews ---- */
  function renderPreview(kind) {
    const raw = $(kind === 'membercount' ? 'member_count_label' : kind + '_message').value;
    if (kind === 'membercount') {
      $('preview-membercount').textContent = (raw || '👥 Members: {count}').replace(/{count}/g, '42');
      return;
    }
    const server = guildData.name || 'Your Server';
    $('preview-' + kind).innerHTML = esc(raw)
      .replace(/{mention}/g, '<span class="mention">@YourName</span>')
      .replace(/{name}/g, 'YourName')
      .replace(/{server}/g, esc(server));
  }
  document.querySelectorAll('input[data-preview]').forEach(el =>
    el.addEventListener('input', () => renderPreview(el.dataset.preview)));

  document.addEventListener('click', (e) => {
    const t = e.target.closest('.token');
    if (!t) return;
    const el = $(t.dataset.target), tok = t.dataset.token;
    const s = el.selectionStart ?? el.value.length, en = el.selectionEnd ?? el.value.length;
    el.value = el.value.slice(0, s) + tok + el.value.slice(en);
    el.selectionStart = el.selectionEnd = s + tok.length;
    el.focus();
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });

  /* ---- data ---- */
  function applyConfig() {
    TEXT_FIELDS.forEach(id => { $(id).value = cfg[id] ?? ''; });
    $('honeypot_purge_hours').value = cfg.honeypot_purge_hours ?? 1;
    SELECTS.forEach(el => fillSelect(el, guildData[el.dataset.src], cfg[el.id]));
    PICKERS.forEach(el => fillPicker(el, guildData[el.dataset.src], cfg[el.id]));
    renderPreview('welcome'); renderPreview('goodbye'); renderPreview('membercount');
  }

  function setStatus(online) {
    $('status-dot').classList.toggle('on', online);
    $('status-text').textContent = online ? (guildData.name || 'Bot online') : 'Bot offline';
  }

  async function fetchGuild() {
    try {
      const data = await (await fetch('/api/guild')).json();
      if (!data.channels.length) return setStatus(false);
      const first = !ready;
      guildData = data;
      setStatus(true);
      ready = true;
      $('save').disabled = false;
      if (first || !dirty) applyConfig();   // never overwrite edits in progress
    } catch (e) { setStatus(false); }
  }

  async function fetchLogs() {
    try {
      const data = await (await fetch('/api/logs')).json();
      $('log-list').innerHTML = data.logs.length
        ? data.logs.map(l => `<div class="log-line">${esc(l)}</div>`).join('')
        : '<div class="empty">No events yet.</div>';
    } catch (e) {}
  }

  async function load() {
    cfg = await (await fetch('/api/config')).json();
    applyConfig();
    await fetchGuild();
    setDirty(false);
  }

  async function save() {
    if (!ready) return toast('Bot is not connected yet', true);
    const body = {};
    TEXT_FIELDS.forEach(id => { body[id] = $(id).value || null; });
    SELECTS.forEach(el => { body[el.id] = el.value || null; });
    PICKERS.forEach(el => { body[el.id] = pickerValues(el.id); });
    body.honeypot_purge_hours = parseFloat($('honeypot_purge_hours').value) || 1;

    $('save').disabled = true;
    try {
      const res = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!res.ok) throw new Error();
      cfg = { ...cfg, ...body };
      setDirty(false);
      if (body.member_count_channel) await fetch('/api/sync-member-count', { method: 'POST' });
      toast('Changes saved');
    } catch (e) {
      toast('Save failed', true);
    }
    $('save').disabled = false;
  }

  $('save').addEventListener('click', save);
  $('discard').addEventListener('click', () => { applyConfig(); setDirty(false); });
  $('repost').addEventListener('click', async () => {
    const res = await fetch('/api/repost-panel', { method: 'POST' }).catch(() => null);
    if (res && res.ok) toast('Ticket panel updated');
    else toast('Failed. Is the bot online?', true);
  });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); if (dirty) save(); }
  });

  $('save').disabled = true;
  showPage(location.hash.slice(1) || 'welcome');
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
    return Response(PAGE, mimetype="text/html")

@app.route("/api/guild")
async def guild():
    bot = state.bot
    if not bot or not bot.guilds:
        return jsonify({"name": "", "channels": [], "roles": [], "categories": [], "voice_channels": []})
    g = bot.guilds[0]
    channels = [{"id": str(c.id), "name": f"# {c.name}"} for c in sorted(g.text_channels, key=lambda c: c.position)]
    voice_channels = [{"id": str(c.id), "name": f"🔊 {c.name}"} for c in sorted(g.voice_channels, key=lambda c: c.position)]
    roles = [{"id": str(r.id), "name": r.name} for r in sorted(g.roles, key=lambda r: -r.position) if r.name != "@everyone"]
    categories = [{"id": str(c.id), "name": c.name} for c in sorted(g.categories, key=lambda c: c.position)]
    return jsonify({"name": g.name, "channels": channels, "roles": roles, "categories": categories, "voice_channels": voice_channels})

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