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
    "RotoWire", "Alerts", "alert", "Menu", "Confirmed Lineup", "Expected Lineup",
    "L", "R", "S", "ERA", "MLB", "Baseball"
}

TEAM_COLORS = {
    "ARI": 0xA71930, "ATL": 0xCE1141, "BAL": 0xDF4601, "BOS": 0xBD3039,
    "CHC": 0x0E3386, "CWS": 0x27251F, "CIN": 0xC6011F, "CLE": 0xE31937,
    "COL": 0x33006F, "DET": 0x0C2340, "HOU": 0xEB6E1F, "KC": 0x004687,
    "LAA": 0xBA0021, "LAD": 0x005A9C, "MIA": 0x00A3E0, "MIL": 0x12284B,
    "MIN": 0x002B5C, "NYM": 0x002D72, "NYY": 0x0C2340, "ATH": 0x003831,
    "PHI": 0xE81828, "PIT": 0xFDB827, "SD": 0x2F241D, "SF": 0xFD5A1E,
    "SEA": 0x005C5C, "STL": 0xC41E3A, "TB": 0x092C5C, "TEX": 0x003278,
    "TOR": 0x134A8E, "WSH": 0xAB0003
}

TEAM_LOGOS = {
    "ARI": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/ARI.svg",
    "ATL": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/ATL.svg",
    "BAL": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/BAL.svg",
    "BOS": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/BOS.svg",
    "CHC": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/CHC.svg",
    "CWS": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/CWS.svg",
    "CIN": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/CIN.svg",
    "CLE": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/CLE.svg",
    "COL": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/COL.svg",
    "DET": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/DET.svg",
    "HOU": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/HOU.svg",
    "KC": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/KC.svg",
    "LAA": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/LAA.svg",
    "LAD": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/LAD.svg",
    "MIA": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/MIA.svg",
    "MIL": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/MIL.svg",
    "MIN": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/MIN.svg",
    "NYM": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/NYM.svg",
    "NYY": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/NYY.svg",
    "ATH": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/OAK.svg",
    "PHI": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/PHI.svg",
    "PIT": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/PIT.svg",
    "SD": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/SD.svg",
    "SF": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/SF.svg",
    "SEA": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/SEA.svg",
    "STL": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/STL.svg",
    "TB": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/TB.svg",
    "TEX": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/TEX.svg",
    "TOR": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/TOR.svg",
    "WSH": "https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/WSH.svg"
}


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[BOT] Failed to load state: {e}", flush=True)
    return {"posted": {}}


def save_state(state):
    tmp_file = STATE_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_file, STATE_FILE)


def within_run_window():
    now = datetime.now(ET)
    start = now.replace(hour=10, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=0, second=0, microsecond=0)
    return start <= now <= end


def fetch_page():
    print("[BOT] Fetching RotoWire page...", flush=True)
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(LINEUPS_URL, headers=headers, timeout=30)
    print(f"[BOT] RotoWire status: {r.status_code}", flush=True)
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
            and 2 <= len(text.split()) <= 4
        ):
            return text

    return None


def find_game_time(lines, start_idx):
    window = lines[max(0, start_idx - 40):start_idx]

    for text in window:
        upper = text.upper()
        if (
            ("AM" in upper or "PM" in upper)
            and ":" in text
            and len(text) <= 25
            and text not in BAD_VALUES
        ):
            return text

    return None


def find_weather(lines, start_idx):
    window = lines[max(0, start_idx - 40):start_idx]

    for text in window:
        lower = text.lower()
        if any(word in lower for word in ["rain", "wind", "temp", "weather", "mph", "degrees"]):
            return text

    return None


def get_last_two_distinct_teams(window_before):
    found = [x for x in window_before if x in VALID_TEAMS]
    distinct = []

    for team in found:
        if not distinct or distinct[-1] != team:
            distinct.append(team)

    if len(distinct) >= 2:
        return distinct[-2], distinct[-1]

    if len(distinct) == 1:
        return distinct[0], None

    return None, None


def parse_lineups(lines):
    lineup_indexes = [
        (i, lines[i])
        for i in range(len(lines))
        if lines[i] in ("Confirmed Lineup", "Expected Lineup")
    ]

    parsed = []

    for idx, lineup_type in lineup_indexes:
        window_before = lines[max(0, idx - 40):idx]
        away_team, home_team = get_last_two_distinct_teams(window_before)

        if not home_team:
            continue

        team = home_team
        lineup = extract_lineup(lines, idx)

        if len(lineup) != 9:
            continue

        pitcher = find_pitcher(lines, idx)
        game_time = find_game_time(lines, idx)
        weather = find_weather(lines, idx)
        matchup = f"{away_team} @ {home_team}" if away_team and home_team else team

        parsed.append({
            "team": team,
            "matchup": matchup,
            "game_time": game_time,
            "ballpark": None,
            "weather": weather,
            "rain": None,
            "pitcher": pitcher,
            "lineup": lineup,
            "lineup_type": lineup_type
        })

    deduped = {}
    for item in parsed:
        key = f"{item['matchup']}|{item['team']}"
        deduped[key] = item

    return list(deduped.values())


def fingerprint(item):
    raw = json.dumps(item, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_embed(item, is_update=False):
    team = item["team"]
    matchup = item.get("matchup")
    time_et = item.get("game_time")
    park = item.get("ballpark")
    weather = item.get("weather")
    rain = item.get("rain")
    pitcher = item.get("pitcher")
    lineup = item.get("lineup", [])
    lineup_type = item.get("lineup_type")

    date_str = datetime.now(ET).strftime("%B %d, %Y")

    if lineup_type == "Expected Lineup":
        title = f"👀 ⚾ {team} Expected Lineup"
    elif is_update:
        title = f"🔄 ⚾ {team} Lineup Updated"
    else:
        title = f"⚾ {team} Confirmed Lineup"

    lines = [
        f"**Matchup:** {matchup}",
        f"**Date:** {date_str}",
    ]

    if time_et:
        lines.append(f"**Game Time:** {time_et}")

    if park:
        lines.append(f"**Ballpark:** {park}")

    if weather:
        lines.append(f"**Weather:** {weather}")

    if rain not in (None, "", 0, "0"):
        lines.append(f"**Rain Risk:** {rain}%")

    lines.append("")

    if pitcher:
        lines.append(f"**SP:** {pitcher}")
        lines.append("")

    for i, p in enumerate(lineup, start=1):
        name = p.get("name", "")
        pos = p.get("pos", "")
        lines.append(f"**{i}.** {name} — {pos}")

    embed = {
        "title": title,
        "description": "\n".join(lines),
        "color": TEAM_COLORS.get(team, 0x5865F2),
        "timestamp": datetime.now(ET).isoformat(),
        "footer": {"text": "Old ESPN Fantasy Baseball Boards"}
    }

    logo = TEAM_LOGOS.get(team)
    if logo:
        embed["thumbnail"] = {"url": logo}

    return embed


def post_embed(embed):
    for attempt in range(6):
        try:
            r = requests.post(
                f"{WEBHOOK_URL}?wait=true",
                json={"embeds": [embed]},
                timeout=20
            )

            if r.status_code == 429:
                retry_after = 2
                try:
                    retry_after = float(r.json().get("retry_after", 2))
                except Exception:
                    pass
                print(f"[BOT] Rate limited on post. Sleeping {retry_after}s", flush=True)
                time.sleep(retry_after)
                continue

            r.raise_for_status()
            return r.json()["id"]

        except requests.RequestException as e:
            print(f"[BOT] Post error: {e}", flush=True)
            if attempt < 5:
                time.sleep(3)
            else:
                raise

    raise RuntimeError("Failed to post embed after retries")


def edit_embed(message_id, embed):
    url = f"{WEBHOOK_URL}/messages/{message_id}"

    for attempt in range(6):
        try:
            r = requests.patch(
                url,
                json={"embeds": [embed]},
                timeout=20
            )

            if r.status_code == 429:
                retry_after = 2
                try:
                    retry_after = float(r.json().get("retry_after", 2))
                except Exception:
                    pass
                print(f"[BOT] Rate limited on edit. Sleeping {retry_after}s", flush=True)
                time.sleep(retry_after)
                continue

            r.raise_for_status()
            return

        except requests.RequestException as e:
            print(f"[BOT] Edit error: {e}", flush=True)
            if attempt < 5:
                time.sleep(3)
            else:
                raise

    raise RuntimeError("Failed to edit embed after retries")


def run_once():
    state = load_state()
    posted = state.get("posted", {})

    html = fetch_page()
    lines = get_lines(html)
    items = parse_lineups(lines)

    print(f"[BOT] Parsed {len(items)} lineups", flush=True)

    for item in items:
        key = f"{item['matchup']}|{item['team']}"
        fp = fingerprint(item)
        existing = posted.get(key)

        if existing and existing.get("fingerprint") == fp:
            print(f"[BOT] Skipping unchanged {key}", flush=True)
            continue

        embed = build_embed(item, is_update=existing is not None)

        if existing:
            print(f"[BOT] Updating {key}", flush=True)
            edit_embed(existing["message_id"], embed)
            posted[key]["fingerprint"] = fp
        else:
            print(f"[BOT] Posting {key}", flush=True)
            msg_id = post_embed(embed)
            posted[key] = {
                "fingerprint": fp,
                "message_id": msg_id
            }

        save_state(state)
        time.sleep(1)


def main():
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set")

    print("[BOT] Worker started", flush=True)

    while True:
        now_str = datetime.now(ET).strftime("%Y-%m-%d %I:%M:%S %p %Z")
        print(f"[BOT] Run started at {now_str}", flush=True)

        if not within_run_window():
            print("[BOT] Outside run window (10AM–11PM ET). Sleeping 10 minutes.", flush=True)
            time.sleep(600)
            continue

        try:
            run_once()
        except Exception as e:
            print(f"[BOT] Error: {e}", flush=True)

        print("[BOT] Sleeping 300 seconds", flush=True)
        time.sleep(300)


if __name__ == "__main__":
    main()
