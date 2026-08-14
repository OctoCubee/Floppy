import json
import os

CONFIG_FILE = os.path.join(os.environ.get("DATA_DIR", "."), "config.json")

DEFAULTS = {
    "welcome_channel": None,
    "welcome_message": "Welcome {mention} to {server}! 🎉",
    "goodbye_channel": None,
    "goodbye_message": "Goodbye {mention}, we'll miss you! 👋",
    # Accounts newer than this are automatically removed when they join.
    "new_account_max_age_hours": 24,
    # Supported values: "kick" or "ban".
    "new_account_action": "kick",
    "join_role": None,
    "trust_role": None,
    "audit_log_channel": None,
    "ticket_channel": None,
    "ticket_category": None,
    "ticket_closed_category": None,
    "ticket_staff_roles": [],
    "ticket_panel_message_id": None,
    "member_count_channel": None,
    "member_count_label": "👥 Members: {count}",
    "level_channel": None,
    "commands_channel": None,
    "honeypot_channel": None,
    "honeypot_role": None,
    "honeypot_attachment_thread": None,
    # NOTE: XP data is stored in Discord (#floppystorage), not here.
}

def load():
    if not os.path.exists(CONFIG_FILE):
        save(DEFAULTS.copy())
        return DEFAULTS.copy()
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
    for k, v in DEFAULTS.items():
        if k not in data:
            data[k] = v
    return data

def save(data: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)