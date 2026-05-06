import random
import json
import os
import asyncio
import html
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, ChatMember
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# CONFIG
# =========================
TOKEN = "8429890592:AAHkdeR_2pGp4EOVTT-lBrYAlBlRjK2tW7Y"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "players.json")
ALLOWED_GROUP_IDS = {-1002664937769, -1003839722848, -1003407035529}
PRIVILEGED_USER_IDS = {1638084297, 7105730933, 6274470012}
MENU_IMAGE_CANDIDATES = ("logo.JPG", "logo.jpg", "logo.png", "menu.jpg", "menu.png")

# In-memory session state
PENDING_CHALLENGES: Dict[Tuple[int, str], Dict[str, Any]] = {}
CHALLENGE_TIMEOUT = 60

ACTIVE_BATTLES: set[int] = set()
BATTLES: Dict[int, Dict[str, Any]] = {}

# Selektions-Zustand für Suimon-Auswahl vor Kampf
PENDING_SELECTION: Dict[int, Dict[str, Any]] = {}

# Text pacing
INTRO_DELAY = 0.8
REPOSITION_COOLDOWN = 3.5
AFK_TIMEOUT = 180
COUNTDOWN_STEP_DELAY = 0.55
ACTION_DELAY = 0.70
HUD_DELAY = 0.45
END_DELAY = 0.8

MAX_LINES_SHOWN = 25
MAX_MESSAGE_CHARS = 3800

# Daily items
DAILY_SUIBALLS = 2
DAILY_SUIBALLS_TOURNAMENT = 10
SUIBALL_CAP = 5
SUIBALL_CAP_TOURNAMENT = 100
MAX_LEVEL = 10
TZ = timezone.utc

# Net Ball
DAILY_NETBALLS = 1
NETBALL_CAP = 3

# Tournament
TOURNAMENT_FILE = os.path.join(BASE_DIR, "tournament.json")

def load_tournament() -> Dict[str, Any]:
    if not os.path.exists(TOURNAMENT_FILE):
        return {"active": False}
    try:
        with open(TOURNAMENT_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"active": False}

def save_tournament(data: Dict[str, Any]) -> None:
    with open(TOURNAMENT_FILE, "w") as f:
        json.dump(data, f, indent=2)

tournament_state: Dict[str, Any] = load_tournament()

def is_tournament_active() -> bool:
    return tournament_state.get("active", False)

def is_xp_boost_active() -> bool:
    expires = tournament_state.get("xp_boost_expires", 0)
    return time.time() < expires

def get_xp_boost_multiplier() -> float:
    return 1.5 if is_xp_boost_active() else 1.0

def get_daily_suiballs() -> int:
    return DAILY_SUIBALLS_TOURNAMENT if is_tournament_active() else DAILY_SUIBALLS

def get_suiball_cap() -> int:
    return SUIBALL_CAP_TOURNAMENT if is_tournament_active() else SUIBALL_CAP

# =========================
# CHAMPS (Starter + Wilde Suimon)
# =========================
CHAMPS: Dict[str, Dict[str, Any]] = {
    "basaurimon": {
        "display": "Basaurimon",
        "type": "nature",
        "base": {"hp": 160, "atk": 24, "def": 11, "spd": 9},
        "moves": [
            {"name": "Vine Whip", "kind": "damage", "power": 48, "acc": 0.95, "text": [
                "whips out something long and flexible — no lube included!",
                "snaps its vine like a dominatrix on a coke binge!",
                "lashes harder than a dealer who wasn't paid on time!",
            ]},
            {"name": "Needle Rain", "kind": "damage_poison", "power": 36, "acc": 0.92,
             "poison_chance": 0.40, "poison_turns": (2, 3), "crit_bonus": 0.08, "text": [
                "opens the vial, smiles, and lets it rain — each drop a promise you'll regret!",
                "launches a volley of needles — not pharmacy grade, not even close!",
                "rains down like a bad batch hitting three people at a party — fast, quiet, and ugly!",
                "pierces through — the needles don't ask permission and neither does the poison!",
                "fires off Needle Rain — somewhere between acupuncture and a funeral!",
            ]},
            {"name": "Leaf Storm", "kind": "damage", "power": 55, "acc": 0.88, "text": [
                "unleashes Leaf Storm — sharper than your dad's comments about your life choices!",
                "summons a vortex nastier than your last intervention!",
                "calls down a tempest that hits harder than a bad batch!",
            ]},
            {"name": "Sleep Spore", "kind": "status_sleep", "power": 0, "acc": 0.75,
             "sleep_turns": (1, 2), "text": [
                "pulls out Cannabis indica — the good stuff, not the street trash!",
                "hotboxes the entire arena with primo kush!",
                "deploys Sleep Spore — straight from the cult's private stash!",
            ]},
        ],
    },
    "suimander": {
        "display": "Suimander",
        "type": "fire",
        "base": {"hp": 154, "atk": 23, "def": 11, "spd": 12},
        "moves": [
            {"name": "Wet Dream", "kind": "status_wet_dream", "power": 0, "acc": 0.90,
             "wet_dream_turns": (3, 4), "text": [
                "slips something into their drink — they don't notice until they piss themselves mid-fight!",
                "whispers something in their ear — whatever it was, they piss themselves instantly!",
                "exhales cult smoke directly into their mouth — they piss themselves before it even kicks in!",
                "doses them with something that has no street name — they piss themselves and forgets why!",
                "reaches into the ritual bag and pulls out the good stuff — opponent pisses themselves on impact!",
            ]},
            {"name": "Flamethrower", "kind": "damage", "power": 55, "acc": 0.90, "text": [
                "blasts a stream hotter than a speedball hitting wrong!",
                "turns up the heat like cooking meth without ventilation!",
                "scorches everything — size matters here and it delivered!",
            ]},
            {"name": "Inferno Claw", "kind": "damage_highcrit", "power": 48, "acc": 0.92,
             "crit_bonus": 0.10, "text": [
                "scratches marks that'll need explaining to your parole officer!",
                "carves deep — leaves marks the cult will be proud of!",
                "rips through like a bad breakup — slow, painful, and very personal!",
            ]},
            {"name": "Will-O-Wisp", "kind": "status_burn", "power": 0, "acc": 0.90,
             "burn_turns": (2, 3), "text": [
                "pulls out a crackpipe and blows burning fumes directly into the opponent's face!",
                "hotboxes the arena with something far worse than tobacco — Will-O-Wisp!",
                "lights up a meth pipe and exhales pure fire — your lungs are not ready!",
                "torches the arena with fumes from a pipe that definitely wasn't bought at a gas station!",
                "exhales something that strips paint, scars lungs, and burns for days — classic Will-O-Wisp!",
            ]},
        ],
    },
    "suiqrtle": {
        "display": "Suiqrtle",
        "type": "water",
        "base": {"hp": 155, "atk": 21, "def": 12, "spd": 8},
        "moves": [
            {"name": "Water Pulse", "kind": "status_confuse", "power": 0, "acc": 0.80,
             "confuse_turns": (1, 2), "confuse_rare_chance": 0.30, "text": [
                "floods the arena with PCP-laced water — someone's going to hurt themselves!",
                "sprays a mist of pure PCP — the opponent doesn't know what year it is anymore!",
                "fires Water Pulse — laced with enough PCP to confuse a horse!",
            ]},
            {"name": "Bubble Beam", "kind": "damage", "power": 46, "acc": 0.93, "text": [
                "releases suspiciously warm bubbles in places you didn't ask for!",
                "fires bubbles like a crackhead blowing kisses — Bubble Beam!",
                "floods the field with something that definitely isn't bathwater!",
            ]},
            {"name": "Aqua Tail", "kind": "damage", "power": 52, "acc": 0.88, "text": [
                "slaps with a wet tail — somewhere between a fetish and a crime!",
                "swings something long and wet in directions that'll require therapy!",
                "whips up water harder than a dealer who wasn't paid!",
            ]},
            {"name": "Hydro Burst", "kind": "damage", "power": 60, "acc": 0.82, "text": [
                "builds pressure like a meth cook with a deadline!",
                "releases fluids with the force of a man who hasn't seen daylight in 3 weeks!",
                "explodes harder than a Breaking Bad finale — Hydro Burst!",
            ]},
        ],
    },
    "poolmon": {
        "display": "Poolmon",
        "type": "water",
        "base": {"hp": 162, "atk": 20, "def": 13, "spd": 8},
        "moves": [
            {"name": "Hydro Pump", "kind": "damage", "power": 60, "acc": 0.82, "text": [
                "blasts a high-pressure water jet — straight out of a fire hose on steroids!",
                "unleashes a deluge that would make a firefighter jealous!",
                "pumps water like a broken dam — no filter!",
            ]},
            {"name": "Hypnose", "kind": "status_confuse", "power": 0, "acc": 0.75,
             "confuse_turns": (1, 2), "confuse_rare_chance": 0.25, "text": [
                "swings a hypno-pendant laced with something unspeakable — the opponent sees double!",
                "whispers sweet nothings… then everything goes sideways!",
                "drops a hypnotic gaze — and the enemy starts arguing with itself!",
            ]},
            {"name": "Bodycheck", "kind": "damage_highcrit", "power": 44, "acc": 0.88,
             "crit_bonus": 0.12, "text": [
                "rams with the full weight of an unlicensed bodybuilder!",
                "crashes in like a freight train with no brakes!",
                "delivers a hit that'll require a spine realignment!",
            ]},
            {"name": "Heuler", "kind": "status_debuff", "power": 0, "acc": 0.92,
             "atk_debuff_pct": 0.30, "debuff_turns": 2, "text": [
                "lets out a howl that saps the opponent's will — their attacks feel like wet noodles!",
                "screams at a frequency that rattles bones and weakens muscles!",
                "wails like a banshee with a hangover — enemy's strength drops!",
            ]},
        ],
    },
    "suideer": {
        "display": "Suideer",
        "type": "fire",
        "base": {"hp": 148, "atk": 26, "def": 10, "spd": 14},
        "moves": [
            {"name": "Flame Burst", "kind": "damage", "power": 50, "acc": 0.92, "text": [
                "erupts in a burst of flame — not quite arson, but close!",
                "explodes with heat like a molotov in a bar fight!",
                "fires a compact fireball that stings like a hornet's nest!",
            ]},
            {"name": "Bambi Blaze", "kind": "damage", "power": 65, "acc": 0.80, "text": [
                "looks innocent, then unleashes a deceptively brutal inferno!",
                "a cute hop, then the world burns!",
                "the deer that sets the forest on fire — literally!",
            ]},
            {"name": "Ember Dash", "kind": "damage", "power": 42, "acc": 0.96, "text": [
                "dashes forward leaving a trail of embers and regret!",
                "a quick, burning charge that catches opponents off guard!",
                "speeds through like a flaming comet — singed and stunned!",
            ]},
            {"name": "Crack Surge", "kind": "damage", "power": 48, "acc": 0.88,
             "spd_boost_chance": 0.25, "spd_boost": 2, "text": [
                "hits the pipe, then hits the enemy — a speed rush made of crack!",
                "inhales a line of something fast and releases it as a blazing surge!",
                "the addict's rush: damage now, speed for later!",
            ]},
        ],
    },
    "jengacide": {
        "display": "Jengacide",
        "type": "nature",
        "base": {"hp": 170, "atk": 22, "def": 14, "spd": 7},
        "moves": [
            {"name": "Blunt Force Trauma", "kind": "damage", "power": 52, "acc": 0.85,
             "def_down_chance": 0.18, "def_down_turns": 2, "text": [
                "slams with the force of a falling Jenga tower — blunt and painful!",
                "clubs the enemy like a brick wrapped in bad decisions!",
                "delivers a hit so heavy the opponent's defense cracks!",
            ]},
            {"name": "Ketamine Quake", "kind": "damage", "power": 44, "acc": 0.82,
             "stun_chance": 0.35, "stun_turns": 1, "text": [
                "stomps the ground so hard the opponent enters a K-hole!",
                "unleashes a tremor that disorients like a horse tranquilizer!",
                "a quake that makes reality wobble — and the enemy might just freeze!",
            ]},
            {"name": "Molly Pressure", "kind": "status_debuff", "power": 0, "acc": 0.90,
             "def_speed_debuff": True, "debuff_turns": 2, "text": [
                "drops a pill of pure pressure — enemy's defenses melt and they slow down!",
                "the love drug hits, but first it cripples!",
                "sends waves of ecstasy that leave the opponent wide open!",
            ]},
            {"name": "Jenga Joint Collapse", "kind": "damage", "power": 70, "acc": 0.75,
             "high_cooldown": 3, "debuff_bonus": True, "text": [
                "lines up the tower, then pulls the critical block — catastrophic collapse!",
                "when already weakened, this finisher hits like a wrecking ball!",
                "the ultimate betrayal: a joint and a Jenga crash combined!",
            ]},
        ],
    },
}

TYPE_EMOJI = {"fire": "🔥", "water": "💧", "nature": "🌿"}
STATUS_EMOJI = {"burn": "🔥", "sleep": "💤", "confuse": "🌀", "poison": "☠️", "wet_dream": "😨"}

CHAMPS_BY_TYPE = {
    "fire": {"strong_against": "nature", "weak_to": "water"},
    "water": {"strong_against": "fire", "weak_to": "nature"},
    "nature": {"strong_against": "water", "weak_to": "fire"},
}

WORLDS = {
    "sedative_abyss": {
        "name": "Sedative Abyss",
        "emoji": "🌊",
        "type": "water",
        "suimon": ["poolmon"],
        "flavor": "dark ocean trenches where the water itself has tranquilizing properties",
        "encounter_chance": 0.30,
    },
    "crackspit_peaks": {
        "name": "Crackspit Peaks",
        "emoji": "🔥",
        "type": "fire",
        "suimon": ["suideer"],
        "flavor": "volcanic mountains where the lava flows like a crack pipe",
        "encounter_chance": 0.30,
    },
    "hash_highlands": {
        "name": "Hash Highlands",
        "emoji": "🌍",
        "type": "nature",
        "suimon": ["jengacide"],
        "flavor": "rolling hills covered in ancient cannabis fields and crumbling Jenga towers",
        "encounter_chance": 0.30,
    },
}

def resolve_menu_image_path() -> Optional[str]:
    for name in MENU_IMAGE_CANDIDATES:
        candidate = os.path.join(BASE_DIR, name)
        if os.path.isfile(candidate):
            return candidate
    return None

def resolve_heal_image_path() -> Optional[str]:
    for name in ("heal.jpg", "heal.JPG", "heal.png"):
        candidate = os.path.join(BASE_DIR, name)
        if os.path.isfile(candidate):
            return candidate
    return None

def is_allowed_chat_id(chat_id: Optional[int]) -> bool:
    return chat_id is not None and chat_id in ALLOWED_GROUP_IDS

async def ensure_allowed_chat(update: Update, context: Optional[ContextTypes.DEFAULT_TYPE] = None) -> bool:
    chat = update.effective_chat
    chat_id = int(chat.id) if chat else None
    if is_allowed_chat_id(chat_id):
        return True
    msg = "🚫 <b>This bot only works in the official Suimon group.</b>"
    if update.callback_query:
        try:
            await update.callback_query.answer("This bot only works in the official Suimon group.", show_alert=True)
        except Exception:
            pass
    elif update.effective_message:
        try:
            await update.effective_message.reply_text(msg, parse_mode="HTML")
        except Exception:
            pass
    return False

async def is_privileged_user(bot, chat_id: int, user_id: int) -> bool:
    if user_id in PRIVILEGED_USER_IDS:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status == ChatMember.OWNER
    except Exception:
        return False

def _parse_target_from_args(chat_id: int, args: List[str]) -> Tuple[Optional[str], int]:
    if not args:
        return None, 1
    first = args[0].strip()
    if not first:
        return None, 1
    if first.isdigit():
        return first, 1
    lookup = first.lstrip('@').lower().replace(' ', '')
    for uid, pdata in players.items():
        if chat_id not in pdata.get('chats', []):
            continue
        username = str(pdata.get('username') or '').lower().lstrip('@')
        name = str(pdata.get('name') or '').lower().replace(' ', '')
        if lookup and (lookup == username or lookup == name):
            return uid, 1
    return None, 1

def _parse_target_and_amount(chat_id: int, args: List[str]) -> Tuple[Optional[str], Optional[int]]:
    target, consumed = _parse_target_from_args(chat_id, args)
    amount: Optional[int] = None
    if len(args) > consumed:
        try:
            amount = int(args[consumed])
        except Exception:
            amount = None
    return target, amount

async def send_menu_photo(message, caption: str, reply_markup: InlineKeyboardMarkup) -> None:
    image_path = resolve_menu_image_path()
    if image_path:
        with open(image_path, "rb") as photo:
            await message.reply_photo(photo=photo, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await message.reply_text(caption, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True)

async def edit_menu_message(query, caption: str, reply_markup: InlineKeyboardMarkup, *, disable_web_page_preview: bool = True) -> None:
    message = query.message
    if message and getattr(message, "photo", None):
        try:
            await query.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            return
        except BadRequest:
            pass
    try:
        await query.edit_message_text(caption, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=disable_web_page_preview)
    except BadRequest:
        try:
            await query.message.reply_text(caption, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=disable_web_page_preview)
        except Exception:
            pass

# =========================
# DATA MODEL (angepasst)
# =========================

def load_players() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_players(players_: Dict[str, Any]) -> None:
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(players_, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

players: Dict[str, Any] = load_players()

# ---------- MIGRATION ALTER DATEN ----------
def migrate_players():
    changed = False
    for uid, p in players.items():
        if "owned_suimon" in p:
            for s in p["owned_suimon"]:
                if s.get("species") in CHAMPS:
                    max_hp = get_stats(s["species"], int(s.get("level", 1)))["hp"]
                    s["hp"] = max(0, min(int(s.get("hp", max_hp)), max_hp))
            for old in ("champ", "champ_nickname", "level", "xp", "hp", "awaiting_nickname", "just_leveled"):
                p.pop(old, None)
            continue

        old_champ = p.get("champ")
        if old_champ not in CHAMPS:
            p["owned_suimon"] = []
            p["active_suimon"] = 0
            for old in ("champ", "champ_nickname", "level", "xp", "hp", "awaiting_nickname", "just_leveled"):
                p.pop(old, None)
            changed = True
            continue

        old_nick = p.get("champ_nickname")
        old_level = int(p.get("level", 1))
        old_xp = int(p.get("xp", 0))
        old_hp = int(p.get("hp") or get_stats(old_champ, old_level)["hp"])
        p["owned_suimon"] = [{
            "species": old_champ,
            "nickname": old_nick,
            "level": old_level,
            "xp": old_xp,
            "hp": old_hp,
            "wins": 0,
            "losses": 0,
        }]
        p["active_suimon"] = 0
        for old in ("champ", "champ_nickname", "level", "xp", "hp", "awaiting_nickname", "just_leveled"):
            p.pop(old, None)
        changed = True

    if changed:
        save_players(players)
        print("[MIGRATION] Alte Spielerdaten wurden konvertiert.")

migrate_players()

# ---------- HELPER FÜR SUIMON ----------
def get_active_suimon_index(user_id: str) -> int:
    p = players.get(user_id, {})
    items = p.get("owned_suimon", [])
    if not items:
        return 0
    return max(0, min(int(p.get("active_suimon", 0)), len(items) - 1))

def get_active_suimon(user_id: str) -> Optional[Dict[str, Any]]:
    p = players.get(user_id, {})
    items = p.get("owned_suimon", [])
    idx = get_active_suimon_index(user_id)
    if 0 <= idx < len(items):
        return items[idx]
    return None

def get_owned_suimon_list(user_id: str) -> List[Dict[str, Any]]:
    return players.get(user_id, {}).get("owned_suimon", [])

def suimon_display_name(s: Dict[str, Any]) -> str:
    nick = s.get("nickname")
    if nick:
        return nick
    return CHAMPS.get(s["species"], {}).get("display", "Unknown")

def suimon_full_name(s: Dict[str, Any]) -> str:
    nick = s.get("nickname")
    base = CHAMPS.get(s["species"], {}).get("display", "Unknown")
    return f"{nick} ({base})" if nick else base

def champ_from_key(key: str) -> Dict[str, Any]:
    return CHAMPS[key]

def display_name(player_id: str, fallback: str = "Player") -> str:
    p = players.get(player_id, {})
    return (p.get("name") or fallback).strip()

def get_champ_nickname(player_id: str) -> Optional[str]:
    s = get_active_suimon(player_id)
    return s.get("nickname") if s else None

def champ_display_for_player(player_id: str, champ_key: Optional[str] = None) -> str:
    s = get_active_suimon(player_id) if champ_key is None else None
    key = champ_key or (s["species"] if s else None)
    if key not in CHAMPS:
        return "Unknown"
    nick = get_champ_nickname(player_id)
    base_name = CHAMPS[key]["display"]
    return nick or base_name

def champ_full_name_for_player(player_id: str, champ_key: Optional[str] = None) -> str:
    s = get_active_suimon(player_id) if champ_key is None else None
    key = champ_key or (s["species"] if s else None)
    if key not in CHAMPS:
        return "Unknown"
    base_name = CHAMPS[key]["display"]
    nick = get_champ_nickname(player_id)
    return f"{nick} ({base_name})" if nick else base_name

def sanitize_champ_nickname(raw: str) -> str:
    allowed = []
    for ch in raw.strip():
        if ch.isalnum() or ch in " _-":
            allowed.append(ch)
    name = " ".join("".join(allowed).split())
    return name[:18].strip()

def has_named_champ(player_id: str) -> bool:
    s = get_active_suimon(player_id)
    return s is not None and bool(s.get("nickname"))

def needs_nickname_prompt(player_id: str) -> bool:
    s = get_active_suimon(player_id)
    return s is not None and not s.get("nickname")

def start_nickname_prompt(player_id: str) -> None:
    players[player_id]["_awaiting_nickname"] = True
    save_players(players)

def clear_nickname_prompt(player_id: str) -> None:
    players[player_id]["_awaiting_nickname"] = False
    save_players(players)

def get_badges_display(user_id: str) -> str:
    badges = players.get(user_id, {}).get("badges", [])
    if not badges:
        return ""
    badge_map = {"cascade": "🌊", "volcano": "🔥", "earth": "🌍"}
    return " ".join(badge_map.get(b, "🏅") for b in badges)

def today_str() -> str:
    return datetime.now(TZ).date().isoformat()

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def hp_bar(current: int, max_hp: int, length: int = 10) -> str:
    mx = max(1, int(max_hp))
    cur = max(0, min(int(current), mx))
    filled = int(round((cur / mx) * length))
    return "█" * filled + "░" * (length - filled)

def format_hp_line(label: str, current: int, max_hp: int) -> str:
    mx = max(1, int(max_hp))
    cur = max(0, min(int(current), mx))
    return f"{label}\nHP {cur:>3}/{mx:<3} [{hp_bar(cur, mx)}]"

def battle_hud(p1_label: str, hp1: int, max1: int, p2_label: str, hp2: int, max2: int) -> str:
    return format_hp_line(p1_label, hp1, max1) + "\n\n" + format_hp_line(p2_label, hp2, max2)

def xp_needed(level: int) -> int:
    level = max(1, min(int(level), MAX_LEVEL))
    _xp_table = {1: 450, 2: 720, 3: 1125, 4: 1710, 5: 2520, 6: 3600, 7: 5085, 8: 7110, 9: 9900}
    return _xp_table.get(level, 9900)

def champ_key_from_input(arg: str) -> Optional[str]:
    if not arg:
        return None
    a = arg.lower().strip()
    aliases = {
        "basaur": "basaurimon", "basaurimon": "basaurimon",
        "suimander": "suimander", "mander": "suimander",
        "suiqrtle": "suiqrtle", "squirtle": "suiqrtle", "qrtle": "suiqrtle",
        "poolmon": "poolmon", "suideer": "suideer", "jengacide": "jengacide",
    }
    return aliases.get(a)

def get_stats(champ_key: str, level: int) -> Dict[str, int]:
    level = max(1, min(int(level), MAX_LEVEL))
    base = champ_from_key(champ_key)["base"]
    hp = int(round(base["hp"] + (level - 1) * 2))
    atk = int(round(base["atk"] + (level - 1) * 0.25))
    df = int(round(base["def"] + (level - 1) * 0.3))
    spd = int(round(base["spd"] + (level - 1) * 1))
    return {"hp": hp, "atk": atk, "def": df, "spd": spd}

def ensure_player(user_id: str, tg_name: str, tg_username: Optional[str] = None) -> None:
    if user_id not in players:
        players[user_id] = {
            "name": tg_name,
            "username": tg_username or "",
            "suiballs": 0,
            "last_daily": None,
            "wins": 0,
            "losses": 0,
            "chats": [],
            "badges": [],
            "net_balls": 0,
            "last_netball_daily": None,
            "owned_suimon": [],
            "active_suimon": 0,
        }
    else:
        if tg_name and players[user_id].get("name") != tg_name:
            players[user_id]["name"] = tg_name
        players[user_id]["username"] = tg_username or players[user_id].get("username", "")
        players[user_id].setdefault("net_balls", 0)
        players[user_id].setdefault("last_netball_daily", None)
        players[user_id].setdefault("owned_suimon", [])
        players[user_id].setdefault("active_suimon", 0)
        players[user_id].setdefault("wins", 0)
        players[user_id].setdefault("losses", 0)

def ensure_daily(user_id: str) -> bool:
    p = players[user_id]
    t = today_str()
    changed = False
    if p.get("last_daily") != t:
        current = int(p.get("suiballs", 0))
        p["suiballs"] = min(get_suiball_cap(), current + get_daily_suiballs())
        p["last_daily"] = t
        changed = True
    if p.get("last_netball_daily") != t:
        p["net_balls"] = min(NETBALL_CAP, int(p.get("net_balls", 0)) + DAILY_NETBALLS)
        p["last_netball_daily"] = t
        changed = True
    return changed

def get_active_suimon_hp(user_id: str) -> int:
    s = get_active_suimon(user_id)
    if not s:
        return 0
    max_hp = get_stats(s["species"], int(s.get("level", 1)))["hp"]
    cur = s.get("hp")
    if cur is None:
        s["hp"] = max_hp
        return max_hp
    return max(0, min(int(cur), max_hp))

def set_active_suimon_hp(user_id: str, new_hp: int) -> None:
    s = get_active_suimon(user_id)
    if s:
        max_hp = get_stats(s["species"], int(s.get("level", 1)))["hp"]
        s["hp"] = max(0, min(int(new_hp), max_hp))

def heal_suimon_by_index(user_id: str, index: int) -> Tuple[int, int]:
    items = players[user_id].get("owned_suimon", [])
    if 0 <= index < len(items):
        s = items[index]
        max_hp = get_stats(s["species"], int(s.get("level", 1)))["hp"]
        s["hp"] = max_hp
        return max_hp, max_hp
    return 0, 0

def grant_xp_to_suimon(suimon: Dict[str, Any], gained: int) -> None:
    if suimon["species"] not in CHAMPS:
        return
    old_level = max(1, min(int(suimon.get("level", 1)), MAX_LEVEL))
    cur_hp = int(suimon.get("hp", 0))
    max_hp = get_stats(suimon["species"], old_level)["hp"]
    suimon["level"] = old_level
    suimon["xp"] = int(suimon.get("xp", 0)) + int(gained)

    leveled = False
    while int(suimon.get("level", 1)) < MAX_LEVEL and suimon["xp"] >= xp_needed(int(suimon.get("level", 1))):
        need = xp_needed(int(suimon.get("level", 1)))
        suimon["xp"] -= need
        suimon["level"] = int(suimon.get("level", 1)) + 1
        leveled = True
        new_max = get_stats(suimon["species"], int(suimon.get("level", 1)))["hp"]
        delta = max(0, new_max - max_hp)
        cur_hp = min(new_max, cur_hp + delta)
        max_hp = new_max
    if int(suimon.get("level", 1)) >= MAX_LEVEL:
        suimon["level"] = MAX_LEVEL
        suimon["xp"] = 0
    suimon["hp"] = max(0, min(cur_hp, max_hp))
    suimon["just_leveled"] = leveled

def award_battle_xp(winner_id: str, loser_id: str, winner_idx: int, loser_idx: int) -> Tuple[int, int]:
    w_suimon = players[winner_id]["owned_suimon"][winner_idx]
    l_suimon = players[loser_id]["owned_suimon"][loser_idx]
    winner_level = int(w_suimon.get("level", 1))
    loser_level = int(l_suimon.get("level", 1))
    level_diff = loser_level - winner_level

    xp_winner = 45
    if level_diff >= 3: xp_winner = 75
    elif level_diff == 2: xp_winner = 65
    elif level_diff == 1: xp_winner = 55
    elif level_diff < 0: xp_winner = 35

    xp_loser = 20
    boost = get_xp_boost_multiplier()
    xp_winner = int(round(xp_winner * boost))
    xp_loser = int(round(xp_loser * boost))
    players[winner_id]["wins"] = int(players[winner_id].get("wins", 0)) + 1
    players[loser_id]["losses"] = int(players[loser_id].get("losses", 0)) + 1
    grant_xp_to_suimon(w_suimon, xp_winner)
    grant_xp_to_suimon(l_suimon, xp_loser)
    return xp_winner, xp_loser

def _remember_chat(user_id: str, chat_id: int) -> None:
    if user_id not in players:
        return
    chats = players[user_id].setdefault("chats", [])
    if chat_id not in chats:
        chats.append(chat_id)

def _eligible_players_in_chat(chat_id: int) -> List[str]:
    out: List[str] = []
    for uid, p in players.items():
        if p.get("owned_suimon") and chat_id in p.get("chats", []):
            out.append(uid)
    return out

def _parse_target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        return str(update.message.reply_to_message.from_user.id)
    if context.args:
        arg = context.args[0].lstrip("@").lower().replace(" ", "")
        for uid, p in players.items():
            name = (p.get("name") or "").lower().replace(" ", "")
            username = (p.get("username") or "").lower().lstrip("@")
            if arg and (arg == name or arg == username):
                return uid
    return None

def ranking_sort_key(uid: str) -> Tuple[int, int, int, int, str, str]:
    pdata = players.get(uid, {})
    wins = int(pdata.get("wins", 0))
    losses = int(pdata.get("losses", 0))
    return (-wins, losses, display_name(uid).lower(), uid)

def get_leaderboard(limit: int = 10) -> List[Tuple[str, str, int, int, int, int]]:
    ranked: List[Tuple[str, str, int, int, int, int]] = []
    for uid, pdata in players.items():
        if not pdata.get("owned_suimon"):
            continue
        ranked.append((
            uid,
            display_name(uid),
            sum(s.get("xp", 0) for s in pdata["owned_suimon"]),
            max(s.get("level", 1) for s in pdata["owned_suimon"]),
            int(pdata.get("wins", 0)),
            int(pdata.get("losses", 0)),
        ))
    ranked.sort(key=lambda row: ranking_sort_key(row[0]))
    return ranked[:limit]

def get_xp_and_rank(user_id: str) -> Tuple[int, Optional[int]]:
    if user_id not in players or not players[user_id].get("owned_suimon"):
        return 0, None
    ordered_ids = sorted(
        [uid for uid, pdata in players.items() if pdata.get("owned_suimon")],
        key=ranking_sort_key,
    )
    xp = sum(s.get("xp", 0) for s in players[user_id]["owned_suimon"])
    try:
        rank = ordered_ids.index(user_id) + 1
    except ValueError:
        rank = None
    return xp, rank

def mention_html(user_id: str, fallback_name: Optional[str] = None) -> str:
    label = html.escape(fallback_name or display_name(user_id) or "Player")
    return f'<a href="tg://user?id={user_id}">{label}</a>'

def build_rankings_text(user_id: Optional[str] = None, limit: int = 10) -> str:
    top_players = get_leaderboard(limit)
    if not top_players:
        return "🏆 <b>SUIMON ARENA — RANKINGS</b>\n\nNo trainers ranked yet. Pick a champ first."

    lines = ["🏆 <b>SUIMON ARENA — RANKINGS</b>", ""]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for rank, (pid, trainer_name, _, _, wins, losses) in enumerate(top_players, 1):
        pdata = players.get(pid, {})
        s = get_active_suimon(pid)
        type_icon = TYPE_EMOJI.get(CHAMPS.get(s["species"], {}).get("type"), "✨") if s else "✨"
        champ_name = html.escape(suimon_full_name(s)) if s else "Unknown"
        total_fights = wins + losses
        winrate = int(round((wins / total_fights) * 100)) if total_fights > 0 else 0
        trainer_link = mention_html(pid, trainer_name)

        if rank <= 3:
            lines.append(f"{medals[rank]} <b>{trainer_link}</b> {type_icon}")
            lines.append(f"<code>{champ_name}</code> • Lv.<b>{s['level'] if s else '?'}</b>")
            lines.append(f"⚔️ <b>{wins}W / {losses}L</b> • <b>{winrate}% WR</b>")
            lines.append("")
        else:
            lines.append(f"{rank}. <b>{trainer_link}</b> • Lv.<b>{s['level'] if s else '?'}</b>")

    if user_id and user_id in players and get_active_suimon(user_id):
        xp, rank = get_xp_and_rank(user_id)
        if rank is not None:
            s = get_active_suimon(user_id)
            lines.extend([
                "",
                "━━━━━━━━━━",
                f"👤 <b>You:</b> #{rank} • Lv.<b>{s['level']}</b> • <b>{xp} XP</b>",
            ])

    return "\n".join(lines)

# =========================
# KAMPF-ENGINE
# =========================

def type_mult(attacker_type: str, defender_type: str) -> Tuple[float, str]:
    if CHAMPS_BY_TYPE[attacker_type]["strong_against"] == defender_type:
        return 1.08, "strong"
    if CHAMPS_BY_TYPE[attacker_type]["weak_to"] == defender_type:
        return 0.95, "weak"
    return 1.0, "neutral"

def pick_first_attacker(spd1: int, spd2: int) -> int:
    if spd1 == spd2:
        return 0 if random.random() < 0.5 else 1
    p = clamp(0.5 + (spd1 - spd2) / 40.0, 0.25, 0.75)
    return 0 if random.random() < p else 1

def level_gap_miss_penalty(attacker_level: int, defender_level: int) -> float:
    gap = attacker_level - defender_level
    if gap <= 0:
        return 0.0
    return min(0.15, gap * 0.03)

def calc_damage(attacker_atk: int, defender_def: int, level: int,
                power: int, type_mult_: float, crit_mult: float,
                defender_level: int = 0) -> int:
    effective_atk = max(1, int(attacker_atk))
    effective_def = max(1, int(defender_def))
    effective_level = max(level, 5)
    level_factor = 1.0 + (effective_level - 3) * 0.015
    base = 4.0 * power * effective_atk / (effective_def * 1.25)
    base = (base / 8) + 2
    base *= level_factor
    base *= random.uniform(0.92, 1.08)
    dmg = int(round(base * type_mult_ * crit_mult))
    return max(1, dmg)

def status_tick_lines(champ_state: Dict[str, Any], champ_display: str) -> List[str]:
    out: List[str] = []
    if champ_state.get("burn_turns", 0) > 0:
        champ_state["burn_turns"] -= 1
        burn_dmg = max(2, int(round(champ_state["max_hp"] * random.uniform(0.08, 0.09))))
        champ_state["hp"] -= burn_dmg
        burn_texts = [
            f"{STATUS_EMOJI['burn']} {champ_display} burns like a bad batch from a sketchy cook! (-{burn_dmg})",
            f"{STATUS_EMOJI['burn']} {champ_display} is on fire — like cooking meth in a studio apartment! (-{burn_dmg})",
            f"{STATUS_EMOJI['burn']} {champ_display} burns like a UTI after a festival weekend! (-{burn_dmg})",
        ]
        out.append(random.choice(burn_texts))
    if champ_state.get("poison_turns", 0) > 0:
        champ_state["poison_turns"] -= 1
        poison_dmg = max(1, int(round(champ_state["max_hp"] * random.uniform(0.04, 0.05))))
        champ_state["hp"] -= poison_dmg
        poison_texts = [
            f"{STATUS_EMOJI['poison']} {champ_display} twitches — the laced batch is working its way through! (-{poison_dmg})",
            f"{STATUS_EMOJI['poison']} {champ_display} goes pale. The toxin doesn't care about your schedule. (-{poison_dmg})",
            f"{STATUS_EMOJI['poison']} {champ_display} feels it now — Needle Rain's parting gift! (-{poison_dmg})",
            f"{STATUS_EMOJI['poison']} {champ_display} is dissolving from the inside — slow, chemical, inevitable! (-{poison_dmg})",
            f"{STATUS_EMOJI['poison']} Another tick. {champ_display} didn't sign up for this batch. (-{poison_dmg})",
            f"{STATUS_EMOJI['poison']} {champ_display} gurgles. The poison has opinions. (-{poison_dmg})",
        ]
        out.append(random.choice(poison_texts))
    if champ_state.get("wet_dream_turns", 0) > 0:
        champ_state["wet_dream_turns"] -= 1
        if champ_state["wet_dream_turns"] == 0:
            out.append(f"{STATUS_EMOJI['wet_dream']} {champ_display} comes back down — whatever that was, it's out of the system. Back to normal.")
        else:
            wet_dream_tick_texts = [
                f"{STATUS_EMOJI['wet_dream']} {champ_display} is still seeing things — hands won't stop shaking! (-10% dmg this turn)",
                f"{STATUS_EMOJI['wet_dream']} {champ_display} flinches at shadows — the dose is still peaking! (-10% dmg this turn)",
                f"{STATUS_EMOJI['wet_dream']} {champ_display} can't hold it together — something in the ritual bag broke them! (-10% dmg this turn)",
                f"{STATUS_EMOJI['wet_dream']} {champ_display} is mid-trip and mid-fight — neither is going well! (-10% dmg this turn)",
            ]
            out.append(random.choice(wet_dream_tick_texts))
    return out

def can_act(champ_state: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if champ_state.get("sleep_turns", 0) > 0:
        champ_state["sleep_turns"] -= 1
        if champ_state["sleep_turns"] == 0:
            champ_state["has_slept"] = True
        sleep_texts = [
            "passed out harder than someone who mixed heroin with Benadryl!",
            "is down for the count — that wasn't just Cannabis indica!",
            "is sleeping like someone who just made a very regrettable decision!",
            "is out cold — the cult calls this 'enlightenment'.",
        ]
        return False, [random.choice(sleep_texts)]
    if champ_state.get("confuse_turns", 0) > 0:
        champ_state["confuse_turns"] -= 1
        self_dmg = max(2, int(round(champ_state["max_hp"] * random.uniform(0.08, 0.10))))
        champ_state["hp"] -= self_dmg
        confuse_texts = [
            f"<b>{{champ_name}}</b> is tweaking on PCP and attacks itself! (-{self_dmg})",
            f"<b>{{champ_name}}</b> is fully gone on PCP — swings at thin air and connects with its own face! (-{self_dmg})",
            f"<b>{{champ_name}}</b> took too much PCP and has no idea what's happening — self-inflicted! (-{self_dmg})",
            f"<b>{{champ_name}}</b> is on a PCP trip and can't tell friend from foe — hits itself! (-{self_dmg})",
        ]
        return False, [("html_named", random.choice(confuse_texts))]
    if champ_state.get("stun_turns", 0) > 0:
        champ_state["stun_turns"] -= 1
        return False, ["is stunned — can't move a muscle!"]
    return True, []

def do_move(attacker: Dict[str, Any], defender: Dict[str, Any], a_key: str, d_key: str,
            a_level: int, move: Dict[str, Any], attacker_name: Optional[str] = None,
            defender_name: Optional[str] = None, defender_level: int = 0) -> List[str]:
    out: List[str] = []
    a = champ_from_key(a_key)
    d = champ_from_key(d_key)
    a_name = attacker_name or a["display"]
    d_name = defender_name or d["display"]

    base_miss = 1.0 - float(move.get("acc", 0.9))
    extra_miss = level_gap_miss_penalty(a_level, defender_level)
    effective_miss = min(0.60, base_miss + extra_miss)
    if random.random() < effective_miss:
        out.append(f"{TYPE_EMOJI[a['type']]} {a_name} used {move['name']}!")
        miss_texts = [
            "💨 Missed! Aim like that and even your dealer would drop you!",
            "💨 Missed! Shaking too hard — lay off the meth next time!",
            "💨 Missed! Even a blind junkie shoots straighter than that!",
        ] if extra_miss > 0 else [
            "💨 Missed! Couldn't hit a barn door with a bazooka!",
            "💨 Missed! Too high to aim properly!",
            "💨 Missed! Your dealer hits more consistently than this!",
        ]
        out.append(random.choice(miss_texts))
        return out

    move_text = random.choice(move.get('text', ['attacks!']))
    out.append(("html", f"{TYPE_EMOJI[a['type']]} <b>{html.escape(a_name)}</b> {move_text}"))

    kind = move.get("kind", "damage")

    if kind == "status_sleep":
        if defender.get("sleep_turns", 0) > 0:
            out.append(f"{STATUS_EMOJI['sleep']} {d_name} is already sleeping! Move wasted.")
            attacker["last_used_sleep"] = False
            return out
        sleep_cooldown_remaining = attacker.get("sleep_spore_cooldown", 0)
        if sleep_cooldown_remaining > 0:
            attacker["sleep_spore_cooldown"] = sleep_cooldown_remaining - 1
            out.append(("html",
                f"🌿 {a_name} reaches for the stash — but the bag's empty! "
                f"Sleep Spore needs {sleep_cooldown_remaining} more turn{'s' if sleep_cooldown_remaining != 1 else ''} to recharge. 💨"
            ))
            return out
        if attacker.get("last_used_sleep", False):
            attacker["sleep_turns"] = 1
            attacker["last_used_sleep"] = False
            attacker["sleep_spore_cooldown"] = 0
            out.append(("html",
                f"🌿 {a_name} reaches into the bag one too many times... takes a massive hit of "
                f"<b>Cannabis indica</b> and zones out completely. 💨\n"
                f"<i>\"Make Love, not War\"</i> — {a_name} refuses to fight this turn!"
            ))
            return out
        turns = move.get("sleep_turns", (1, 2))
        sleep_t = random.randint(int(turns[0]), int(turns[1]))
        defender["sleep_turns"] = sleep_t
        defender["has_slept"] = True
        attacker["last_used_sleep"] = True
        attacker["sleep_spore_cooldown"] = 3
        cannabis_texts = [
            f"🌿 {a_name} hurls a fistful of <b>Cannabis indica</b>! {d_name} is absolutely baked and refuses to fight! 💨",
            f"🌿 {a_name} deploys the <b>Cannabis indica</b>! {d_name} takes a massive hit and passes out! 💨",
            f"🌿 {a_name} releases <b>Cannabis indica</b> spores! {d_name} smells it and immediately forgets what a battle is! 💨",
            f"🌿 {a_name} attacks with a plant called <b>Cannabis indica</b>! {d_name} is stoned beyond comprehension — it ain't moving! 💨",
        ]
        out.append(("html", random.choice(cannabis_texts)))
        out.append(f"💤 {d_name} is asleep for {sleep_t} turn{'s' if sleep_t != 1 else ''}!")
        return out

    if kind == "status_wet_dream":
        uses_left = attacker.get("wet_dream_uses_left", 0)
        if uses_left <= 0:
            out.append(f"{STATUS_EMOJI['wet_dream']} {a_name} tries to frighten {d_name} — but the nerve is gone! (Used up)")
            return out
        if defender.get("wet_dream_turns", 0) > 0:
            out.append(f"{STATUS_EMOJI['wet_dream']} {d_name} is already frightened! Can't stack Fright.")
            return out
        mult, eff = type_mult(a["type"], d["type"])
        wet_dream_dmg = calc_damage(attacker_atk=int(attacker["atk"]), defender_def=int(defender["def"]),
                                    level=a_level, power=28, type_mult_=mult, crit_mult=1.0, defender_level=defender_level)
        defender["hp"] -= wet_dream_dmg
        turns = move.get("wet_dream_turns", (2, 3))
        wet_dream_t = random.randint(int(turns[0]), int(turns[1]))
        defender["wet_dream_turns"] = wet_dream_t
        attacker["wet_dream_uses_left"] = uses_left - 1
        wet_dream_texts = [
            f"😨 {d_name} takes the hit and something behind their eyes breaks — <b>{wet_dream_dmg} dmg</b>! Shaking too hard to fight properly! (-10% dmg, {wet_dream_t} turns)",
            f"😨 {d_name} catches a face full of whatever that was — <b>{wet_dream_dmg} dmg</b>! Pupils blown, hands trembling! (-10% dmg, {wet_dream_t} turns)",
            f"😨 {a_name} lands the strike and watches {d_name} realize what's in their bloodstream — <b>{wet_dream_dmg} dmg</b>! They're not okay! (-10% dmg, {wet_dream_t} turns)",
            f"😨 {d_name} got touched by something that cannot be unfelt — <b>{wet_dream_dmg} dmg</b>! Fight-or-flight chose flight! (-10% dmg, {wet_dream_t} turns)",
            f"😨 {d_name} staggers back — the dose hit the wrong nerve! <b>{wet_dream_dmg} dmg</b>! Body's fighting itself now! (-10% dmg, {wet_dream_t} turns)",
        ]
        out.append(("html", random.choice(wet_dream_texts)))
        remaining = attacker["wet_dream_uses_left"]
        out.append(f"📋 Fright uses remaining: {remaining}/2")
        return out

    attacker["last_used_sleep"] = False
    if attacker.get("sleep_spore_cooldown", 0) > 0:
        attacker["sleep_spore_cooldown"] -= 1

    if kind == "status_burn":
        if defender.get("burn_turns", 0) > 0:
            out.append(f"{STATUS_EMOJI['burn']} {d_name} is already burning! The pipe backfires on {a_name}!")
            burn_t = random.randint(1, 2)
            attacker["burn_turns"] = max(attacker.get("burn_turns", 0), burn_t)
            return out
        burn_t = random.randint(*move.get("burn_turns", (2, 3)))
        defender["burn_turns"] = burn_t
        wisp_texts = [
            f"🔥 {d_name} inhales the fumes — burning from the inside for {burn_t} turns!",
            f"🔥 {d_name} gets hotboxed — Will-O-Wisp sets them on fire for {burn_t} turns!",
            f"🔥 {d_name} takes a massive hit of the fumes — scorched for {burn_t} turns!",
        ]
        out.append(("html", random.choice(wisp_texts)))
        return out

    if kind == "status_confuse":
        if defender.get("confuse_turns", 0) > 0:
            out.append(f"{STATUS_EMOJI['confuse']} {d_name} is already on a PCP trip! Move wasted.")
            return out
        rare = random.random() < float(move.get("confuse_rare_chance", 0.15))
        confuse_t = 2 if rare else 1
        defender["confuse_turns"] = confuse_t
        pulse_texts = [
            f"🌀 {d_name} takes a face full of PCP-laced water and loses all grip on reality! ({confuse_t} turn{'s' if confuse_t != 1 else ''})",
            f"🌀 {d_name} swallows the Water Pulse — fully dosed on PCP, confused for {confuse_t} turn{'s' if confuse_t != 1 else ''}!",
            f"🌀 {d_name} is absolutely tweaking on PCP — doesn't know where it is for {confuse_t} turn{'s' if confuse_t != 1 else ''}!",
        ]
        out.append(("html", random.choice(pulse_texts)))
        return out

    if kind == "status_debuff":
        if move.get("atk_debuff_pct"):
            if not defender.get("atk_debuff_turns", 0):
                defender["atk_debuff_turns"] = int(move.get("debuff_turns", 2))
                defender["atk"] = int(defender.get("atk", 0) * (1 - float(move["atk_debuff_pct"])))
                out.append(f"📉 {d_name}'s ATK dropped by {int(float(move['atk_debuff_pct'])*100)}%!")
            else:
                out.append(f"{d_name} is already debuffed!")
            return out
        if move.get("def_speed_debuff"):
            if not defender.get("def_speed_debuff_turns", 0):
                defender["def_speed_debuff_turns"] = int(move.get("debuff_turns", 2))
                defender["def"] = int(defender.get("def", 0) * 0.85)
                defender["spd"] = int(defender.get("spd", 0) * 0.85)
                out.append(f"💊 Molly Pressure hits! {d_name}'s DEF and SPD dropped!")
            else:
                out.append(f"{d_name} is already feeling the Molly pressure!")
            return out

    power = int(move.get("power", 40))
    crit_chance = 0.08 + float(move.get("crit_bonus", 0.0))
    crit = random.random() < crit_chance if kind == "damage_highcrit" else (random.random() < 0.08)
    crit_mult = 1.5 if crit else 1.0
    mult, eff = type_mult(a["type"], d["type"])

    dmg = calc_damage(attacker_atk=int(attacker["atk"]), defender_def=int(defender["def"]),
                      level=a_level, power=power, type_mult_=mult, crit_mult=crit_mult, defender_level=defender_level)

    if attacker.get("wet_dream_turns", 0) > 0:
        dmg = max(1, int(round(dmg * 0.90)))

    if move.get("debuff_bonus") and (defender.get("def_speed_debuff_turns", 0) > 0):
        dmg = int(round(dmg * 1.25))
        out.append("🧨 Debuff Bonus: Jenga Joint Collapse hits extra hard!")

    defender["hp"] -= dmg
    eff_txt = ""
    if eff == "strong":
        eff_txt = " 💥 Super effective!"
    elif eff == "weak":
        eff_txt = " 🫧 Not very effective…"
    crit_texts = [
        " CRIT — hits harder than a bad batch!",
        " CRIT — lands like a fentanyl overdose, unexpected and devastating!",
        " CRIT — dirty hit that would make a cartel blush!",
        " CRIT — straight to the nerve, no warning!",
    ]
    crit_txt = random.choice(crit_texts) if crit else ""
    out.append(("html", f"💢 Hit: <b>{dmg} damage</b>{crit_txt}{eff_txt}"))

    if move.get("spd_boost_chance") and random.random() < float(move["spd_boost_chance"]):
        boost = int(move.get("spd_boost", 2))
        attacker["spd"] = int(attacker.get("spd", 0)) + boost
        out.append(f"⚡ Crack Surge! {a_name}'s SPD increased by {boost}!")

    if move.get("def_down_chance") and random.random() < float(move["def_down_chance"]):
        defender["def"] = int(defender.get("def", 0) * 0.85)
        defender["def_down_turns"] = int(move.get("def_down_turns", 2))
        out.append(f"🛡️ {d_name}'s DEF dropped!")

    if move.get("stun_chance") and random.random() < float(move["stun_chance"]):
        defender["stun_turns"] = int(move.get("stun_turns", 1))
        out.append(f"🌀 {d_name} is stunned by the Ketamine Quake!")

    if kind == "damage_burn":
        if defender.get("burn_turns", 0) == 0 and random.random() < float(move.get("burn_chance", 0.25)):
            defender["burn_turns"] = 3
            out.append(f"{STATUS_EMOJI['burn']} {d_name} was burned! (3 turns)")
    if kind == "damage_poison":
        if defender.get("poison_turns", 0) == 0 and random.random() < float(move.get("poison_chance", 0.60)):
            turns = move.get("poison_turns", (3, 4))
            poison_t = random.randint(int(turns[0]), int(turns[1]))
            defender["poison_turns"] = poison_t
            out.append(random.choice([
                f"{STATUS_EMOJI['poison']} {d_name} got dosed — the toxin's already in the blood! ({poison_t} turns)",
                f"{STATUS_EMOJI['poison']} {d_name} didn't feel it hit — that's the worst kind! ({poison_t} turns)",
                f"{STATUS_EMOJI['poison']} The laced tip found a vein. {d_name} has {poison_t} turns to regret standing still.",
            ]))

    return out

# =========================
# MESSAGE EDIT / BATTLE UI
# =========================

async def _safe_edit(bot, chat_id: int, message_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[-MAX_MESSAGE_CHARS:]
    for _ in range(5):
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
                parse_mode='HTML', disable_web_page_preview=True, reply_markup=reply_markup,
            )
            return True
        except RetryAfter as e:
            await asyncio.sleep(float(getattr(e, "retry_after", 1.5)))
        except (TimedOut, NetworkError):
            await asyncio.sleep(0.8)
        except BadRequest:
            text = "".join(ch for ch in text if ch >= " " or ch in "\n\t")
            text = text.replace("\u202e", "")
            await asyncio.sleep(0.25)
        except Exception:
            await asyncio.sleep(0.5)
    return False

async def _battle_reposition_message(bot, chat_id: int, state: Dict[str, Any], text: str,
                                     reply_markup: Optional[InlineKeyboardMarkup] = None,
                                     *, force: bool = False) -> None:
    now = time.monotonic()
    cooldown = float(state.get("reposition_cooldown", REPOSITION_COOLDOWN))
    should_reposition = force or ((now - float(state.get("last_reposition", 0.0))) >= cooldown)

    if not should_reposition:
        ok = await _safe_edit(bot, chat_id, state["message_id"], text, reply_markup=reply_markup)
        if ok:
            state["last_rendered_text"] = text
            state["last_reply_markup"] = reply_markup
        return

    sent = False
    for _ in range(3):
        try:
            new_msg = await bot.send_message(
                chat_id=chat_id, text=text, parse_mode='HTML',
                disable_web_page_preview=True, reply_markup=reply_markup,
            )
            old_message_id = state["message_id"]
            state["message_id"] = new_msg.message_id
            state["last_reposition"] = now
            state["last_rendered_text"] = text
            state["last_reply_markup"] = reply_markup
            sent = True
            asyncio.ensure_future(bot.delete_message(chat_id=chat_id, message_id=old_message_id))
            break
        except RetryAfter as e:
            await asyncio.sleep(float(getattr(e, "retry_after", 1.5)))
        except (TimedOut, NetworkError):
            await asyncio.sleep(0.8)
        except Exception:
            await asyncio.sleep(0.4)

    if not sent:
        ok = await _safe_edit(bot, chat_id, state["message_id"], text, reply_markup=reply_markup)
        if ok:
            state["last_rendered_text"] = text
            state["last_reply_markup"] = reply_markup

def _battle_render(state: Dict[str, Any]) -> str:
    lines = state["log_lines"]
    if len(lines) > MAX_LINES_SHOWN:
        del lines[:-MAX_LINES_SHOWN]
    body = "\n".join(lines) if lines else "…"
    while len(body) > MAX_MESSAGE_CHARS and len(lines) > 8:
        del lines[:3]
        body = "\n".join(lines)
    if len(body) > MAX_MESSAGE_CHARS:
        body = body[-MAX_MESSAGE_CHARS:]
    return body

def _battle_hud_html(state: Dict[str, Any]) -> str:
    return f"<pre>{html.escape(battle_hud(state['c1_label'], state['champ1']['hp'], state['champ1']['max_hp'], state['c2_label'], state['champ2']['hp'], state['champ2']['max_hp']), quote=False)}</pre>"

async def _battle_push_message(chat_id: int, state: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE, line, delay: float = ACTION_DELAY, reply_markup: Optional[InlineKeyboardMarkup] = None, *, force_reposition: bool = False, raw_html: bool = False):
    if isinstance(line, tuple) and line[0] == "html":
        state["log_lines"].append(line[1])
    elif raw_html:
        state["log_lines"].append(line)
    else:
        state["log_lines"].append(html.escape(str(line), quote=False))
    text = _battle_render(state)
    await _battle_reposition_message(context.bot, chat_id, state, text, reply_markup=reply_markup, force=force_reposition)
    if delay > 0:
        await asyncio.sleep(delay)

async def _battle_push_hud(chat_id: int, state: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE, delay: float = HUD_DELAY, reply_markup: Optional[InlineKeyboardMarkup] = None, *, force_reposition: bool = False):
    state["log_lines"].append(_battle_hud_html(state))
    text = _battle_render(state)
    await _battle_reposition_message(context.bot, chat_id, state, text, reply_markup=reply_markup, force=force_reposition)
    if delay > 0:
        await asyncio.sleep(delay)

def _battle_turn_user(state: Dict[str, Any]) -> str:
    return state["user"] if state["turn"] == 0 else state["opponent"]

def _battle_turn_name(state: Dict[str, Any]) -> str:
    return state["p1_name"] if state["turn"] == 0 else state["p2_name"]

def _battle_turn_champ_key(state: Dict[str, Any]) -> str:
    return state["c1_key"] if state["turn"] == 0 else state["c2_key"]

def _battle_turn_champ_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return state["champ1"] if state["turn"] == 0 else state["champ2"]

def _battle_def_champ_key(state: Dict[str, Any]) -> str:
    return state["c2_key"] if state["turn"] == 0 else state["c1_key"]

def _battle_def_champ_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return state["champ2"] if state["turn"] == 0 else state["champ1"]

def _battle_turn_level(state: Dict[str, Any]) -> int:
    return state["lv1"] if state["turn"] == 0 else state["lv2"]

def _battle_next_turn(state: Dict[str, Any]) -> None:
    state["turn"] = 1 - state["turn"]

async def _battle_prompt_turn(chat_id: int, state: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE):
    if state["actions"] % 2 == 0:
        state["round"] += 1
        await _battle_push_message(chat_id, state, context, f"━━━ Round {state['round']} ━━━", delay=0.35, force_reposition=False)
    name = _battle_turn_name(state)
    champ_key = _battle_turn_champ_key(state)
    turn_user = _battle_turn_user(state)
    champ_name = champ_display_for_player(turn_user, champ_key)
    kb = _battle_move_keyboard(chat_id, champ_key, turn_user, state)
    await _battle_push_message(chat_id, state, context, f"\n🎯 {name}'s turn — choose a move for {champ_name}:", delay=0.05, reply_markup=kb, force_reposition=True)

async def _end_battle(chat_id: int, state: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE, winner: str, loser: str):
    players[state["user"]]["owned_suimon"][state["u_idx"]]["hp"] = max(state["champ1"]["hp"], 0)
    players[state["opponent"]]["owned_suimon"][state["o_idx"]]["hp"] = max(state["champ2"]["hp"], 0)

    u_idx = state["u_idx"]
    o_idx = state["o_idx"]
    xp_w, xp_l = award_battle_xp(winner, loser, u_idx, o_idx)
    save_players(players)

    w_name = display_name(winner, "Winner")
    w_suimon = players[winner]["owned_suimon"][u_idx if winner == state["user"] else o_idx]

    await _battle_push_message(chat_id, state, context, "The dust settles…", delay=0.45, reply_markup=None)
    await _battle_push_message(chat_id, state, context, f"🏆 Winner: {w_name} with {suimon_full_name(w_suimon)}!", delay=0.45, reply_markup=None)
    await _battle_push_message(chat_id, state, context, f"🎁 XP: {xp_w} (Winner) / {xp_l} (Loser)", delay=0.35, reply_markup=None)

    lvlups = []
    u_suimon = players[state["user"]]["owned_suimon"][u_idx]
    o_suimon = players[state["opponent"]]["owned_suimon"][o_idx]
    if u_suimon.get("just_leveled"):
        lvlups.append((state["p1_name"], u_suimon["level"]))
        u_suimon.pop("just_leveled", None)
    if o_suimon.get("just_leveled"):
        lvlups.append((state["p2_name"], o_suimon["level"]))
        o_suimon.pop("just_leveled", None)
    if lvlups:
        await _battle_push_message(chat_id, state, context, "📣 Level Up!", delay=0.25, reply_markup=None)
        for n, lv in lvlups:
            await _battle_push_message(chat_id, state, context, f"⭐ {n} is now Lv.{lv}!", delay=0.25, reply_markup=None)

    await _battle_push_message(chat_id, state, context, "✅ Battle complete.", delay=END_DELAY, reply_markup=None)

    BATTLES.pop(chat_id, None)
    ACTIVE_BATTLES.discard(chat_id)

async def _auto_move(chat_id: int, state: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE):
    turn_user = _battle_turn_user(state)
    a_key = _battle_turn_champ_key(state)
    moves = champ_from_key(a_key)["moves"]
    idx = random.randint(0, len(moves) - 1)

    state["resolving"] = True
    state["resolving_since"] = time.monotonic()
    state["last_move_ts"] = time.monotonic()

    attacker = _battle_turn_champ_state(state)
    defender = _battle_def_champ_state(state)
    a_key = _battle_turn_champ_key(state)
    d_key = _battle_def_champ_key(state)
    a_lvl = _battle_turn_level(state)
    a_name = champ_display_for_player(turn_user, a_key)
    defender_user = state["opponent"] if turn_user == state["user"] else state["user"]
    d_lvl = state["lv2"] if turn_user == state["user"] else state["lv1"]

    try:
        await _battle_push_message(chat_id, state, context, f"⏰ {_battle_turn_name(state)} is AFK — auto-move triggered!", delay=0.4, reply_markup=None)

        for line in status_tick_lines(attacker, a_name):
            await _battle_push_message(chat_id, state, context, line, delay=0.45, reply_markup=None)
        if attacker["hp"] <= 0:
            winner = state["opponent"] if turn_user == state["user"] else state["user"]
            await _end_battle(chat_id, state, context, winner=winner, loser=turn_user)
            return

        ok, sleep_lines = can_act(attacker)
        if not ok:
            raw = sleep_lines[0]
            if isinstance(raw, tuple) and raw[0] == "html_named":
                line_out = ("html", raw[1].format(champ_name=html.escape(a_name)))
            elif isinstance(raw, tuple) and raw[0] == "html":
                line_out = raw
            else:
                line_out = ("html", f"{STATUS_EMOJI['sleep']} <b>{html.escape(a_name)}</b> {raw}")
            await _battle_push_message(chat_id, state, context, line_out, delay=0.55, reply_markup=None)
        else:
            move = moves[idx]
            for line in do_move(attacker, defender, a_key, d_key, a_lvl, move, attacker_name=a_name, defender_name=champ_display_for_player(defender_user, d_key), defender_level=d_lvl):
                await _battle_push_message(chat_id, state, context, line, delay=0.55, reply_markup=None)

        attacker["hp"] = max(0, int(attacker["hp"]))
        defender["hp"] = max(0, int(defender["hp"]))
        await _battle_push_hud(chat_id, state, context, delay=0.25, reply_markup=None)

        if state["champ1"]["hp"] <= 0 or state["champ2"]["hp"] <= 0:
            winner = state["user"] if state["champ1"]["hp"] > 0 else state["opponent"]
            loser = state["opponent"] if winner == state["user"] else state["user"]
            await _end_battle(chat_id, state, context, winner=winner, loser=loser)
            return

        state["actions"] += 1
        if state["round"] >= state["max_rounds"]:
            if state["champ1"]["hp"] == state["champ2"]["hp"]:
                winner = state["user"] if random.random() < 0.5 else state["opponent"]
            else:
                winner = state["user"] if state["champ1"]["hp"] > state["champ2"]["hp"] else state["opponent"]
            loser = state["opponent"] if winner == state["user"] else state["user"]
            await _battle_push_message(chat_id, state, context, "⏱️ Time! Battle ends by decision.", delay=0.35, reply_markup=None)
            await _end_battle(chat_id, state, context, winner=winner, loser=loser)
            return

        _battle_next_turn(state)
        await _battle_prompt_turn(chat_id, state, context)
    finally:
        latest = BATTLES.get(chat_id)
        if latest is state:
            state["resolving"] = False

async def _afk_watcher(context: ContextTypes.DEFAULT_TYPE):
    now = time.monotonic()
    for chat_id, state in list(BATTLES.items()):
        if state.get("resolving"):
            continue
        last = state.get("last_move_ts", now)
        if now - last >= AFK_TIMEOUT:
            state["last_move_ts"] = now
            try:
                await _auto_move(chat_id, state, context)
            except Exception as e:
                print(f"[AFK watcher] Error in chat {chat_id}: {e}")

def _battle_move_keyboard(chat_id: int, champ_key: str, player_id: str, state: Dict[str, Any]) -> InlineKeyboardMarkup:
    moves = champ_from_key(champ_key)["moves"]
    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for idx, m in enumerate(moves[:4]):
        row.append(InlineKeyboardButton(m["name"], callback_data=f"mv|{chat_id}|{idx}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    balls = int(players.get(player_id, {}).get("suiballs", 0))
    used_this_battle = state.get("suiballs_used", {}).get(player_id, 0)
    remaining_uses = max(0, 1 - used_this_battle)
    can_heal = balls > 0 and remaining_uses > 0
    ball_label = f"🧿 Use Suiball ({balls} 🎒 · {remaining_uses}/1 left)" if can_heal else f"🧿 Suiball (0 left)"
    rows.append([InlineKeyboardButton(ball_label, callback_data=f"heal|{chat_id}" if can_heal else f"noop|{chat_id}")])
    rows.append([InlineKeyboardButton("🏳️ Forfeit", callback_data=f"ff|{chat_id}")])
    return InlineKeyboardMarkup(rows)

async def battle_move_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()

    global players
    players = load_players()

    data = query.data or ""
    parts = data.split("|")
    if len(parts) < 2:
        return

    kind = parts[0]
    try:
        chat_id = int(parts[1])
    except Exception:
        return

    state = BATTLES.get(chat_id)
    if not state:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    clicker = str(query.from_user.id)
    await query.answer()

    if kind == "noop":
        return

    if state.get("resolving"):
        resolving_since = float(state.get("resolving_since", 0.0))
        if resolving_since > 0 and (time.monotonic() - resolving_since) > 30:
            state["resolving"] = False
            state["resolving_since"] = 0.0
        else:
            return

    if kind == "ff":
        if clicker not in (state["user"], state["opponent"]):
            return
        winner = state["opponent"] if clicker == state["user"] else state["user"]
        loser = clicker
        await _battle_push_message(chat_id, state, context, f"🏳️ {display_name(clicker)} forfeits!", delay=0.25, reply_markup=None)
        await _end_battle(chat_id, state, context, winner=winner, loser=loser)
        return

    if kind == "heal":
        turn_user = _battle_turn_user(state)
        if clicker != turn_user:
            await query.answer("Not your turn.", show_alert=False)
            return
        balls = int(players.get(clicker, {}).get("suiballs", 0))
        if balls <= 0:
            await query.answer("❌ You have no Suiballs!", show_alert=True)
            return
        used_this_battle = state.get("suiballs_used", {}).get(clicker, 0)
        if used_this_battle >= 1:
            await query.answer()
            return
        state["resolving"] = True
        state["resolving_since"] = time.monotonic()
        try:
            players[clicker]["suiballs"] = balls - 1
            save_players(players)
            state["suiballs_used"][clicker] = state.get("suiballs_used", {}).get(clicker, 0) + 1
            healer_champ_state = _battle_turn_champ_state(state)
            healer_champ_state["hp"] = healer_champ_state["max_hp"]
            healer_name = champ_display_for_player(clicker, _battle_turn_champ_key(state))
            await _battle_reposition_message(context.bot, chat_id, state, _battle_render(state), reply_markup=None)
            await _battle_push_message(chat_id, state, context, f"🧿 {display_name(clicker)} used a Suiball on {healer_name}! HP fully restored!", delay=0.5, reply_markup=None)
            await _battle_push_hud(chat_id, state, context, delay=0.25, reply_markup=None)
            state["actions"] += 1
            _battle_next_turn(state)
            await _battle_prompt_turn(chat_id, state, context)
        finally:
            latest = BATTLES.get(chat_id)
            if latest is state:
                state["resolving"] = False
        return

    if kind != "mv" or len(parts) != 3:
        return

    turn_user = _battle_turn_user(state)
    if clicker != turn_user:
        await query.answer("Not your turn.", show_alert=False)
        return

    state["resolving"] = True
    state["resolving_since"] = time.monotonic()
    state["last_move_ts"] = time.monotonic()

    attacker = _battle_turn_champ_state(state)
    defender = _battle_def_champ_state(state)
    a_key = _battle_turn_champ_key(state)
    d_key = _battle_def_champ_key(state)
    a_lvl = _battle_turn_level(state)
    a_name = champ_display_for_player(clicker, a_key)

    await _battle_reposition_message(context.bot, chat_id, state, _battle_render(state), reply_markup=None)

    try:
        for line in status_tick_lines(attacker, a_name):
            await _battle_push_message(chat_id, state, context, line, delay=0.45, reply_markup=None)
        if attacker["hp"] <= 0:
            winner = state["opponent"] if clicker == state["user"] else state["user"]
            loser = clicker
            await _end_battle(chat_id, state, context, winner=winner, loser=loser)
            return

        ok, sleep_lines = can_act(attacker)
        if not ok:
            raw = sleep_lines[0]
            if isinstance(raw, tuple) and raw[0] == "html_named":
                line_out = ("html", raw[1].format(champ_name=html.escape(a_name)))
            elif isinstance(raw, tuple) and raw[0] == "html":
                line_out = raw
            else:
                line_out = ("html", f"{STATUS_EMOJI['confuse'] if 'PCP' in str(raw) else STATUS_EMOJI['sleep']} <b>{html.escape(a_name)}</b> {raw}")
            await _battle_push_message(chat_id, state, context, line_out, delay=0.55, reply_markup=None)
        else:
            try:
                idx = int(parts[2])
            except Exception:
                idx = 0
            moves = champ_from_key(a_key)["moves"]
            idx = max(0, min(idx, len(moves) - 1))
            move = moves[idx]

            defender_user = state["opponent"] if clicker == state["user"] else state["user"]
            d_lvl = state["lv2"] if clicker == state["user"] else state["lv1"]
            for line in do_move(attacker, defender, a_key, d_key, a_lvl, move, attacker_name=a_name, defender_name=champ_display_for_player(defender_user, d_key), defender_level=d_lvl):
                await _battle_push_message(chat_id, state, context, line, delay=0.55, reply_markup=None)

        attacker["hp"] = max(0, int(attacker["hp"]))
        defender["hp"] = max(0, int(defender["hp"]))
        await _battle_push_hud(chat_id, state, context, delay=0.25, reply_markup=None)

        if state["champ1"]["hp"] <= 0 or state["champ2"]["hp"] <= 0:
            winner = state["user"] if state["champ1"]["hp"] > 0 else state["opponent"]
            loser = state["opponent"] if winner == state["user"] else state["user"]
            await _end_battle(chat_id, state, context, winner=winner, loser=loser)
            return

        state["actions"] += 1
        if state["round"] >= state["max_rounds"]:
            if state["champ1"]["hp"] == state["champ2"]["hp"]:
                winner = state["user"] if random.random() < 0.5 else state["opponent"]
            else:
                winner = state["user"] if state["champ1"]["hp"] > state["champ2"]["hp"] else state["opponent"]
            loser = state["opponent"] if winner == state["user"] else state["user"]
            await _battle_push_message(chat_id, state, context, "⏱️ Time! Battle ends by decision.", delay=0.35, reply_markup=None)
            await _end_battle(chat_id, state, context, winner=winner, loser=loser)
            return

        _battle_next_turn(state)
        await _battle_prompt_turn(chat_id, state, context)
    finally:
        latest = BATTLES.get(chat_id)
        if latest is state:
            state["resolving"] = False

# =========================
# MENÜS & KEYBOARDS
# =========================

def main_menu_kb(user_id: Optional[str] = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Champs", callback_data="menu|champs"),
         InlineKeyboardButton("⚔️ Fight", callback_data="menu|fight")],
        [InlineKeyboardButton("🏆 Rankings", callback_data="menu|leaderboard"),
         InlineKeyboardButton("🪪 Profile", callback_data="menu|profile")],
        [InlineKeyboardButton("🎒 Inventory", callback_data="menu|inventory"),
         InlineKeyboardButton("🩹 Heal", callback_data="menu|heal")],
        [InlineKeyboardButton("🌍 Explore", callback_data="menu|explore")],
    ])

def choose_champ_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌿 Basaurimon", callback_data="choose|basaurimon")],
        [InlineKeyboardButton("🔥 Suimander", callback_data="choose|suimander")],
        [InlineKeyboardButton("💧 Suiqrtle", callback_data="choose|suiqrtle")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu|home")],
    ])

def naming_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu|home")]])

def nickname_required_text(player_id: str) -> str:
    s = get_active_suimon(player_id)
    if not s:
        return "Choose your champ first with /choose or Menu → 📜 Champs."
    base_name = CHAMPS.get(s["species"], {}).get("display", "Unknown")
    return (
        "📝 <b>Name required</b>\n\n"
        f"Your starter is <b>{base_name}</b>.\n\n"
        "🚫 You cannot fight yet. First give your champ a custom name.\n\n"
        "Use <code>/name YourName</code>\n"
        "Example: <code>/name Joyamon</code>"
    )

def fancy_menu_caption(user_id: str) -> str:
    p = players.get(user_id, {})
    s = get_active_suimon(user_id)
    title = f"🧭 <b>{html.escape(display_name(user_id))}'s Menu</b>"
    if not s:
        return (
            f"{title}\n\n"
            "🔥 <b>Welcome to Suimon Arena</b>\n"
            "Pick your starter, name it and begin your climb.\n\n"
            "✨ <b>Start here</b>\n"
            "• Open <b>📜 Champs</b>\n"
            "• Pick your starter\n"
            "• Name it with <code>/name YourName</code>\n"
            "• Challenge players with <code>/fight</code>"
        )

    level = int(s.get("level", 1))
    xp = int(s.get("xp", 0))
    need = xp_needed(level)
    wins = int(s.get("wins", 0))
    losses = int(s.get("losses", 0))
    balls = int(p.get("suiballs", 0))
    net_balls = int(p.get("net_balls", 0))
    stats = get_stats(s["species"], level)
    cur_hp = s.get("hp", stats["hp"])
    champ_label = html.escape(suimon_full_name(s))
    type_icon = TYPE_EMOJI.get(CHAMPS[s["species"]]["type"], "✨")
    team_size = len(p.get("owned_suimon", []))
    return (
        f"{title}\n\n"
        f"{type_icon} <b>{champ_label}</b> • Lv.<b>{level}</b>\n"
        f"❤️ <b>HP:</b> {cur_hp}/{stats['hp']}\n"
        f"✨ <b>XP:</b> {xp}/{need if level < MAX_LEVEL else 0}\n"
        f"⚔️ <b>Record:</b> {wins}W / {losses}L\n"
        f"🎒 <b>Suiballs:</b> {balls} | 🥅 <b>Net Balls:</b> {net_balls}\n"
        f"📦 <b>Team:</b> {team_size} Suimon\n\n"
        "Choose your next move below."
    )

# =========================
# COMMANDS
# =========================

async def _bootstrap_user(update: Update) -> str:
    global players
    players = load_players()
    user_id = str(update.effective_user.id)
    tg_name = (update.effective_user.first_name or "Player").strip()
    ensure_player(user_id, tg_name, update.effective_user.username)
    if update.effective_chat:
        _remember_chat(user_id, int(update.effective_chat.id))
    ensure_daily(user_id)
    save_players(players)
    return user_id

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user_id = await _bootstrap_user(update)
    if not update.message: return
    await send_menu_photo(update.message, fancy_menu_caption(user_id), main_menu_kb(user_id))

async def intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    lines = [
        "🎮 <b>Welcome to Suimon Arena</b>",
        "",
        "A turn based Telegram PvP game where every trainer controls multiple Suimon, levels them up and keeps their HP between battles.",
        "",
        "━━━ How to play ━━━",
        "1. Open Menu → <b>📜 Champs</b> and pick your permanent starter.",
        "2. Name your champ with <b>/name YourName</b>.",
        "3. Challenge someone with <b>/fight</b> or <b>/fight @Name</b>.",
        "4. Explore worlds with <b>/explore</b> to find wild Suimon!",
        "5. In battle, choose moves with the inline buttons.",
        "",
        "Type chart: 🔥 > 🌿 > 💧 > 🔥",
        "",
        "━━━ Core rules ━━━",
        "• Your Suimon keep their remaining HP after every fight.",
        "• If HP reaches 0, heal first with <b>/heal</b>.",
        f"• You receive {DAILY_SUIBALLS} Suiballs per day (cap {SUIBALL_CAP}).",
        f"• You receive {DAILY_NETBALLS} Net Ball per day (cap {NETBALL_CAP}) for catching wild Suimon.",
        f"• Max level is {MAX_LEVEL}.",
        "",
        "━━━ Commands ━━━",
        "/start /menu /intro /champs /choose /name /profile /rankings /inventory /heal /explore /fight",
    ]
    if not get_active_suimon(user):
        lines.insert(2, "⚠️ You haven't chosen a champ yet. Pick one with /choose.")
    await update.message.reply_text("\n".join(lines), reply_markup=main_menu_kb(user), parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    await send_menu_photo(update.message, fancy_menu_caption(user), main_menu_kb(user))

async def champs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    await _bootstrap_user(update)
    lines = ["📜 Starter Champs", ""]
    for key in ["basaurimon", "suimander", "suiqrtle"]:
        c = CHAMPS[key]
        moves = ", ".join([m["name"] for m in c["moves"]])
        lines.append(f"{TYPE_EMOJI[c['type']]} {c['display']}  — type: {c['type']}")
        lines.append(f"   Moves: {moves}")
        lines.append("")
    if update.message:
        await update.message.reply_text("🌟 <b>Choose your starter</b>\n\n" + "\n".join(lines), choose_champ_kb(), parse_mode="HTML")

async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    if not context.args:
        await update.message.reply_text("Choose your starter via Menu → 📜 Champs.", reply_markup=main_menu_kb(user))
        return
    if get_owned_suimon_list(user):
        await update.message.reply_text("⚠️ You already chose a starter.", reply_markup=main_menu_kb(user))
        return
    champ_key = champ_key_from_input(context.args[0])
    if champ_key not in ("basaurimon", "suimander", "suiqrtle"):
        await update.message.reply_text("Unknown champ. Use: /champs", reply_markup=main_menu_kb(user))
        return
    c = CHAMPS[champ_key]
    new_suimon = {
        "species": champ_key,
        "nickname": None,
        "level": 1,
        "xp": 0,
        "hp": get_stats(champ_key, 1)["hp"],
        "wins": 0,
        "losses": 0,
    }
    players[user]["owned_suimon"] = [new_suimon]
    players[user]["active_suimon"] = 0
    players[user]["suiballs"] = max(int(players[user].get("suiballs", 0)), 1)
    start_nickname_prompt(user)
    save_players(players)
    await update.message.reply_text(
        "📝 <b>Starter selected</b>\n\n"
        f"You picked <b>{c['display']}</b> {TYPE_EMOJI[c['type']]}.\n\n"
        "🚫 You cannot fight yet. First give your champ a custom name.\n\n"
        "Use <code>/name YourName</code>\n"
        "Example: <code>/name Joyamon</code>",
        naming_prompt_kb(), parse_mode="HTML"
    )

async def nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    s = get_active_suimon(user)
    if not s:
        await update.message.reply_text("Choose your champ first with /choose or Menu → 📜 Champs.", reply_markup=main_menu_kb(user))
        return
    current = suimon_full_name(s)
    raw = " ".join(context.args).strip()
    if not raw:
        start_nickname_prompt(user)
        await update.message.reply_text(
            f"📝 <b>Name your champ</b>\n\n"
            f"Current: <b>{html.escape(current)}</b>\n\n"
            "Use <code>/name YourName</code>\n"
            "Example: <code>/name Joyamon</code>",
            naming_prompt_kb(), parse_mode="HTML"
        )
        return
    nick = sanitize_champ_nickname(raw)
    if len(nick) < 2:
        start_nickname_prompt(user)
        await update.message.reply_text("Nickname too short. Use /name with 2 to 18 letters or numbers.", reply_markup=naming_prompt_kb())
        return
    s["nickname"] = nick
    clear_nickname_prompt(user)
    save_players(players)
    base_name = CHAMPS[s["species"]]["display"]
    await update.message.reply_text(
        f"✅ <b>{base_name}</b> is now named <b>{html.escape(nick)}</b>!\n\n"
        f"🎉 <b>{html.escape(nick)}</b> joined your team!",
        reply_markup=main_menu_kb(user), parse_mode="HTML"
    )

async def nickname_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    if not players[user].get("_awaiting_nickname"): return
    raw = (update.message.text or "").strip()
    nick = sanitize_champ_nickname(raw)
    if len(nick) < 2:
        start_nickname_prompt(user)
        await update.message.reply_text("❌ Too short. Use /name with 2 to 18 letters or numbers.", reply_markup=naming_prompt_kb())
        return
    s = get_active_suimon(user)
    if not s:
        return
    s["nickname"] = nick
    clear_nickname_prompt(user)
    save_players(players)
    base_name = CHAMPS[s["species"]]["display"]
    await update.message.reply_text(
        f"✅ <b>{base_name}</b> is now named <b>{html.escape(nick)}</b>!\n"
        f"🎉 <b>{html.escape(nick)}</b> joined your team! You can now fight.",
        reply_markup=main_menu_kb(user), parse_mode="HTML"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(user):
        await update.message.reply_text(nickname_required_text(user), reply_markup=naming_prompt_kb(), parse_mode="HTML")
        return
    if not update.message: return
    s = get_active_suimon(user)
    if not s:
        await update.message.reply_text("You have no champ yet. Use /start", reply_markup=main_menu_kb(user))
        return
    p = players[user]
    champ_data = CHAMPS[s["species"]]
    lv = int(s.get("level", 1))
    stats = get_stats(s["species"], lv)
    cur_hp = s.get("hp", stats["hp"])
    w = int(s.get("wins", 0))
    lo = int(s.get("losses", 0))
    balls = int(p.get("suiballs", 0))
    net_balls = int(p.get("net_balls", 0))
    fainted = " (FAINTED)" if cur_hp <= 0 else ""
    await update.message.reply_text(
        f"🪪 <b>Trainer Card</b>\n\n"
        f"👤 {display_name(user)}\n"
        f"🏅 Record: {w}W / {lo}L\n"
        f"{TYPE_EMOJI[champ_data['type']]} {suimon_full_name(s)} (Lv.{lv}){fainted}\n"
        f"❤️ HP: {cur_hp}/{stats['hp']}\n"
        f"✨ XP: {s.get('xp', 0)}/{xp_needed(lv) if lv < MAX_LEVEL else 0}\n"
        f"📈 Stats: ATK {stats['atk']} | DEF {stats['def']} | SPD {stats['spd']}\n\n"
        f"🎒 Suiballs: {balls} | 🥅 Net Balls: {net_balls}\n"
        f"📦 Team: {len(get_owned_suimon_list(user))} Suimon",
        reply_markup=main_menu_kb(user), parse_mode="HTML"
    )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    text = build_rankings_text(user, 10)
    await update.message.reply_text(text, reply_markup=main_menu_kb(user), parse_mode="HTML", disable_web_page_preview=True)

async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    p = players[user]
    balls = int(p.get("suiballs", 0))
    net_balls = int(p.get("net_balls", 0))
    team_list = []
    for i, s in enumerate(get_owned_suimon_list(user)):
        active = "⭐" if i == get_active_suimon_index(user) else "  "
        hp = s.get("hp", 0)
        max_hp = get_stats(s["species"], int(s.get("level", 1)))["hp"]
        team_list.append(f"{active} {suimon_full_name(s)} Lv.{s.get('level',1)} HP {hp}/{max_hp}")
    await update.message.reply_text(
        "🎒 <b>Inventory</b>\n\n"
        f"🧿 Suiballs: <b>{balls}</b> (daily +{get_daily_suiballs()}, cap {get_suiball_cap()})\n"
        f"🥅 Net Balls: <b>{net_balls}</b> (daily +{DAILY_NETBALLS}, cap {NETBALL_CAP})\n\n"
        "📦 <b>Your Suimon Team:</b>\n" + "\n".join(team_list if team_list else ["No Suimon yet."]),
        reply_markup=main_menu_kb(user), parse_mode="HTML"
    )

async def heal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    items = get_owned_suimon_list(user)
    if not items:
        await update.message.reply_text("You have no Suimon.", reply_markup=main_menu_kb(user))
        return
    balls = int(players[user].get("suiballs", 0))
    if balls <= 0:
        await update.message.reply_text(f"❌ No Suiballs. You get {DAILY_SUIBALLS}/day.", reply_markup=main_menu_kb(user))
        return

    kb = []
    for i, s in enumerate(items):
        cur_hp = s.get("hp", 0)
        max_hp = get_stats(s["species"], int(s.get("level", 1)))["hp"]
        status = "✅" if cur_hp >= max_hp else "❤️‍🩹"
        label = f"{status} {suimon_full_name(s)} ({cur_hp}/{max_hp})"
        kb.append([InlineKeyboardButton(label, callback_data=f"heal_select|{i}")])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="menu|home")])
    await update.message.reply_text(
        "🏥 <b>Health Center</b>\nSelect a Suimon to heal (1 Suiball):",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
    )

async def heal_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    await query.answer()
    user_id = str(query.from_user.id)
    global players
    ensure_player(user_id, query.from_user.first_name or "", query.from_user.username)
    ensure_daily(user_id)
    parts = query.data.split("|")
    if len(parts) < 2: return
    idx = int(parts[1])
    items = get_owned_suimon_list(user_id)
    if idx < 0 or idx >= len(items):
        await query.edit_message_text("Invalid selection.", reply_markup=main_menu_kb(user_id))
        return
    s = items[idx]
    max_hp = get_stats(s["species"], int(s.get("level", 1)))["hp"]
    if s.get("hp", 0) >= max_hp:
        await query.edit_message_text("This Suimon is already at full HP.", reply_markup=main_menu_kb(user_id))
        return
    balls = int(players[user_id].get("suiballs", 0))
    if balls <= 0:
        await query.edit_message_text("❌ No Suiballs.", reply_markup=main_menu_kb(user_id))
        return
    players[user_id]["suiballs"] = balls - 1
    heal_suimon_by_index(user_id, idx)
    save_players(players)
    await query.edit_message_text(
        f"🧿 <b>{suimon_full_name(s)}</b> healed to full HP ({max_hp}/{max_hp})!\n"
        f"Remaining Suiballs: {players[user_id]['suiballs']}",
        reply_markup=main_menu_kb(user_id), parse_mode="HTML"
    )

async def cutforsuimon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    p = players[user]
    t = today_str()
    if p.get("last_cut") == t:
        await update.message.reply_text("🩸 Already cut today.", reply_markup=main_menu_kb(user))
        return
    p["suiballs"] = min(get_suiball_cap(), int(p.get("suiballs", 0)) + 1)
    p["last_cut"] = t
    save_players(players)
    await update.message.reply_text("🩸 You cut for the cult and earned 1 Suiball!", reply_markup=main_menu_kb(user))

# ---------- EXPLORE ----------
async def explore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if not update.message: return
    if not get_active_suimon(user):
        await update.message.reply_text("❌ You need at least one Suimon to explore.", reply_markup=main_menu_kb(user))
        return

    kb = []
    for key, world in WORLDS.items():
        last = players[user].get(f"explore_{key}_date")
        cooldown = (last == today_str())
        label = f"{world['emoji']} {world['name']} {'✅' if cooldown else '🕒'}"
        kb.append([InlineKeyboardButton(label, callback_data=f"explore_world|{key}")])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="menu|home")])
    await update.message.reply_text("🌍 <b>Choose a world to explore:</b>\n(Each world once per day)", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def explore_world_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    await query.answer()
    user_id = str(query.from_user.id)
    ensure_player(user_id, query.from_user.first_name or "", query.from_user.username)
    ensure_daily(user_id)
    data = query.data.split("|")
    if len(data) < 2: return
    world_key = data[1]
    world = WORLDS.get(world_key)
    if not world:
        await query.edit_message_text("World not found.")
        return

    p = players[user_id]
    cooldown_key = f"explore_{world_key}_date"
    if p.get(cooldown_key) == today_str():
        await query.edit_message_text(f"⏳ You already explored the {world['name']} today.", reply_markup=main_menu_kb(user_id))
        return

    encounter = random.random() < world["encounter_chance"]
    if not encounter:
        p[cooldown_key] = today_str()
        save_players(players)
        await query.edit_message_text(
            f"{world['emoji']} You explore the <b>{world['name']}</b>...\n\n{world['flavor']}\n\n"
            "No wild Suimon encountered. Try again tomorrow!",
            reply_markup=main_menu_kb(user_id), parse_mode="HTML"
        )
        return

    wild_species = random.choice(world["suimon"])
    wild_data = CHAMPS[wild_species]
    text = (
        f"{world['emoji']} Exploring <b>{world['name']}</b>...\n\n"
        f"🌿 A wild <b>{wild_data['display']}</b> appeared!\n"
        f"Type: {TYPE_EMOJI[wild_data['type']]}\n\n"
        "Do you want to catch it? (Costs 1 Net Ball, 50% catch rate)"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Catch", callback_data=f"catch|{world_key}|{wild_species}"),
         InlineKeyboardButton("🏃 Flee", callback_data=f"explore_flee|{world_key}")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

async def catch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    await query.answer()
    user_id = str(query.from_user.id)
    p = players.setdefault(user_id, {})
    data = query.data.split("|")
    if len(data) < 3: return
    world_key = data[1]
    wild_species = data[2]
    world = WORLDS.get(world_key)

    cooldown_key = f"explore_{world_key}_date"
    if p.get(cooldown_key) == today_str():
        await query.edit_message_text("This world is already completed today.", reply_markup=main_menu_kb(user_id))
        return

    net_balls = int(p.get("net_balls", 0))
    if net_balls <= 0:
        await query.edit_message_text("❌ No Net Balls! Wait for daily replenishment.", reply_markup=main_menu_kb(user_id))
        return

    p["net_balls"] = net_balls - 1
    p[cooldown_key] = today_str()
    caught = random.random() < 0.5

    if caught:
        new_s = {
            "species": wild_species,
            "nickname": None,
            "level": 1,
            "xp": 0,
            "hp": get_stats(wild_species, 1)["hp"],
            "wins": 0,
            "losses": 0,
        }
        p.setdefault("owned_suimon", []).append(new_s)
        # Aktiv setzen auf das neue Suimon, damit /name es benennt
        new_idx = len(p["owned_suimon"]) - 1
        p["active_suimon"] = new_idx
        save_players(players)
        start_nickname_prompt(user_id)
        await query.edit_message_text(
            f"🎉 <b>{CHAMPS[wild_species]['display']}</b> caught! Added to your team.\n\n"
            "📝 <b>Name your new Suimon</b>\n"
            "Use <code>/name YourName</code> to give it a nickname.",
            naming_prompt_kb(), parse_mode="HTML"
        )
    else:
        save_players(players)
        await query.edit_message_text(
            f"💨 The wild <b>{CHAMPS[wild_species]['display']}</b> escaped! Better luck next time.",
            reply_markup=main_menu_kb(user_id), parse_mode="HTML"
        )

async def explore_flee_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    await query.answer()
    user_id = str(query.from_user.id)
    world_key = query.data.split("|")[1]
    p = players[user_id]
    p[f"explore_{world_key}_date"] = today_str()
    save_players(players)
    await query.edit_message_text("🏃 You fled. World complete for today.", reply_markup=main_menu_kb(user_id))

# ---------- PVP ----------
async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    user = await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(user):
        await update.message.reply_text(nickname_required_text(user), reply_markup=naming_prompt_kb(), parse_mode="HTML")
        return
    chat = update.effective_chat
    if not chat or not update.message: return
    chat_id = int(chat.id)
    if not get_active_suimon(user):
        await update.message.reply_text("⚠️ You need at least one named Suimon.", reply_markup=main_menu_kb(user))
        return

    eligible = [uid for uid in _eligible_players_in_chat(chat_id) if uid != user]
    if not eligible:
        await update.message.reply_text("No opponents in this chat yet.", reply_markup=main_menu_kb(user))
        return

    target = _parse_target_user_id(update, context)
    if len(eligible) == 1:
        target = eligible[0]
    elif not target or target not in eligible:
        await update.message.reply_text("⚔️ Multiple opponents. Reply to a player or use /fight @Name.", reply_markup=main_menu_kb(user))
        return

    now = time.monotonic()
    for k in list(PENDING_CHALLENGES.keys()):
        if k[0] == chat_id and PENDING_CHALLENGES[k].get("from") == user:
            if now - PENDING_CHALLENGES[k].get("ts_mono", 0) > CHALLENGE_TIMEOUT:
                PENDING_CHALLENGES.pop(k, None)

    existing = PENDING_CHALLENGES.get((chat_id, target))
    if existing and now - existing.get("ts_mono", 0) < CHALLENGE_TIMEOUT:
        await update.message.reply_text(
            f"⏳ <b>{html.escape(display_name(target))}</b> already has a pending challenge.",
            parse_mode="HTML", reply_markup=main_menu_kb(user)
        )
        return

    PENDING_CHALLENGES[(chat_id, target)] = {"from": user, "ts": datetime.now(TZ).isoformat(), "ts_mono": now}

    challenger_name = display_name(user)
    target_name = display_name(target)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"suimon_accept|{user}|{target}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"suimon_decline|{user}|{target}"),
    ]])

    sent_msg = await update.message.reply_text(
        f"⚔️ <b>{html.escape(challenger_name)}</b> challenges <b>{html.escape(target_name)}</b>!\n\n"
        f"<b>{html.escape(target_name)}</b>, do you accept?\n⏳ Expires in {CHALLENGE_TIMEOUT}s.",
        reply_markup=kb, parse_mode="HTML",
    )

    async def _expire():
        await asyncio.sleep(CHALLENGE_TIMEOUT)
        key = (chat_id, target)
        if PENDING_CHALLENGES.get(key, {}).get("from") == user:
            PENDING_CHALLENGES.pop(key, None)
            try:
                await sent_msg.edit_text(
                    f"⏰ Challenge expired! {html.escape(challenger_name)} vs {html.escape(target_name)}.",
                    reply_markup=None, parse_mode="HTML"
                )
            except Exception:
                pass
    asyncio.create_task(_expire())

async def challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    query = update.callback_query
    if not query or not query.message: return
    await query.answer()
    data = query.data.split("|")
    if len(data) < 3: return
    action, challenger, target = data[0], data[1], data[2]
    chat_id = int(query.message.chat.id)
    clicker = str(query.from_user.id)

    if clicker != target:
        await query.answer("This challenge is not for you.", show_alert=True)
        return

    key = (chat_id, clicker)
    payload = PENDING_CHALLENGES.get(key)
    if not payload:
        await query.edit_message_text("⚠️ Challenge expired or already handled.")
        return
    if time.monotonic() - payload.get("ts_mono", 0) > CHALLENGE_TIMEOUT:
        PENDING_CHALLENGES.pop(key, None)
        await query.edit_message_text("⏰ Challenge expired.")
        return
    if str(payload.get("from")) != str(challenger):
        PENDING_CHALLENGES.pop(key, None)
        await query.edit_message_text("⚠️ Mismatch. Challenge again.")
        return

    PENDING_CHALLENGES.pop(key, None)

    if action.startswith("suimon_decline"):
        await query.edit_message_text("❌ Challenge declined.")
        return
    if not action.startswith("suimon_accept"):
        return

    await query.edit_message_text("✅ Accepted! Challenger, choose your Suimon first...")

    PENDING_SELECTION[chat_id] = {
        "challenger": str(challenger),
        "opponent": clicker,
        "challenger_suimon": None,
        "opponent_suimon": None,
        "message_id": query.message.message_id,
    }

    items = get_owned_suimon_list(str(challenger))
    kb = []
    for i, s in enumerate(items):
        fainted = "💀" if s["hp"] <= 0 else ""
        label = f"{suimon_full_name(s)} Lv.{s['level']} ({s['hp']}/{get_stats(s['species'], s['level'])['hp']}) {fainted}"
        kb.append([InlineKeyboardButton(label, callback_data=f"select_suimon|challenger|{i}")])
    try:
        await query.message.reply_text(
            f"🎯 <b>{html.escape(display_name(str(challenger)))}</b>, choose your Suimon:",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
    except Exception:
        pass

async def select_suimon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data.split("|")
    if len(data) < 3: return
    role = data[1]
    idx = int(data[2])
    chat_id = int(query.message.chat.id)

    sel = PENDING_SELECTION.get(chat_id)
    if not sel:
        await query.edit_message_text("Selection expired.")
        return

    if role == "challenger" and user_id != sel["challenger"]:
        await query.answer("Not your selection.", show_alert=True)
        return
    if role == "opponent" and user_id != sel["opponent"]:
        await query.answer("Not your selection.", show_alert=True)
        return

    items = get_owned_suimon_list(user_id)
    if idx < 0 or idx >= len(items):
        await query.answer("Invalid Suimon.")
        return

    if items[idx]["hp"] <= 0:
        await query.answer("This Suimon is fainted! Choose a healthy one.", show_alert=True)
        return

    sel[f"{role}_suimon"] = idx

    if role == "challenger":
        opp = sel["opponent"]
        items2 = get_owned_suimon_list(opp)
        kb = []
        for i, s in enumerate(items2):
            fainted = "💀" if s["hp"] <= 0 else ""
            label = f"{suimon_full_name(s)} Lv.{s['level']} ({s['hp']}/{get_stats(s['species'], s['level'])['hp']}) {fainted}"
            kb.append([InlineKeyboardButton(label, callback_data=f"select_suimon|opponent|{i}")])
        await query.edit_message_text(
            f"✅ Challenger selected {suimon_full_name(items[idx])}!\n\n"
            f"🎯 Now <b>{html.escape(display_name(opp))}</b>, choose your Suimon:",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
    else:
        await query.edit_message_text("✅ Both Suimon selected! Battle starting...")
        await _start_battle_with_suimon(chat_id, sel, context)

async def _start_battle_with_suimon(chat_id: int, sel: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE):
    global players
    players = load_players()
    user = sel["challenger"]
    opponent = sel["opponent"]
    u_idx = sel["challenger_suimon"]
    o_idx = sel["opponent_suimon"]

    if chat_id in ACTIVE_BATTLES:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ A battle is already running.")
        return

    u_s = players[user]["owned_suimon"][u_idx]
    o_s = players[opponent]["owned_suimon"][o_idx]

    if u_s["hp"] <= 0:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ {display_name(user)}'s Suimon is fainted.")
        return
    if o_s["hp"] <= 0:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ {display_name(opponent)}'s Suimon is fainted.")
        return

    ACTIVE_BATTLES.add(chat_id)
    msg = await context.bot.send_message(chat_id=chat_id, text="⚔️ BATTLE START (loading...)")
    message_id = msg.message_id

    c1_key = u_s["species"]
    c2_key = o_s["species"]
    lv1 = int(u_s["level"])
    lv2 = int(o_s["level"])
    s1 = get_stats(c1_key, lv1)
    s2 = get_stats(c2_key, lv2)

    champ1 = {"hp": int(u_s["hp"]), "max_hp": s1["hp"], "atk": s1["atk"], "def": s1["def"], "spd": s1["spd"],
              "burn_turns": 0, "sleep_turns": 0, "confuse_turns": 0, "poison_turns": 0,
              "wet_dream_turns": 0, "wet_dream_uses_left": 2 if c1_key == "suimander" else 0,
              "has_slept": False, "last_used_sleep": False, "stun_turns": 0}
    champ2 = {"hp": int(o_s["hp"]), "max_hp": s2["hp"], "atk": s2["atk"], "def": s2["def"], "spd": s2["spd"],
              "burn_turns": 0, "sleep_turns": 0, "confuse_turns": 0, "poison_turns": 0,
              "wet_dream_turns": 0, "wet_dream_uses_left": 2 if c2_key == "suimander" else 0,
              "has_slept": False, "last_used_sleep": False, "stun_turns": 0}

    p1_name = display_name(user, "Player A")
    p2_name = display_name(opponent, "Player B")

    state = {
        "message_id": message_id,
        "log_lines": [],
        "last_reposition": 0.0,
        "reposition_cooldown": REPOSITION_COOLDOWN,
        "last_rendered_text": "",
        "last_reply_markup": None,
        "resolving": False,
        "resolving_since": 0.0,
        "user": user, "opponent": opponent,
        "u_idx": u_idx, "o_idx": o_idx,
        "p1_name": p1_name, "p2_name": p2_name,
        "c1_key": c1_key, "c2_key": c2_key,
        "lv1": lv1, "lv2": lv2,
        "champ1": champ1, "champ2": champ2,
        "c1_label": f"{p1_name} - {suimon_full_name(u_s)} (Lv.{lv1})",
        "c2_label": f"{p2_name} - {suimon_full_name(o_s)} (Lv.{lv2})",
        "turn": 0, "round": 0, "actions": 0, "max_rounds": 24,
        "suiballs_used": {},
        "last_move_ts": time.monotonic(),
    }
    BATTLES[chat_id] = state

    await _battle_push_message(chat_id, state, context, "⚔️ BATTLE START ⚔️", delay=0.25, reply_markup=None, force_reposition=True)
    await _battle_push_message(chat_id, state, context, f"👤 {p1_name} sends out {suimon_full_name(u_s)}!", delay=0.30)
    await _battle_push_message(chat_id, state, context, f"👤 {p2_name} sends out {suimon_full_name(o_s)}!", delay=0.30)
    await _battle_push_hud(chat_id, state, context, delay=0.30)
    for t in ("3…", "2…", "1…", "GO!"):
        await _battle_push_message(chat_id, state, context, t, delay=COUNTDOWN_STEP_DELAY)
    first = pick_first_attacker(int(champ1["spd"]), int(champ2["spd"]))
    state["turn"] = first
    starter_name = suimon_full_name(u_s) if first == 0 else suimon_full_name(o_s)
    await _battle_push_message(chat_id, state, context, f"🏁 {starter_name} moves first!", delay=0.35)
    await _battle_prompt_turn(chat_id, state, context)

# ---------- ADMIN ----------
async def change_champ(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    admin = await _bootstrap_user(update)
    if not update.message or not update.effective_chat: return
    if not await is_privileged_user(context.bot, int(update.effective_chat.id), int(admin)):
        await update.message.reply_text("❌ Only privileged users.")
        return
    target = _parse_target_user_id(update, context)
    if not target or target not in players:
        await update.message.reply_text("Player not found.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /changechamp @user champname")
        return
    new_champ = champ_key_from_input(context.args[-1])
    if not new_champ:
        await update.message.reply_text("Unknown champ.")
        return
    items = players[target].setdefault("owned_suimon", [])
    if items:
        active = get_active_suimon_index(target)
        items[active]["species"] = new_champ
        items[active]["hp"] = get_stats(new_champ, int(items[active].get("level", 1)))["hp"]
    else:
        items.append({"species": new_champ, "nickname": None, "level": 1, "xp": 0, "hp": get_stats(new_champ, 1)["hp"], "wins": 0, "losses": 0})
    save_players(players)
    await update.message.reply_text(f"✅ {display_name(target)}'s active Suimon changed.")

async def tournamenton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    admin = await _bootstrap_user(update)
    if not update.message or not update.effective_chat: return
    if not await is_privileged_user(context.bot, int(update.effective_chat.id), int(admin)):
        await update.message.reply_text("❌ Only privileged users.")
        return
    tournament_state["active"] = True
    save_tournament(tournament_state)
    for uid in players:
        players[uid]["suiballs"] = 100
    save_players(players)
    await update.message.reply_text("🏆 TOURNAMENT STARTED! Everyone gets 100 Suiballs.", parse_mode="HTML")

async def tournamentoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    admin = await _bootstrap_user(update)
    if not update.message or not update.effective_chat: return
    if not await is_privileged_user(context.bot, int(update.effective_chat.id), int(admin)):
        await update.message.reply_text("❌ Only privileged users.")
        return
    tournament_state["active"] = False
    save_tournament(tournament_state)
    top = get_leaderboard(10)
    if top:
        winner_id = top[0][0]
        players[winner_id].setdefault("badges", []).append("earth")
        save_players(players)
        await update.message.reply_text(f"🏁 Tournament over! Winner: {display_name(winner_id)} gets Earth Badge! 🌍", parse_mode="HTML")
    else:
        await update.message.reply_text("Tournament ended. No players.")

async def xpboost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    admin = await _bootstrap_user(update)
    if not await is_privileged_user(context.bot, int(update.effective_chat.id), int(admin)):
        await update.message.reply_text("❌ Only privileged users.")
        return
    tournament_state["xp_boost_expires"] = time.time() + 7200
    save_tournament(tournament_state)
    await update.message.reply_text("⚡ XP BOOST activated for 2 hours! +50% XP!")

async def endfight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    admin = await _bootstrap_user(update)
    if not await is_privileged_user(context.bot, int(update.effective_chat.id), int(admin)):
        await update.message.reply_text("❌ Only privileged users.")
        return
    state = BATTLES.get(int(update.effective_chat.id))
    if not state:
        await update.message.reply_text("No active battle.")
        return
    winner_id = state["user"]
    if context.args:
        target, _ = _parse_target_from_args(int(update.effective_chat.id), context.args)
        if target in (state["user"], state["opponent"]):
            winner_id = target
    loser_id = state["opponent"] if winner_id == state["user"] else state["user"]
    await _end_battle(int(update.effective_chat.id), state, context, winner=winner_id, loser=loser_id)
    await update.message.reply_text(f"🛑 Admin ended fight. Winner: {display_name(winner_id)}")

async def give_suiball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    giver = await _bootstrap_user(update)
    if not update.message or not update.effective_chat: return
    if not await is_privileged_user(context.bot, int(update.effective_chat.id), int(giver)):
        await update.message.reply_text("❌ Only privileged users.")
        return
    target, amount = _parse_target_and_amount(int(update.effective_chat.id), context.args)
    if not target or amount is None or amount <= 0:
        await update.message.reply_text("Usage: /givesuiball @user amount")
        return
    before = int(players.get(target, {}).get("suiballs", 0))
    players[target]["suiballs"] = min(999, before + amount)
    save_players(players)
    await update.message.reply_text(f"✅ Gave {amount} Suiballs to {display_name(target)}.")

async def remove_suiball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    giver = await _bootstrap_user(update)
    if not update.message or not update.effective_chat: return
    if not await is_privileged_user(context.bot, int(update.effective_chat.id), int(giver)):
        await update.message.reply_text("❌ Only privileged users.")
        return
    target, amount = _parse_target_and_amount(int(update.effective_chat.id), context.args)
    if not target or amount is None or amount <= 0:
        await update.message.reply_text("Usage: /takesuiball @user amount")
        return
    before = int(players.get(target, {}).get("suiballs", 0))
    players[target]["suiballs"] = max(0, before - amount)
    save_players(players)
    await update.message.reply_text(f"✅ Removed {amount} Suiballs from {display_name(target)}.")

PENDING_RESETS: Dict[str, float] = {}
async def reset_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    caller = await _bootstrap_user(update)
    if not update.message or not update.effective_chat: return
    if not await is_privileged_user(context.bot, int(update.effective_chat.id), int(caller)):
        await update.message.reply_text("❌ Only privileged users.")
        return
    now = time.monotonic()
    if PENDING_RESETS.get(caller) and (now - PENDING_RESETS[caller]) < 30:
        PENDING_RESETS.pop(caller, None)
        for uid, p in players.items():
            for s in p.get("owned_suimon", []):
                s["level"] = 1
                s["xp"] = 0
                s["wins"] = 0
                s["losses"] = 0
                s["hp"] = get_stats(s["species"], 1)["hp"]
            p["suiballs"] = DAILY_SUIBALLS
            p["wins"] = 0
            p["losses"] = 0
        save_players(players)
        await update.message.reply_text("♻️ Leaderboard reset complete.")
    else:
        PENDING_RESETS[caller] = now
        await update.message.reply_text("Type /resetleaderboard again within 30s to confirm.")

# ---------- MENU CALLBACKS ----------
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    query = update.callback_query
    if not query or not query.data: return
    await query.answer()
    user_id = str(query.from_user.id)
    ensure_player(user_id, (query.from_user.first_name or "Player").strip(), query.from_user.username)
    if query.message:
        _remember_chat(user_id, int(query.message.chat.id))
    ensure_daily(user_id)
    save_players(players)

    action = query.data.split("|", 1)[1] if "|" in query.data else "home"

    if action == "profile":
        s = get_active_suimon(user_id)
        if not s:
            await edit_menu_message(query, "No Suimon yet.", main_menu_kb(user_id))
            return
        p = players[user_id]
        lv = int(s.get("level", 1))
        stats = get_stats(s["species"], lv)
        cur_hp = s.get("hp", stats["hp"])
        await edit_menu_message(query,
            f"🪪 Trainer Card\n\n{suimon_full_name(s)} Lv.{lv}\nHP: {cur_hp}/{stats['hp']}",
            main_menu_kb(user_id))
        return
    if action == "leaderboard":
        await edit_menu_message(query, build_rankings_text(user_id, 10), main_menu_kb(user_id))
        return
    if action == "inventory":
        p = players[user_id]
        balls = int(p.get("suiballs", 0))
        net = int(p.get("net_balls", 0))
        await edit_menu_message(query, f"🎒 Inventory\n🧿 Suiballs: {balls}\n🥅 Net Balls: {net}", main_menu_kb(user_id))
        return
    if action == "heal":
        # DIREKT Heal-Auswahl anzeigen, ohne Message-Delete
        items = get_owned_suimon_list(user_id)
        if not items:
            await edit_menu_message(query, "You have no Suimon.", main_menu_kb(user_id))
            return
        balls = int(players[user_id].get("suiballs", 0))
        if balls <= 0:
            await edit_menu_message(query, f"❌ No Suiballs. You get {DAILY_SUIBALLS}/day.", main_menu_kb(user_id))
            return
        kb = []
        for i, s in enumerate(items):
            cur_hp = s.get("hp", 0)
            max_hp = get_stats(s["species"], int(s.get("level", 1)))["hp"]
            status = "✅" if cur_hp >= max_hp else "❤️‍🩹"
            label = f"{status} {suimon_full_name(s)} ({cur_hp}/{max_hp})"
            kb.append([InlineKeyboardButton(label, callback_data=f"heal_select|{i}")])
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="menu|home")])
        await edit_menu_message(query, "🏥 <b>Health Center</b>\nSelect a Suimon to heal (1 Suiball):", InlineKeyboardMarkup(kb))
        return
    if action == "explore":
        # DIREKT Explore-Auswahl anzeigen, ohne Message-Delete
        if not get_active_suimon(user_id):
            await edit_menu_message(query, "❌ You need at least one Suimon to explore.", main_menu_kb(user_id))
            return
        kb = []
        for key, world in WORLDS.items():
            last = players[user_id].get(f"explore_{key}_date")
            cooldown = (last == today_str())
            label = f"{world['emoji']} {world['name']} {'✅' if cooldown else '🕒'}"
            kb.append([InlineKeyboardButton(label, callback_data=f"explore_world|{key}")])
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="menu|home")])
        await edit_menu_message(query, "🌍 <b>Choose a world to explore:</b>\n(Each world once per day)", InlineKeyboardMarkup(kb))
        return
    if action == "champs":
        lines = ["📜 Starter Champs", ""]
        for key in ["basaurimon", "suimander", "suiqrtle"]:
            c = CHAMPS[key]
            moves = ", ".join([m["name"] for m in c["moves"]])
            lines.append(f"{TYPE_EMOJI[c['type']]} {c['display']}  — {c['type']}")
            lines.append(f"   Moves: {moves}")
            lines.append("")
        await edit_menu_message(query, "🌟 Choose your starter\n\n" + "\n".join(lines), choose_champ_kb())
        return
    if action == "fight":
        await edit_menu_message(query, "⚔️ Use /fight @username to challenge someone.", main_menu_kb(user_id))
        return
    await edit_menu_message(query, fancy_menu_caption(user_id), main_menu_kb(user_id))

async def choose_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context): return
    query = update.callback_query
    if not query: return
    await query.answer()
    user = await _bootstrap_user(update)
    champ_key = query.data.split("|", 1)[1].strip()
    if champ_key not in ("basaurimon", "suimander", "suiqrtle"):
        await edit_menu_message(query, "Unknown champ.", main_menu_kb(user))
        return
    if get_owned_suimon_list(user):
        await edit_menu_message(query, "Already have a starter.", main_menu_kb(user))
        return
    c = CHAMPS[champ_key]
    new_s = {"species": champ_key, "nickname": None, "level": 1, "xp": 0, "hp": get_stats(champ_key, 1)["hp"], "wins": 0, "losses": 0}
    players[user]["owned_suimon"] = [new_s]
    players[user]["active_suimon"] = 0
    players[user]["suiballs"] = max(int(players[user].get("suiballs", 0)), 1)
    start_nickname_prompt(user)
    save_players(players)
    await edit_menu_message(query,
        f"📝 Selected {c['display']}!\nUse /name YourName to nickname it.",
        naming_prompt_kb())

# =========================
# MAIN
# =========================

def main():
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN":
        raise RuntimeError("TOKEN is not set.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("intro", intro))
    app.add_handler(CommandHandler("champs", champs_cmd))
    app.add_handler(CommandHandler("choose", choose))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("name", nickname))
    app.add_handler(CommandHandler("nickname", nickname))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nickname_text_reply))
    app.add_handler(CommandHandler(["rankings", "leaderboard"], leaderboard))
    app.add_handler(CommandHandler("inventory", inventory))
    app.add_handler(CommandHandler("heal", heal))
    app.add_handler(CommandHandler("explore", explore))
    app.add_handler(CommandHandler("cutforsuimon", cutforsuimon))
    app.add_handler(CommandHandler("givesuiball", give_suiball))
    app.add_handler(CommandHandler("takesuiball", remove_suiball))
    app.add_handler(CommandHandler("resetleaderboard", reset_leaderboard))
    app.add_handler(CommandHandler("tournamenton", tournamenton))
    app.add_handler(CommandHandler("tournamentoff", tournamentoff))
    app.add_handler(CommandHandler("changechamp", change_champ))
    app.add_handler(CommandHandler("xpboost", xpboost))
    app.add_handler(CommandHandler("endfight", endfight))
    app.add_handler(CommandHandler("fight", fight))

    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu(?:\||$)"))
    app.add_handler(CallbackQueryHandler(choose_callback, pattern=r"^choose\|"))
    app.add_handler(CallbackQueryHandler(challenge_callback, pattern=r"^suimon_(accept|decline)\|"))
    app.add_handler(CallbackQueryHandler(select_suimon_callback, pattern=r"^select_suimon\|"))
    app.add_handler(CallbackQueryHandler(explore_world_callback, pattern=r"^explore_world\|"))
    app.add_handler(CallbackQueryHandler(catch_callback, pattern=r"^catch\|"))
    app.add_handler(CallbackQueryHandler(explore_flee_callback, pattern=r"^explore_flee\|"))
    app.add_handler(CallbackQueryHandler(heal_select_callback, pattern=r"^heal_select\|"))
    app.add_handler(CallbackQueryHandler(battle_move_callback, pattern=r"^(mv|ff|heal|noop)\|"))

    async def _afk_loop(application):
        while True:
            await asyncio.sleep(30)
            try:
                await _afk_watcher(application)
            except Exception as e:
                print(f"[AFK loop error] {e}")

    async def post_init(application):
        asyncio.create_task(_afk_loop(application))

    app.post_init = post_init

    print("Suimon Arena bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()