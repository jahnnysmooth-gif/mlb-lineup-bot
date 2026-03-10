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

POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
BAD_TEAM_VALUES = {
    "RotoWire", "Alerts", "alert", "Menu", "L", "R", "S",
    "ET", "ERA", "Confirmed Lineup"
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


def get_text_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    lines = [clean(x) for x in soup.get_text("\n").splitlines()]
    return [x for x in lines if x]


def is_team_code(text):
    return text.isupper() and 2 <= len(text) <= 3 and text not in BAD_TEAM_VALUES


def is_pitcher_name(text):
    parts = text.split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if text in BAD_TEAM_VALUES:
        return False
    if "ERA" in text or "$" in text:
        return False
    if is_team_code(text):
        return False
    return True


def extract_lineup(lines, start_idx):
    lineup = []
    i = start_idx + 1

    while i < len(lines) and len(lineup) < 9:
        if lines[i] in POSITIONS:
            pos = lines[i]
            if i + 1 < len(lines):
                player = lines[i + 1]
                if (
                    player
                    and player not in BAD_TEAM_VALUES
                    and "$" not in player
                    and "ERA" not in player
                    and player not in POSITIONS
                    and not is_team_code(player)
                ):
                    lineup.append({"name": player, "pos": pos})
                    i += 2
                    continue
        i += 1

    return lineup


def find_team_and_pitcher(lines, confirmed_idx, lineup_number_in_game):
    # Look backward from "Confirmed Lineup"
    # Current Rotowire page shows team codes before pitcher name, then Confirmed Lineup. :contentReference[oaicite:1]{index=1}
    nearby = lines[max(0, confirmed_idx - 60):confirmed_idx]

    team_codes = [x for x in nearby if is_team_code(x)]
    pitcher_names = [x for x in nearby if is_pitcher_name(x)]

    team = None
    pitcher = None

    # For each game block there are usually 2 team codes and 2 pitchers
    if len(team_codes) >= 2:
        if lineup_number_in_game == 0:
            team = team_codes[-2]
        else:
            team = team_codes[-1]
    elif len(team_codes) == 1:
        team = team_codes[-1]

    if len(pitcher_names) >= 2:
        if lineup_number_in_game == 0:
            pitcher = pitcher_names[-2]
        else:
            pitcher = pitcher_names[-1]
    elif len(pitcher_names) == 1:
        pitcher = pitcher_names[-1]

    return team, pitcher


def parse_lineups(lines):
    confirmed_indexes = [i for i, line in enumerate(lines) if line == "Confirmed Lineup"]

    parsed = []
    last_game_anchor = -999
    lineup_number_in_game = 0

    for idx in confirmed_indexes:
        # If these two confirmed lineups are close together, treat as same game
        if idx - last_game_anchor > 80:
            lineup_number_in_game = 0
        else:
            lineup_number_in_game += 1

        team, pitcher = find_team_and_pitcher(lines, idx, lineup_number_in_game)
        lineup = extract_lineup(lines, idx)

        if team and len(lineup) == 9:
            parsed.append({
                "team": team,
                "pitcher": pitcher,
                "lineup": lineup
            })

        last_game_anchor = idx

    # Deduplicate by team
    deduped = {}
    for item in parsed:
        deduped[item["team"]] = item

    return list(deduped.values())


def format_message(team, lineup, pitcher=None):
    lines = []
    lines.append("📋 **LINEUP POSTED**")
    lines.append("")
    lines.append(f"**{team}**")

    for i, player in enumerate(lineup, start=1):
        lines.append(f"{i}. {player['name']} — {player['pos']}")

    if pitcher:
        lines.append("")
        lines.append(f"SP: {pitcher}")

    return "\n".join(lines)


def post_to_discord(content):
    while True:
        r = requests.post(WEBHOOK_URL, json={"content": content}, timeout=20)

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
    lines = get_text_lines(html)
    parsed = parse_lineups(lines)

    print(f"Parsed {len(parsed)} valid lineups")

    state = load_state()
    today_key = datetime.now(ET).strftime("%Y-%m-%d")

    if state.get("date") != today_key:
        state = {"date": today_key, "posted": {}}

    posted = state.get("posted", {})
    posted_any = False

    for item in parsed:
        team = item["team"]

        if posted.get(team):
            print(f"Skipping {team}, already posted")
            continue

        print(f"Posting lineup for {team}")
        msg = format_message(team, item["lineup"], item.get("pitcher"))
        post_to_discord(msg)
        posted[team] = True
        posted_any = True

    state["posted"] = posted
    save_state(state)

    if not posted_any:
        print("No new confirmed lineups to post.")


if __name__ == "__main__":
    main()
