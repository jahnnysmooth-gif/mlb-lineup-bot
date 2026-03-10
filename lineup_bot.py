import os
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "posted_lineups.json"
LINEUPS_URL = "https://www.rotowire.com/baseball/daily-lineups.php"
ET = ZoneInfo("America/New_York")

VALID_TEAMS = {
    "ARI", "ATL", "BAL", "BOS", "CHC", "CWS", "CIN", "CLE", "COL", "DET",
    "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "ATH",
    "PHI", "PIT", "SD", "SF", "SEA", "STL", "TB", "TEX", "TOR", "WSH"
}

POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
BAD_VALUES = {
    "RotoWire", "Alerts", "alert", "Menu", "Confirmed Lineup",
    "L", "R", "S", "ERA", "MLB", "Baseball"
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch_page():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(LINEUPS_URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def clean(text):
    return " ".join(text.split()).strip()


def get_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    lines = [clean(x) for x in soup.get_text("\n").splitlines()]
    return [x for x in lines if x]


def extract_lineup_after_confirmed(lines, start_idx):
    lineup = []
    i = start_idx + 1

    while i < len(lines) and len(lineup) < 9:
        token = lines[i]

        if token in POSITIONS and i + 1 < len(lines):
            player = lines[i + 1]

            if (
                player
                and player not in BAD_VALUES
                and player not in POSITIONS
                and "$" not in player
                and "ERA" not in player
                and player not in VALID_TEAMS
            ):
                lineup.append({"name": player, "pos": token})
                i += 2
                continue

        i += 1

    return lineup


def parse_lineups(lines):
    confirmed_indexes = [i for i, line in enumerate(lines) if line == "Confirmed Lineup"]
    parsed = []

    for idx in confirmed_indexes:
        window_before = lines[max(0, idx - 40):idx]

        teams_in_window = [x for x in window_before if x in VALID_TEAMS]
        if not teams_in_window:
            continue

        team = teams_in_window[-1]
        lineup = extract_lineup_after_confirmed(lines, idx)

        if len(lineup) == 9:
            parsed.append({
                "team": team,
                "lineup": lineup
            })

    deduped = {}
    for item in parsed:
        deduped[item["team"]] = item

    return list(deduped.values())


def format_roundup_message(new_items):
    lines = []
    lines.append("📋 **STARTING LINEUPS UPDATE**")
    lines.append("")

    for item in sorted(new_items, key=lambda x: x["team"]):
        team = item["team"]
        lineup = item["lineup"]

        lines.append(f"**{team}**")
        short_line = ", ".join([player["name"] for player in lineup[:9]])
        lines.append(short_line)
        lines.append("")

    return "\n".join(lines).strip()


def post_to_discord(content):
    chunks = []

    while len(content) > 1900:
        split_at = content.rfind("\n\n", 0, 1900)
        if split_at == -1:
            split_at = content.rfind("\n", 0, 1900)
        if split_at == -1:
            split_at = 1900

        chunks.append(content[:split_at])
        content = content[split_at:].lstrip()

    if content:
        chunks.append(content)

    for chunk in chunks:
        while True:
            r = requests.post(WEBHOOK_URL, json={"content": chunk}, timeout=20)

            if r.status_code == 429:
                retry_after = 2
                try:
                    retry_after = float(r.json().get("retry_after", 2))
                except Exception:
                    pass

                print(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue

            r.raise_for_status()
            break


def main():
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set")

    print("Fetching Rotowire lineups page...")
    html = fetch_page()
    lines = get_lines(html)
    parsed = parse_lineups(lines)

    print(f"Parsed {len(parsed)} valid lineups")

    today_key = datetime.now(ET).strftime("%Y-%m-%d")
    state = load_state()

    if state.get("date") != today_key:
        state = {"date": today_key, "posted": {}}

    posted = state.get("posted", {})
    new_items = []

    for item in parsed:
        team = item["team"]
        if posted.get(team):
            print(f"Skipping {team}, already posted today")
            continue

        new_items.append(item)
        posted[team] = True

    state["posted"] = posted
    save_state(state)

    if not new_items:
        print("No new confirmed lineups to post.")
        return

    msg = format_roundup_message(new_items)
    print(f"Posting roundup for {len(new_items)} new lineups")
    post_to_discord(msg)


if __name__ == "__main__":
    main()
