import os
import json
import time
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "posted_lineups.json"
ET = ZoneInfo("America/New_York")

ROTOWIRE_API = "https://www.rotowire.com/daily/tables/mlb-lineups.php"

TEAM_COLORS = {
    "ARI":0xA71930,"ATL":0xCE1141,"BAL":0xDF4601,"BOS":0xBD3039,"CHC":0x0E3386,
    "CWS":0x27251F,"CIN":0xC6011F,"CLE":0xE31937,"COL":0x33006F,"DET":0x0C2340,
    "HOU":0xEB6E1F,"KC":0x004687,"LAA":0xBA0021,"LAD":0x005A9C,"MIA":0x00A3E0,
    "MIL":0x12284B,"MIN":0x002B5C,"NYM":0x002D72,"NYY":0x0C2340,"ATH":0x003831,
    "PHI":0xE81828,"PIT":0xFDB827,"SD":0x2F241D,"SF":0xFD5A1E,"SEA":0x005C5C,
    "STL":0xC41E3A,"TB":0x092C5C,"TEX":0x003278,"TOR":0x134A8E,"WSH":0xAB0003
}

TEAM_LOGOS = {
"ARI":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/ARI.svg",
"ATL":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/ATL.svg",
"BAL":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/BAL.svg",
"BOS":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/BOS.svg",
"CHC":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/CHC.svg",
"CWS":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/CWS.svg",
"CIN":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/CIN.svg",
"CLE":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/CLE.svg",
"COL":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/COL.svg",
"DET":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/DET.svg",
"HOU":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/HOU.svg",
"KC":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/KC.svg",
"LAA":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/LAA.svg",
"LAD":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/LAD.svg",
"MIA":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/MIA.svg",
"MIL":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/MIL.svg",
"MIN":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/MIN.svg",
"NYM":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/NYM.svg",
"NYY":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/NYY.svg",
"ATH":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/OAK.svg",
"PHI":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/PHI.svg",
"PIT":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/PIT.svg",
"SD":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/SD.svg",
"SF":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/SF.svg",
"SEA":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/SEA.svg",
"STL":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/STL.svg",
"TB":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/TB.svg",
"TEX":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/TEX.svg",
"TOR":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/TOR.svg",
"WSH":"https://raw.githubusercontent.com/mlb-logos/mlb-logos/main/WSH.svg"
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE,"w") as f:
        json.dump(state,f,indent=2)


def fetch_rotowire_lineups():

    try:
        r=requests.get(ROTOWIRE_API,timeout=20)
        r.raise_for_status()
        data=r.json()
    except Exception as e:
        print(f"[BOT] API error: {e}")
        return []

    parsed=[]

    for game in data:

        away=game["away_team"]
        home=game["home_team"]

        matchup=f"{away} @ {home}"

        for side in ["away","home"]:

            team=game[f"{side}_team"]

            players=game.get(f"{side}_lineup",[])
            lineup=[]

            for p in players:

                lineup.append({
                    "name":p["name"],
                    "pos":p["position"]
                })

            parsed.append({
                "team":team,
                "matchup":matchup,
                "game_time":game.get("time_et"),
                "ballpark":game.get("park"),
                "weather":game.get("weather"),
                "rain":game.get("rain_percentage"),
                "lineup":lineup,
                "pitcher":game.get(f"{side}_pitcher"),
                "lineup_type":"Confirmed Lineup" if game.get("confirmed") else "Expected Lineup"
            })

    return parsed


def lineup_fingerprint(item):
    raw=json.dumps(item,sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def build_embed(item,is_update=False):

    team=item["team"]
    lineup=item["lineup"]

    matchup=item.get("matchup")
    game_time=item.get("game_time")
    ballpark=item.get("ballpark")
    weather=item.get("weather")
    rain=item.get("rain")
    pitcher=item.get("pitcher")

    lineup_type=item.get("lineup_type")

    date_str=datetime.now(ET).strftime("%B %d, %Y")

    if lineup_type=="Expected Lineup":
        title=f"👀 ⚾ {team} Expected Lineup"
    elif is_update:
        title=f"🔄 ⚾ {team} Lineup Updated"
    else:
        title=f"⚾ {team} Confirmed Lineup"

    lines=[
        f"**Matchup:** {matchup}",
        f"**Date:** {date_str}",
    ]

    if game_time:
        lines.append(f"**Game Time:** {game_time}")

    if ballpark:
        lines.append(f"**Ballpark:** {ballpark}")

    if weather:
        lines.append(f"**Weather:** {weather}")

    if rain:
        lines.append(f"**Rain Risk:** {rain}%")

    lines.append("")

    if pitcher:
        lines.append(f"**SP:** {pitcher}")
        lines.append("")

    for i,p in enumerate(lineup,start=1):
        lines.append(f"**{i}.** {p['name']} — {p['pos']}")

    embed={
        "title":title,
        "description":"\n".join(lines),
        "color":TEAM_COLORS.get(team,0x5865F2),
        "timestamp":datetime.now(ET).isoformat(),
        "footer":{"text":"Old ESPN Fantasy Baseball Boards"}
    }

    logo=TEAM_LOGOS.get(team)
    if logo:
        embed["thumbnail"]={"url":logo}

    return embed


def post_embed(embed):

    payload={"embeds":[embed]}

    while True:

        r=requests.post(WEBHOOK_URL,json=payload)

        if r.status_code==429:
            retry=r.json().get("retry_after",2)
            time.sleep(retry)
            continue

        r.raise_for_status()
        break


def run_once():

    state=load_state()
    posted=state.get("posted",{})

    parsed=fetch_rotowire_lineups()

    print(f"[BOT] Parsed {len(parsed)} lineups")

    for item in parsed:

        key=f"{item['matchup']}|{item['team']}"
        fingerprint=lineup_fingerprint(item)

        if posted.get(key)==fingerprint:
            continue

        embed=build_embed(item,is_update=key in posted)

        print(f"[BOT] Posting {key}")

        post_embed(embed)

        posted[key]=fingerprint

        save_state({"posted":posted})

        time.sleep(1)


def main():

    print("[BOT] Worker started")

    while True:

        try:
            run_once()
        except Exception as e:
            print("[BOT] Error:",e)

        print("[BOT] Sleeping 300 seconds")

        time.sleep(300)


if __name__=="__main__":
    main()
