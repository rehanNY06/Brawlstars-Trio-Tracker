import requests
import json
import os
import time
import threading
from flask import Flask, jsonify
from flask import render_template

CONFIG_FILE = "config.json"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(
            f"{CONFIG_FILE} not found. Copy config.example.json to {CONFIG_FILE} "
            "and fill in your Brawl Stars API key and trio tags."
        )
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


config = load_config()
API_KEY = config["brawlstars_api_key"]
TRIO_TAGS = config["trio_tags"]
PLAYER_TAG = TRIO_TAGS[0] 


def get_player(tag, api_key):
    encoded_tag = tag.replace("#", "%23")
    url = f"https://api.brawlstars.com/v1/players/{encoded_tag}"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()


def get_summary(player_data):
    name = player_data["name"]
    trophies = player_data["trophies"]

    brawlers = player_data["brawlers"]
    top_brawler = brawlers[0]
    for brawler in brawlers:
        if brawler["trophies"] > top_brawler["trophies"]:
            top_brawler = brawler

    return {
        "name": name,
        "trophies": trophies,
        "top_brawler_name": top_brawler["name"],
        "top_brawler_id": top_brawler["id"],
        "top_brawler_trophies": top_brawler["trophies"],
        "top_brawler_highest_trophies": top_brawler["highestTrophies"],
    }


def get_battlelog(tag, api_key):
    encoded_tag = tag.replace("#", "%23")
    url = f"https://api.brawlstars.com/v1/players/{encoded_tag}/battlelog"
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["items"]


def find_your_team(battle, your_tag):
    teams = battle["battle"].get("teams")
    if not teams:
        return None

    for team in teams:
        team_tags = {player["tag"] for player in team}
        if your_tag in team_tags:
            return team
    return None


def is_trio_match(battle, trio_tags):
    your_tag = next(iter(trio_tags))
    team = find_your_team(battle, your_tag)
    if team is None:
        return False

    team_tags = {player["tag"] for player in team}
    return trio_tags.issubset(team_tags)


def get_trios_stats(battles, trio_tags):
    wins = 0
    losses = 0
    star_player_counts = {tag: 0 for tag in trio_tags}

    for battle in battles:
        if not is_trio_match(battle, trio_tags):
            continue

        result = battle["battle"]["result"]
        if result == "victory":
            wins += 1
        elif result == "defeat":
            losses += 1

        star_player = battle["battle"].get("starPlayer")
        if star_player is not None and star_player["tag"] in star_player_counts:
            star_player_counts[star_player["tag"]] += 1

    return {
        "wins": wins,
        "losses": losses,
        "star_player_counts": star_player_counts,
    }


STATE_FILE = "trio_state.json"


def load_state(trio_tags):
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)

    return {
        "last_battle_time": None,
        "wins": 0,
        "losses": 0,
        "star_player_counts": {tag: 0 for tag in trio_tags},
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def update_trio_stats(state, battles, trio_tags):
    battles_sorted = sorted(battles, key=lambda b: b["battleTime"])

    if "history" not in state:
        state["history"] = []

    for battle in battles_sorted:
        if state["last_battle_time"] and battle["battleTime"] <= state["last_battle_time"]:
            continue

        state["last_battle_time"] = battle["battleTime"]

        if not is_trio_match(battle, trio_tags):
            continue

        result = battle["battle"]["result"]
        if result == "victory":
            state["wins"] += 1
        elif result == "defeat":
            state["losses"] += 1

        star_player = battle["battle"].get("starPlayer")
        if star_player is not None and star_player["tag"] in state["star_player_counts"]:
            state["star_player_counts"][star_player["tag"]] += 1

        team = find_your_team(battle, next(iter(trio_tags)))
        brawlers_played = {player["tag"]: {"name": player["brawler"]["name"], "id": player["brawler"]["id"]} for player in team}

        state["history"].append({
            "battle_time": battle["battleTime"],
            "result": result,
            "mode": battle["battle"]["mode"],
            "brawlers": brawlers_played,
            "star_player_tag": star_player["tag"] if star_player else None,
        })
    return state


def poll_once(trio_tags):
    state = load_state(trio_tags)
    battles = get_battlelog(PLAYER_TAG, API_KEY)
    state = update_trio_stats(state, battles, trio_tags)
    save_state(state)
    return state


def get_trio_profiles(trio_tags, api_key):
    profiles = {}
    for tag in trio_tags:
        player_data = get_player(tag, api_key)
        profiles[tag] = get_summary(player_data)
    return profiles


def fetch_gamemode_icons():
    try:
        response = requests.get("https://api.brawlapi.com/v1/gamemodes", timeout=10)
        response.raise_for_status()
        modes = response.json()["list"]
        return {mode["scHash"]: mode["imageUrl"] for mode in modes}
    except Exception as e:
        print(f"Warning: couldn't fetch gamemode icons ({e}). Continuing without them.")
        return {}


app = Flask(__name__)
state_lock = threading.Lock()
shared_state = {
    "gamemode_icons": fetch_gamemode_icons(),
    "trio_tags": TRIO_TAGS,
}


def background_poller(trio_tags, interval_seconds=30):
    while True:
        try:
            new_state = poll_once(trio_tags)
            profiles = get_trio_profiles(trio_tags, API_KEY)
            with state_lock:
                shared_state.update(new_state)
                shared_state["profiles"] = profiles
        except Exception as e:
            print(f"Error during poll: {e}")

        time.sleep(interval_seconds)


@app.route("/api/state")
def api_state():
    with state_lock:
        return jsonify(shared_state)


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


if __name__ == "__main__":
    trio_tags = set(TRIO_TAGS)

    poller_thread = threading.Thread(
        target=background_poller,
        args=(trio_tags,),
        daemon=True
    )
    poller_thread.start()

    app.run(host="0.0.0.0", port=5000)
