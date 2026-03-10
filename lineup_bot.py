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


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch_page():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    r = requests.get(LINEUPS_URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def clean(text):
    return " ".join(text.split()).strip()


def parse_lineups(html):
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    # Find game containers broadly
    games = soup.find_all(["div", "section", "article"])

    parsed = []

    for game in games:
        text = clean(game.get_text(" ", strip=True))
        if not text:
            continue

        if "Confirmed Lineup" not in text:
            continue

        # Try to identify team names from image alt text or visible text
        team_names = []
        for img in game.find_all("img", alt=True):
            alt = clean(img.get("alt", ""))
            if alt and alt not in team_names:
                team_names.append(alt)

        # Fallback: scan likely headings
        if len(team_names) < 2:
            for tag in game.find_all(["h2", "h3", "h4", "span", "div"]):
                t = clean(tag.get_text(" ", strip=True))
                if "(" in t and ")" in t:
                    continue
                if len(t.split()) >= 1 and len(t) < 40 and t not in team_names:
                    team_names.append(t)

        # Extract lineup blocks by looking for "Confirmed Lineup"
        lines = [clean(x) for x in text.split("Confirmed Lineup")]
        if len(lines) < 2:
            continue

        # We only want likely player/position rows
        for idx, after in enumerate(lines[1:3]):
            if idx >= 2:
                break

            team_name = team_names[idx] if idx < len(team_names) else f"Team {idx+1}"

            raw_parts = after.split()
            lineup = []
            pitcher = None

            # Very simple parsing heuristic:
            # look for repeated POS markers after player names
            positions = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
            i = 0
            while i < len(raw_parts) - 1:
                # collect name until a position token
                j = i
                while j < len(raw_parts) and raw_parts[j] not in positions:
                    j += 1

                if j < len(raw_parts) and raw_parts[j] in positions:
                    name = " ".join(raw_parts[i:j]).strip()
                    pos = raw_parts[j]
                    if name and len(lineup) < 9:
                        lineup.append({"name": name, "pos": pos})
                    i = j + 1
                else:
                    break

            # Try to detect probable SP
            if "Lineup" in text and "ERA" in text:
                pitcher = None

            if len(lineup) >= 7:
                parsed.append({
                    "team": team_name,
                    "lineup": lineup[:9],
                    "pitcher": pitcher,
                })

    # Deduplicate by team
    deduped = {}
    for item in parsed:
        deduped[item["team"]] = item

    return list(deduped.values())


def format_message(team_name, lineup, pitcher=None):
    lines = []
    lines.append("📋 **LINEUP POSTED**")
    lines.append("")
    lines.append(f"**{team_name}**")

    for i, player in enumerate(lineup, start=1):
        lines.append(f"{i}. {player['name']} — {player['pos']}")

    if pitcher:
        lines.append("")
        lines.append(f"SP: {pitcher}")

    return "\n".join(lines)


def post_to_discord(content):
    chunks = []

    while len(content) > 1900:
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
                retry_after = 5
                try:
                    retry_after = float(r.json().get("retry_after", 5))
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

    html = fetch_page()
    lineups = parse_lineups(html)
    state = load_state()

    today_key = datetime.now(ET).strftime("%Y-%m-%d")
    if state.get("date") != today_key:
        state = {"date": today_key, "posted": {}}

    posted = state.get("posted", {})

    posted_any = False

    for item in lineups:
        team = item["team"]
        lineup = item["lineup"]

        if team in posted:
            continue

        msg = format_message(team, lineup, item.get("pitcher"))
        print(f"Posting lineup for {team}")
        post_to_discord(msg)
        posted[team] = True
        posted_any = True

    state["posted"] = posted
    save_state(state)

    if not posted_any:
        print("No new confirmed lineups to post.")


if __name__ == "__main__":
    main()