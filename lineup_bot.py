import os
import json
import time
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "posted_lineups.json"
LINEUPS_URL = "https://www.rotowire.com/baseball/daily-lineups.php"
ET = ZoneInfo("America/New_York")

POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}


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


def clean_text(text):
    return " ".join(text.split()).strip()


def extract_lineups_from_text(text):
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    lineups = []
    i = 0

    while i < len(lines):
        if lines[i] != "Confirmed Lineup":
            i += 1
            continue

        # Walk backward to find the most recent probable pitcher line
        # Pattern in current Rotowire page is pitcher name followed by hand / ERA, then Confirmed Lineup. :contentReference[oaicite:1]{index=1}
        team = None
        pitcher = None

        j = i - 1
        while j >= 0 and i - j <= 30:
            candidate = clean_text(lines[j])

            if pitcher is None and candidate not in {"L", "R", "S"} and "ERA" not in candidate:
                # likely pitcher name right before handedness/ERA block
                if 2 <= len(candidate.split()) <= 4 and not re.match(r"^\d", candidate):
                    pitcher = candidate

            # team abbreviation block appears shortly above
            if re.fullmatch(r"[A-Z]{2,3}", candidate):
                team = candidate
                break

            j -= 1

        lineup = []
        k = i + 1

        while k < len(lines) and len(lineup) < 9:
            pos = clean_text(lines[k])

            if pos in POSITIONS:
                if k + 1 < len(lines):
                    name = clean_text(lines[k + 1])

                    # Skip salary lines / handedness lines
                    if (
                        name
                        and not name.startswith("$")
                        and name not in {"L", "R", "S"}
                        and "ERA" not in name
                        and name != "Confirmed Lineup"
                    ):
                        lineup.append({"name": name, "pos": pos})
                        k += 2
                        continue

            k += 1

        if team and len(lineup) == 9:
            lineups.append({
                "team": team,
                "pitcher": pitcher,
                "lineup": lineup
            })

        i = k

    # dedupe by team abbreviation
    deduped = {}
    for item in lineups:
        deduped[item["team"]] = item

    return list(deduped.values())


def format_message(team, lineup, pitcher=None):
    lines = []
    lines.append("📋 **LINEUP POSTED**")
    lines.append("")
    lines.append(f"**{team}**")

    for idx, player in enumerate(lineup, start=1):
        lines.append(f"{idx}. {player['name']} — {player['pos']}")

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

    print("Fetching Rotowire lineups page...")
    html = fetch_page()
    print(f"Fetched {len(html)} characters")

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    parsed_lineups = extract_lineups_from_text(text)

    print(f"Parsed {len(parsed_lineups)} lineups")

    state = load_state()
    today_key = datetime.now(ET).strftime("%Y-%m-%d")

    if state.get("date") != today_key:
        state = {"date": today_key, "posted": {}}

    posted = state.get("posted", {})
    posted_any = False

    for item in parsed_lineups:
        team = item["team"]

        if posted.get(team):
            print(f"Skipping {team}, already posted")
            continue

        msg = format_message(team, item["lineup"], item.get("pitcher"))
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
