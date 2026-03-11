import os
import json
import time
import hashlib
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

POSITIONS = {"C", "1B", "2B", "2B/SS", "3B", "SS", "LF", "CF", "RF", "DH"}

BAD_VALUES = {
    "RotoWire", "Alerts", "alert", "Menu", "Confirmed Lineup",
    "L", "R", "S", "ERA", "MLB", "Baseball"
}


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[BOT] Failed to load state file: {e}")
    return {}


def save_state(state):
    tmp_file = STATE_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_file, STATE_FILE)


def fetch_page():
    headers = {"User-Agent": "Mozilla/5.0"}
    print("[BOT] Fetching RotoWire page...")
    r = requests.get(LINEUPS_URL, headers=headers, timeout=30)
    print(f"[BOT] RotoWire response: {r.status_code}")
    r.raise_for_status()
    return r.text


def clean(text):
    return " ".join(text.split()).strip()


def get_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    lines = [clean(x) for x in soup.get_text("\n").splitlines()]
    return [x for x in lines if x]


def extract_lineup(lines, start_idx):
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
                lineup.append({
                    "name": player,
                    "pos": token
                })
                i += 2
                continue

        i += 1

    return lineup


def find_pitcher(lines, start_idx):
    window = lines[max(0, start_idx - 25):start_idx]

    for text in reversed(window):
        if (
            text not in BAD_VALUES
            and text not in VALID_TEAMS
            and "ERA" not in text
            and len(text.split()) >= 2
            and len(text.split()) <= 4
        ):
            return text

    return None


def parse_lineups(lines):
    confirmed_indexes = [i for i, x in enumerate(lines) if x == "Confirmed Lineup"]

    parsed = []

    for idx in confirmed_indexes:
        window_before = lines[max(0, idx - 40):idx]
        teams = [x for x in window_before if x in VALID_TEAMS]

        if not teams:
            continue

        team = teams[-1]
        lineup = extract_lineup(lines, idx)

        if len(lineup) != 9:
            continue

        pitcher = find_pitcher(lines, idx)

        parsed.append({
            "team": team,
            "lineup": lineup,
            "pitcher": pitcher
        })

    deduped = {}
    for item in parsed:
        deduped[item["team"]] = item

    return list(deduped.values())


def lineup_fingerprint(item):
    raw = json.dumps(item, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def format_team_message(item, is_update=False):
    team = item["team"]
    lineup = item["lineup"]
    pitcher = item.get("pitcher")
    date_str = datetime.now(ET).strftime("%B %d, %Y")

    if is_update:
        header = f"🔄 **UPDATED {team} STARTING LINEUP**"
    else:
        header = f"📋 **{team} STARTING LINEUP**"

    lines = []
    lines.append(header)
    lines.append(f"**Date:** {date_str}")
    lines.append("")

    if pitcher:
        lines.append(f"**SP:** {pitcher}")
        lines.append("")

    for i, player in enumerate(lineup, start=1):
        pos = player.get("pos", "")
        name = player.get("name", "")
        lines.append(f"**{i}.** {name} — {pos}")

    return "\n".join(lines).strip()


def post_with_retries(content):
    for attempt in range(6):
        try:
            r = requests.post(
                WEBHOOK_URL,
                json={"content": content},
                timeout=20
            )

            if r.status_code == 429:
                retry_after = 2
                try:
                    retry_after = float(r.json().get("retry_after", 2))
                except Exception:
                    pass

                print(f"[BOT] Rate limited. Retry {attempt + 1}/6 in {retry_after}s")
                time.sleep(retry_after)
                continue

            print(f"[BOT] Discord response: {r.status_code}")
            r.raise_for_status()
            return

        except requests.RequestException as e:
            print(f"[BOT] Discord post error on attempt {attempt + 1}/6: {e}")
            if attempt < 5:
                time.sleep(3)
            else:
                raise

    raise RuntimeError("Failed to post to Discord after retries")


def main():
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set")

    print(f"[BOT] Run started at {datetime.now(ET).strftime('%Y-%m-%d %I:%M:%S %p %Z')}")

    today_key = datetime.now(ET).strftime("%Y-%m-%d")
    state = load_state()

    if state.get("date") != today_key:
        print(f"[BOT] New day detected. Resetting state for {today_key}")
        state = {"date": today_key, "posted": {}}

    posted = state.get("posted", {})

    html = fetch_page()
    lines = get_lines(html)
    parsed = parse_lineups(lines)

    print(f"[BOT] Parsed {len(parsed)} valid lineups")

    if parsed:
        print(f"[BOT] Teams parsed: {', '.join(sorted(x['team'] for x in parsed))}")

    new_items = []

    for item in parsed:
        team = item["team"]
        fingerprint = lineup_fingerprint(item)
        old_fingerprint = posted.get(team)

        if old_fingerprint == fingerprint:
            print(f"[BOT] Skipping {team} (already posted, unchanged)")
            continue

        print(f"[BOT] New or updated lineup found for {team}")
        new_items.append(item)

    if not new_items:
        print("[BOT] No new lineups")
        return

    posted_this_run = 0

    for item in sorted(new_items, key=lambda x: x["team"]):
        team = item["team"]
        is_update = team in posted
        msg = format_team_message(item, is_update=is_update)

        try:
            print(f"[BOT] Posting lineup for {team}")
            post_with_retries(msg)

            posted[team] = lineup_fingerprint(item)
            state["posted"] = posted
            save_state(state)

            posted_this_run += 1
            time.sleep(1.25)

        except Exception as e:
            print(f"[BOT] Failed posting {team}: {e}")

    print(f"[BOT] Finished. Posted {posted_this_run} team lineups.")


if __name__ == "__main__":
    main()
