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
# Only these user IDs + the Telegram group owner can use privileged admin commands
PRIVILEGED_USER_IDS = {1638084297, 7105730933, 6274470012}
MENU_IMAGE_CANDIDATES = ("logo.JPG", "logo.jpg", "logo.png", "menu.jpg", "menu.png")

# In-memory session state (resets if the bot restarts)
# Keyed by (chat_id, target_user_id) -> {"from": challenger_id, "ts": iso}
PENDING_CHALLENGES: Dict[Tuple[int, str], Dict[str, Any]] = {}
CHALLENGE_TIMEOUT = 60  # seconds

# Active battles per chat (prevents overlap)
ACTIVE_BATTLES: set[int] = set()

# Live battle state (interactive move selection)
# Keyed by chat_id -> state dict
BATTLES: Dict[int, Dict[str, Any]] = {}

# -------------------------
# Text pacing (seconds)
# -------------------------
INTRO_DELAY = 0.8
REPOSITION_COOLDOWN = 3.5
COUNTDOWN_STEP_DELAY = 0.55
ACTION_DELAY = 0.70
HUD_DELAY = 0.45
END_DELAY = 0.8

# Keep Telegram message length manageable
MAX_LINES_SHOWN = 70
MAX_MESSAGE_CHARS = 3800  # keep under Telegram 4096 edit limit

# Daily items
DAILY_SUIBALLS = 2
DAILY_SUIBALLS_TOURNAMENT = 10
SUIBALL_CAP = 5
SUIBALL_CAP_TOURNAMENT = 100
MAX_LEVEL = 10
TZ = timezone.utc

# Tournament state (persisted in tournament.json)
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
# CHAMPS (Suimon Starter Set)
# =========================
# Type cycle:
# Fire > Nature, Nature > Water, Water > Fire
CHAMPS: Dict[str, Dict[str, Any]] = {
    "basaurimon": {
        "display": "Basaurimon",
        "type": "nature",
        "base": {"hp": 155, "atk": 24, "def": 11, "spd": 9},
        "moves": [
            {"name": "Vine Whip", "kind": "damage", "power": 48, "acc": 0.95, "text": [
                "whips out something long and flexible — no lube included!",
                "snaps its vine like a dominatrix on a coke binge!",
                "lashes harder than a dealer who wasn't paid on time!",
            ]},
            {"name": "Needle Rain", "kind": "damage_poison", "power": 36, "acc": 0.92, "poison_chance": 0.40, "poison_turns": (2, 3), "crit_bonus": 0.08, "text": [
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
            {"name": "Sleep Spore", "kind": "status_sleep", "power": 0, "acc": 0.75, "sleep_turns": (1, 2), "text": [
                "pulls out Cannabis indica — the good stuff, not the street trash!",
                "hotboxes the entire arena with primo kush!",
                "deploys Sleep Spore — straight from the cult's private stash!",
            ]},
        ],
    },
    "suimander": {
        "display": "Suimander",
        "type": "fire",
        "base": {"hp": 154, "atk": 24, "def": 10, "spd": 12},
        "moves": [
            {"name": "Wet Dream", "kind": "status_wet_dream", "power": 0, "acc": 0.90, "wet_dream_turns": (3, 4), "text": [
                "slips something into their drink — they don't notice until they pisses themselves mid-fight!",
                "whispers something in their ear — whatever it was, they pisses themselves instantly!",
                "exhales cult smoke directly into their mouth — they pisses themselves before it even kicks in!",
                "doses them with something that has no street name — they pisses themselves and forgets why!",
                "reaches into the ritual bag and pulls out the good stuff — opponent pisses themselves on impact!",
            ]},
            {"name": "Flamethrower", "kind": "damage", "power": 55, "acc": 0.90, "text": [
                "blasts a stream hotter than a speedball hitting wrong!",
                "turns up the heat like cooking meth without ventilation!",
                "scorches everything — size matters here and it delivered!",
            ]},
            {"name": "Inferno Claw", "kind": "damage_highcrit", "power": 48, "acc": 0.92, "crit_bonus": 0.10, "text": [
                "scratches marks that'll need explaining to your parole officer!",
                "carves deep — leaves marks the cult will be proud of!",
                "rips through like a bad breakup — slow, painful, and very personal!",
            ]},
            {"name": "Will-O-Wisp", "kind": "status_burn", "power": 0, "acc": 0.90, "burn_turns": (2, 3), "text": [
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
            {"name": "Water Pulse", "kind": "status_confuse", "power": 0, "acc": 0.80, "confuse_turns": (1, 2), "confuse_rare_chance": 0.30, "text": [
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
}

TYPE_EMOJI = {"fire": "🔥", "water": "💧", "nature": "🌿"}
STATUS_EMOJI = {"burn": "🔥", "sleep": "💤", "confuse": "🌀", "poison": "☠️", "wet_dream": "😨"}

CHAMPS_BY_TYPE = {
    "fire": {"strong_against": "nature", "weak_to": "water"},
    "water": {"strong_against": "fire", "weak_to": "nature"},
    "nature": {"strong_against": "water", "weak_to": "fire"},
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


def fancy_menu_caption(user_id: str) -> str:
    p = players.get(user_id, {})
    champ_key = p.get("champ")
    title = f"🧭 <b>{html.escape(display_name(user_id))}'s Menu</b>"
    if champ_key not in CHAMPS:
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

    level = int(p.get("level", 1))
    xp = int(p.get("xp", 0))
    need = xp_needed(level)
    wins = int(p.get("wins", 0))
    losses = int(p.get("losses", 0))
    balls = int(p.get("suiballs", 0))
    stats = get_stats(champ_key, level)
    cur_hp = get_or_init_current_hp(user_id)
    champ_label = html.escape(champ_full_name_for_player(user_id, champ_key))
    type_icon = TYPE_EMOJI.get(champ_from_key(champ_key)["type"], "✨")
    return (
        f"{title}\n\n"
        f"{type_icon} <b>{champ_label}</b> • Lv.<b>{level}</b>\n"
        f"❤️ <b>HP:</b> {cur_hp}/{stats['hp']}\n"
        f"✨ <b>XP:</b> {xp}/{need if level < MAX_LEVEL else 0}\n"
        f"⚔️ <b>Record:</b> {wins}W / {losses}L\n"
        f"🎒 <b>Suiballs:</b> {balls}\n\n"
        "Choose your next move below."
    )


# =========================
# STORAGE
# =========================

def load_players() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        # Corrupt JSON shouldn't brick the bot
        return {}

def save_players(players_: Dict[str, Any]) -> None:
    # Atomic write to avoid broken json on crash
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(players_, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

players: Dict[str, Any] = load_players()

# =========================
# CORE HELPERS
# =========================

def today_str() -> str:
    return datetime.now(TZ).date().isoformat()

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def champ_from_key(key: str) -> Dict[str, Any]:
    return CHAMPS[key]

def display_name(player_id: str, fallback: str = "Player") -> str:
    p = players.get(player_id, {})
    return (p.get("name") or fallback).strip()

def get_champ_nickname(player_id: str) -> Optional[str]:
    p = players.get(player_id, {})
    nick = str(p.get("champ_nickname") or "").strip()
    return nick or None

def champ_display_for_player(player_id: str, champ_key: Optional[str] = None) -> str:
    p = players.get(player_id, {})
    key = champ_key or p.get("champ")
    if key not in CHAMPS:
        return "Unknown"
    nick = get_champ_nickname(player_id)
    base_name = champ_from_key(key)["display"]
    return nick or base_name

def champ_full_name_for_player(player_id: str, champ_key: Optional[str] = None) -> str:
    p = players.get(player_id, {})
    key = champ_key or p.get("champ")
    if key not in CHAMPS:
        return "Unknown"
    base_name = champ_from_key(key)["display"]
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
    p = players.get(player_id, {})
    return p.get("champ") in CHAMPS and bool(get_champ_nickname(player_id))

def menu_title(player_id: str) -> str:
    return f"🧭 <b>{html.escape(display_name(player_id))}'s Menu</b>"

def naming_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu|home")]])

def nickname_required_text(player_id: str) -> str:
    p = players.get(player_id, {})
    champ_key = p.get("champ")
    if champ_key not in CHAMPS:
        return "Choose your champ first with /choose or Menu → 📜 Champs."
    base_name = champ_from_key(champ_key)["display"]
    return (
        "📝 <b>Name required</b>\n\n"
        f"Your starter is <b>{base_name}</b>.\n\n"
        "🚫 You cannot fight yet. First give your champ a custom name.\n\n"
        "Use <code>/name YourName</code>\n"
        "Example: <code>/name Joyamon</code>"
    )

def start_nickname_prompt(player_id: str) -> None:
    if player_id in players:
        players[player_id]["awaiting_nickname"] = True
        save_players(players)

def clear_nickname_prompt(player_id: str) -> None:
    if player_id in players and players[player_id].get("awaiting_nickname"):
        players[player_id]["awaiting_nickname"] = False
        save_players(players)

def needs_nickname_prompt(player_id: str) -> bool:
    p = players.get(player_id, {})
    return p.get("champ") in CHAMPS and not get_champ_nickname(player_id)

def get_badges_display(user_id: str) -> str:
    badges = players.get(user_id, {}).get("badges", [])
    if not badges:
        return ""
    badge_map = {"cascade": "🌊"}
    return " ".join(badge_map.get(b, "🏅") for b in badges)


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
        "basaur": "basaurimon",
        "basaurimon": "basaurimon",
        "suimander": "suimander",
        "mander": "suimander",
        "suiqrtle": "suiqrtle",
        "squirtle": "suiqrtle",
        "qrtle": "suiqrtle",
    }
    return aliases.get(a)

def get_stats(champ_key: str, level: int) -> Dict[str, int]:
    level = max(1, min(int(level), MAX_LEVEL))
    base = champ_from_key(champ_key)["base"]
    # HP scales +2/level — Lv9 gets +16 HP over Lv1 (ratio ~1.06x, matches DMG ratio)
    hp = int(round(base["hp"] + (level - 1) * 2))
    # ATK scales +0.25/level from Lv1 — low levels hit almost as hard as high levels
    atk = int(round(base["atk"] + (level - 1) * 0.25))
    df = int(round(base["def"] + (level - 1) * 0.3))
    spd = int(round(base["spd"] + (level - 1) * 1))
    return {"hp": hp, "atk": atk, "def": df, "spd": spd}

def normalize_player_state(user_id: str) -> None:
    if user_id not in players:
        return
    p = players[user_id]
    try:
        p["level"] = max(1, min(int(p.get("level", 1)), MAX_LEVEL))
    except Exception:
        p["level"] = 1
    try:
        p["xp"] = max(0, int(p.get("xp", 0)))
    except Exception:
        p["xp"] = 0
    if p["level"] >= MAX_LEVEL:
        p["level"] = MAX_LEVEL
        p["xp"] = 0

def ensure_player(user_id: str, tg_name: str, tg_username: Optional[str] = None) -> None:
    if user_id not in players:
        players[user_id] = {
            "name": tg_name,
            "username": tg_username or "",
            "champ": None,
            "level": 1,
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "suiballs": 0,
            "last_daily": None,
            "hp": None,          # persistent HP
            "chats": [],         # chat ids where player is active
            "champ_nickname": None,
            "awaiting_nickname": False,
        }
    else:
        if tg_name and players[user_id].get("name") != tg_name:
            players[user_id]["name"] = tg_name
        players[user_id]["username"] = tg_username or players[user_id].get("username", "")
    normalize_player_state(user_id)

def ensure_daily(user_id: str) -> bool:
    p = players[user_id]
    t = today_str()
    if p.get("last_daily") == t:
        return False
    current = int(p.get("suiballs", 0))
    p["suiballs"] = min(get_suiball_cap(), current + get_daily_suiballs())
    p["last_daily"] = t
    return True

def get_or_init_current_hp(user_id: str) -> int:
    p = players[user_id]
    champ_key = p.get("champ")
    if champ_key not in CHAMPS:
        return 0
    lv = int(p.get("level", 1))
    max_hp = get_stats(champ_key, lv)["hp"]
    cur = p.get("hp")
    if cur is None:
        p["hp"] = max_hp
        return max_hp
    try:
        cur_int = int(cur)
    except Exception:
        cur_int = max_hp
    return max(0, min(cur_int, max_hp))

def set_current_hp(user_id: str, new_hp: int) -> None:
    p = players[user_id]
    champ_key = p.get("champ")
    if champ_key not in CHAMPS:
        p["hp"] = None
        return
    lv = int(p.get("level", 1))
    max_hp = get_stats(champ_key, lv)["hp"]
    p["hp"] = max(0, min(int(new_hp), max_hp))

def heal_to_full(user_id: str) -> Tuple[int, int]:
    champ_key = players[user_id].get("champ")
    lv = int(players[user_id].get("level", 1))
    max_hp = get_stats(champ_key, lv)["hp"]
    set_current_hp(user_id, max_hp)
    return max_hp, max_hp

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
    """Extra miss chance for the higher-level attacker. 0 if attacker is equal or weaker."""
    gap = attacker_level - defender_level
    if gap <= 0:
        return 0.0
    # +3% per level gap, capped at 15%
    return min(0.15, gap * 0.03)

def calc_damage(attacker_atk: int, defender_def: int, level: int,
                power: int, type_mult_: float, crit_mult: float,
                defender_level: int = 0) -> int:
    effective_atk = max(1, int(attacker_atk))
    effective_def = max(1, int(defender_def))
    # Lv1-5 all use Lv5 factor — identical damage floor
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
        # if sleep just ended, mark as recoverable so Sleep Spore can't be immediately reused
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
    return True, []

def do_move(attacker: Dict[str, Any], defender: Dict[str, Any], a_key: str, d_key: str, a_level: int, move: Dict[str, Any], attacker_name: Optional[str] = None, defender_name: Optional[str] = None, defender_level: int = 0) -> List[str]:
    out: List[str] = []

    a = champ_from_key(a_key)
    d = champ_from_key(d_key)
    a_name = attacker_name or a["display"]
    d_name = defender_name or d["display"]

    # Level-gap miss penalty: higher-level attacker misses more often vs lower-level
    base_miss = 1.0 - float(move.get("acc", 0.9))
    extra_miss = level_gap_miss_penalty(a_level, defender_level)
    effective_miss = min(0.60, base_miss + extra_miss)
    if random.random() < effective_miss:
        out.append(f"{TYPE_EMOJI[a['type']]} {a_name} used {move['name']}!")
        if extra_miss > 0:
            miss_texts = [
                "💨 Missed! Aim like that and even your dealer would drop you!",
                "💨 Missed! Shaking too hard — lay off the meth next time!",
                "💨 Missed! Even a blind junkie shoots straighter than that!",
            ]
        else:
            miss_texts = [
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
        # Cooldown: Sleep Spore can only be used once every 3 turns
        sleep_cooldown_remaining = attacker.get("sleep_spore_cooldown", 0)
        if sleep_cooldown_remaining > 0:
            attacker["sleep_spore_cooldown"] = sleep_cooldown_remaining - 1
            out.append(("html",
                f"🌿 {a_name} reaches for the stash — but the bag's empty! "
                f"Sleep Spore needs {sleep_cooldown_remaining} more turn{'s' if sleep_cooldown_remaining != 1 else ''} to recharge. 💨"
            ))
            return out
        if attacker.get("last_used_sleep", False):
            # used sleep spore twice in a row — backfires
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
        attacker["sleep_spore_cooldown"] = 3  # can't use again for 3 turns
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
        # Direct damage hit (weak but guaranteed)
        mult, eff = type_mult(a["type"], d["type"])
        wet_dream_dmg = calc_damage(
            attacker_atk=int(attacker["atk"]),
            defender_def=int(defender["def"]),
            level=a_level,
            power=28,
            type_mult_=mult,
            crit_mult=1.0,
            defender_level=defender_level,
        )
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

    # attacker used a non-sleep move — reset consecutive sleep tracking
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

    power = int(move.get("power", 40))

    crit_chance = 0.08 + float(move.get("crit_bonus", 0.0))
    crit = random.random() < crit_chance if kind == "damage_highcrit" else (random.random() < 0.08)
    crit_mult = 1.5 if crit else 1.0

    mult, eff = type_mult(a["type"], d["type"])

    dmg = calc_damage(
        attacker_atk=int(attacker["atk"]),
        defender_def=int(defender["def"]),
        level=a_level,
        power=power,
        type_mult_=mult,
        crit_mult=crit_mult,
        defender_level=defender_level,
    )

    # Fright debuff: frightened attacker deals 10% less damage
    if attacker.get("wet_dream_turns", 0) > 0:
        dmg = max(1, int(round(dmg * 0.90)))

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

    if kind == "damage_burn":
        if defender.get("burn_turns", 0) == 0 and random.random() < float(move.get("burn_chance", 0.25)):
            defender["burn_turns"] = 3
            out.append(f"{STATUS_EMOJI['burn']} {d_name} was burned! (3 turns)")

    if kind == "damage_poison":
        if defender.get("poison_turns", 0) == 0 and random.random() < float(move.get("poison_chance", 0.60)):
            turns = move.get("poison_turns", (3, 4))
            poison_t = random.randint(int(turns[0]), int(turns[1]))
            defender["poison_turns"] = poison_t
            poison_apply_texts = [
                f"{STATUS_EMOJI['poison']} {d_name} got dosed — the toxin's already in the blood! ({poison_t} turns)",
                f"{STATUS_EMOJI['poison']} {d_name} didn't feel it hit — that's the worst kind! ({poison_t} turns)",
                f"{STATUS_EMOJI['poison']} The laced tip found a vein. {d_name} has {poison_t} turns to regret standing still.",
                f"{STATUS_EMOJI['poison']} {d_name} is running on borrowed time — poison's cooking from the inside! ({poison_t} turns)",
                f"{STATUS_EMOJI['poison']} {d_name} is infected. Needle Rain delivers. ({poison_t} turns of pure suffering)",
            ]
            out.append(random.choice(poison_apply_texts))

    return out

def grant_xp_with_hp_adjust(player_id: str, gained: int) -> None:
    p = players[player_id]
    champ_key = p.get("champ")
    old_level = max(1, min(int(p.get("level", 1)), MAX_LEVEL))
    p["level"] = old_level
    old_max = get_stats(champ_key, old_level)["hp"] if champ_key in CHAMPS else 0
    cur_hp = get_or_init_current_hp(player_id)

    if old_level >= MAX_LEVEL:
        p["xp"] = 0
        p["just_leveled"] = False
        set_current_hp(player_id, cur_hp)
        return

    p["xp"] = int(p.get("xp", 0)) + int(gained)

    leveled = False
    while int(p.get("level", 1)) < MAX_LEVEL and p["xp"] >= xp_needed(int(p.get("level", 1))):
        need = xp_needed(int(p.get("level", 1)))
        p["xp"] -= need
        p["level"] = int(p.get("level", 1)) + 1
        leveled = True

        new_level = int(p["level"])
        new_max = get_stats(champ_key, new_level)["hp"] if champ_key in CHAMPS else old_max
        delta = max(0, new_max - old_max)
        cur_hp = min(new_max, cur_hp + delta)
        old_max = new_max
        set_current_hp(player_id, cur_hp)

    if int(p.get("level", 1)) >= MAX_LEVEL:
        p["level"] = MAX_LEVEL
        p["xp"] = 0

    set_current_hp(player_id, cur_hp)
    p["just_leveled"] = leveled

def _remember_chat(user_id: str, chat_id: int) -> None:
    if user_id not in players:
        return
    chats = players[user_id].setdefault("chats", [])
    if chat_id not in chats:
        chats.append(chat_id)

def _eligible_players_in_chat(chat_id: int) -> List[str]:
    out: List[str] = []
    for uid, p in players.items():
        if p.get("champ") in CHAMPS and chat_id in p.get("chats", []) and bool(str(p.get("champ_nickname") or "").strip()):
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
    level = int(pdata.get("level", 1))
    xp = int(pdata.get("xp", 0))
    wins = int(pdata.get("wins", 0))
    losses = int(pdata.get("losses", 0))
    return (-level, -xp, -wins, losses, display_name(uid).lower(), uid)


def get_leaderboard(limit: int = 10) -> List[Tuple[str, str, int, int, int, int]]:
    ranked: List[Tuple[str, str, int, int, int, int]] = []
    for uid, pdata in players.items():
        if pdata.get("champ") not in CHAMPS:
            continue
        ranked.append((
            uid,
            display_name(uid),
            int(pdata.get("xp", 0)),
            int(pdata.get("level", 1)),
            int(pdata.get("wins", 0)),
            int(pdata.get("losses", 0)),
        ))
    ranked.sort(key=lambda row: ranking_sort_key(row[0]))
    return ranked[:limit]


def get_xp_and_rank(user_id: str) -> Tuple[int, Optional[int]]:
    if user_id not in players or players[user_id].get("champ") not in CHAMPS:
        return 0, None

    ordered_ids = sorted(
        [uid for uid, pdata in players.items() if pdata.get("champ") in CHAMPS],
        key=ranking_sort_key,
    )
    xp = int(players[user_id].get("xp", 0))
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

    for rank, (pid, trainer_name, xp, level, wins, losses) in enumerate(top_players, 1):
        pdata = players.get(pid, {})
        champ_key = pdata.get("champ")
        champ_type = champ_from_key(champ_key)["type"] if champ_key in CHAMPS else None
        type_icon = TYPE_EMOJI.get(champ_type, "✨")
        champ_name = html.escape(champ_full_name_for_player(pid, champ_key) if champ_key in CHAMPS else "Unknown")
        total_fights = wins + losses
        winrate = int(round((wins / total_fights) * 100)) if total_fights > 0 else 0
        trainer_link = mention_html(pid, trainer_name)

        if rank <= 3:
            lines.append(f"{medals[rank]} <b>{trainer_link}</b> {type_icon}")
            lines.append(f"<code>{champ_name}</code> • Lv.<b>{level}</b>")
            lines.append(f"⚔️ <b>{wins}W / {losses}L</b> • <b>{winrate}% WR</b>")
            lines.append("")
        else:
            lines.append(f"{rank}. <b>{trainer_link}</b> • Lv.<b>{level}</b> • <b>{xp} XP</b>")

    if user_id and user_id in players and players[user_id].get("champ") in CHAMPS:
        xp, rank = get_xp_and_rank(user_id)
        if rank is not None:
            p = players[user_id]
            level = int(p.get("level", 1))
            lines.extend([
                "",
                "━━━━━━━━━━",
                f"👤 <b>You:</b> #{rank} • Lv.<b>{level}</b> • <b>{xp} XP</b>",
            ])

    return "\n".join(lines)

# =========================
# MENUS (INLINE BUTTONS)
# =========================

def main_menu_kb(user_id: Optional[str] = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Champs", callback_data="menu|champs"),
         InlineKeyboardButton("⚔️ Fight", callback_data="menu|fight")],
        [InlineKeyboardButton("🏆 Rankings", callback_data="menu|leaderboard"),
         InlineKeyboardButton("🪪 Profile", callback_data="menu|profile")],
        [InlineKeyboardButton("🎒 Inventory", callback_data="menu|inventory"),
         InlineKeyboardButton("🩹 Heal", callback_data="menu|heal")],
    ])

def choose_champ_kb() -> InlineKeyboardMarkup:
    # Menu that lets users pick their starter without typing /choose
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌿 Basaurimon", callback_data="choose|basaurimon")],
        [InlineKeyboardButton("🔥 Suimander", callback_data="choose|suimander")],
        [InlineKeyboardButton("💧 Suiqrtle", callback_data="choose|suiqrtle")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu|home")],
    ])

# =========================
# MESSAGE EDIT STREAM (anti-freeze)
# =========================

async def _safe_edit(bot, chat_id: int, message_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[-MAX_MESSAGE_CHARS:]
    for _ in range(5):
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
            return True
        except RetryAfter as e:
            await asyncio.sleep(float(getattr(e, "retry_after", 1.5)))
        except (TimedOut, NetworkError):
            await asyncio.sleep(0.8)
        except BadRequest:
            # sanitize a bit
            text = "".join(ch for ch in text if ch >= " " or ch in "\n\t")
            text = text.replace("\u202e", "")
            await asyncio.sleep(0.25)
        except Exception:
            await asyncio.sleep(0.5)
    return False


async def _battle_reposition_message(bot, chat_id: int, state: Dict[str, Any], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, *, force: bool = False) -> None:
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
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
            old_message_id = state["message_id"]
            state["message_id"] = new_msg.message_id
            state["last_reposition"] = now
            state["last_rendered_text"] = text
            state["last_reply_markup"] = reply_markup
            sent = True
            # Fire-and-forget delete — don't block on it
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

def _trim_lines_to_fit(lines: List[str]) -> str:
    if len(lines) > MAX_LINES_SHOWN:
        lines[:] = lines[-MAX_LINES_SHOWN:]
    body = "\n".join(lines) if lines else "…"
    while len(body) > MAX_MESSAGE_CHARS and len(lines) > 5:
        lines[:] = lines[3:]
        body = "\n".join(lines)
    if len(body) > MAX_MESSAGE_CHARS:
        body = body[-MAX_MESSAGE_CHARS:]
    return body

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
    if not await ensure_allowed_chat(update, context):
        return
    user_id = await _bootstrap_user(update)
    if not update.message:
        return
    await send_menu_photo(update.message, fancy_menu_caption(user_id), main_menu_kb(user_id))

async def intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    p = players[user]
    lines = [
        "🎮 <b>Welcome to Suimon Arena</b>",
        "",
        "A turn based Telegram PvP game where every trainer controls one starter, levels it up and keeps its HP between battles.",
        "",
        "━━━ How to play ━━━",
        "1. Open Menu → <b>📜 Champs</b> and pick your permanent starter.",
        "2. Name your champ with <b>/name YourName</b>.",
        "3. Challenge someone with <b>/fight</b> or <b>/fight @Name</b>.",
        "4. In battle, choose moves with the inline buttons.",
        "",
        "Type chart: 🔥 > 🌿 > 💧 > 🔥",
        "",
        "━━━ Core rules ━━━",
        "• Your champ keeps its remaining HP after every fight.",
        "• If HP reaches 0, heal first with <b>/heal</b>.",
        f"• You receive {DAILY_SUIBALLS} Suiballs per day (cap {SUIBALL_CAP}).",
        f"• Max level is {MAX_LEVEL}.",
        "• In groups with many players, fights can require an accept/decline step.",
        "",
        "━━━ Commands ━━━",
        "/start /menu /intro /champs /choose /name /profile /rankings /inventory /heal /fight",
    ]
    if p.get("champ") not in CHAMPS:
        lines.insert(2, "⚠️ You haven't chosen a champ yet. Pick one with /choose.")
    await update.message.reply_text("\n".join(lines), reply_markup=main_menu_kb(user), parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if not update.message:
        return
    await send_menu_photo(update.message, fancy_menu_caption(user), main_menu_kb(user))

async def champs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    await _bootstrap_user(update)
    lines = ["📜 Starter Champs", ""]
    for _, c in CHAMPS.items():
        moves = ", ".join([m["name"] for m in c["moves"]])
        lines.append(f"{TYPE_EMOJI[c['type']]} {c['display']}  — type: {c['type']}")
        lines.append(f"   Moves: {moves}")
        lines.append("")
    if update.message:
        await update.message.reply_text("🌟 <b>Choose your starter</b>\n\n" + "\n".join(lines), choose_champ_kb(), parse_mode="HTML")

async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if not update.message:
        return
    if not context.args:
        await update.message.reply_text("Choose your starter via Menu → 📜 Champs.", reply_markup=main_menu_kb(user))
        return
    if players[user].get("champ") in CHAMPS:
        await update.message.reply_text("⚠️ You already chose a champ. This choice is permanent.", reply_markup=main_menu_kb(user))
        return
    champ_key = champ_key_from_input(context.args[0])
    if champ_key not in CHAMPS:
        await update.message.reply_text("Unknown champ. Use: /champs", reply_markup=main_menu_kb(user))
        return
    players[user]["champ"] = champ_key
    players[user]["level"] = 1
    players[user]["xp"] = 0
    players[user]["wins"] = 0
    players[user]["losses"] = 0
    players[user]["champ_nickname"] = None
    set_current_hp(user, get_stats(champ_key, 1)["hp"])
    players[user]["suiballs"] = max(int(players[user].get("suiballs", 0)), 1)
    start_nickname_prompt(user)
    save_players(players)
    c = champ_from_key(champ_key)
    await update.message.reply_text(
        "📝 <b>Starter selected</b>\n\n"
        f"You picked <b>{c['display']}</b> {TYPE_EMOJI[c['type']]}.\n\n"
        "🚫 You cannot fight yet. First give your champ a custom name.\n\n"
        "Use <code>/name YourName</code>\n"
        "Example: <code>/name Joyamon</code>",
        naming_prompt_kb()
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(user):
        await update.message.reply_text(nickname_required_text(user), reply_markup=naming_prompt_kb(), parse_mode="HTML")
        return
    if not update.message:
        return
    p = players[user]
    champ_key = p.get("champ")
    if champ_key not in CHAMPS:
        await update.message.reply_text("You have no champ yet. Use /start", reply_markup=main_menu_kb(user))
        return
    champ = champ_from_key(champ_key)
    lv = int(p.get("level", 1))
    xp = int(p.get("xp", 0))
    need = xp_needed(lv)
    stats = get_stats(champ_key, lv)
    cur_hp = get_or_init_current_hp(user)
    w = int(p.get("wins", 0))
    l = int(p.get("losses", 0))
    balls = int(p.get("suiballs", 0))
    fainted = " (FAINTED)" if cur_hp <= 0 else ""
    champ_label = champ_full_name_for_player(user, champ_key)
    badges_txt = get_badges_display(user)
    await update.message.reply_text(
        "🪪 <b>Trainer Card</b>\n\n"
        f"👤 {display_name(user)}\n"
        f"🏅 Record: {w}W / {l}L\n"
        + (f"🎖️ Badges: {badges_txt}\n" if badges_txt else "") +
        f"\n{TYPE_EMOJI[champ['type']]} {champ_label} (Lv.{lv}){fainted}\n"
        f"❤️ HP: {cur_hp}/{stats['hp']} ({hp_bar(cur_hp, stats['hp'])})\n"
        f"✨ XP: {xp}/{need if lv < MAX_LEVEL else 0}\n"
        f"📈 Stats: ATK {stats['atk']} | DEF {stats['def']} | SPD {stats['spd']}\n\n"
        f"🎒 Suiballs: {balls} (daily +{get_daily_suiballs()}, cap {get_suiball_cap()})\n"
        f"🔒 Max Level: {MAX_LEVEL}",
        reply_markup=main_menu_kb(user),
        parse_mode="HTML"
    )

async def nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if not update.message:
        return
    p = players[user]
    champ_key = p.get("champ")
    if champ_key not in CHAMPS:
        await update.message.reply_text("Choose your champ first with /choose or Menu → 📜 Champs.", reply_markup=main_menu_kb(user))
        return
    current = champ_full_name_for_player(user, champ_key)
    raw = " ".join(context.args).strip()
    if not raw:
        start_nickname_prompt(user)
        await update.message.reply_text(
            "📝 <b>Name your champ</b>\n\n"
            f"Current champ: <b>{html.escape(current)}</b>\n\n"
            "Use this command format: <code>/name YourName</code>\n"
            "Example: <code>/name Joyamon</code>\n\nThen use ⬅️ Back to return to the menu.",
            parse_mode="HTML",
            reply_markup=naming_prompt_kb(),
        )
        return
    nick = sanitize_champ_nickname(raw)
    if len(nick) < 2:
        start_nickname_prompt(user)
        await update.message.reply_text("Nickname too short. Use /name with 2 to 18 letters or numbers.", reply_markup=naming_prompt_kb())
        return
    players[user]["champ_nickname"] = nick
    players[user]["awaiting_nickname"] = False
    save_players(players)
    base_name = champ_from_key(champ_key)["display"]
    champ_emoji = TYPE_EMOJI[champ_from_key(champ_key)["type"]]
    await update.message.reply_text(
        f"✅ <b>{base_name}</b> is now named <b>{html.escape(nick)}</b>!\n\n"
        f"🎉 <b>{html.escape(nick)}</b> joined your team {champ_emoji}\n"
        "🧿 You received <b>1 Suiball</b>.\n\n"
        f"Battle display: <b>{html.escape(nick)}</b> vs ...",
        reply_markup=main_menu_kb(user),
        parse_mode="HTML"
    )

async def nickname_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if not update.message:
        return
    if not needs_nickname_prompt(user) and not players[user].get("awaiting_nickname"):
        return
    raw = (update.message.text or "").strip()
    nick = sanitize_champ_nickname(raw)
    if len(nick) < 2:
        start_nickname_prompt(user)
        await update.message.reply_text(
            "❌ That name is too short. Use /name with 2 to 18 letters or numbers.",
            reply_markup=naming_prompt_kb()
        )
        return
    champ_key = players[user].get("champ")
    if champ_key not in CHAMPS:
        await update.message.reply_text("Choose your champ first with /choose or Menu → 📜 Champs.", reply_markup=main_menu_kb(user))
        return
    players[user]["champ_nickname"] = nick
    players[user]["awaiting_nickname"] = False
    save_players(players)
    base_name = champ_from_key(champ_key)["display"]
    champ_emoji = TYPE_EMOJI[champ_from_key(champ_key)["type"]]
    await update.message.reply_text(
        f"✅ <b>{base_name}</b> is now named <b>{html.escape(nick)}</b>!\n\n"
        f"🎉 <b>{html.escape(nick)}</b> joined your team {champ_emoji}\n"
        "🧿 You received <b>1 Suiball</b>.\n\n"
        f"You can now fight with <b>{html.escape(nick)}</b>.",
        reply_markup=main_menu_kb(user),
        parse_mode='HTML'
    )
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(user):
        await update.message.reply_text(nickname_required_text(user), reply_markup=naming_prompt_kb(), parse_mode="HTML")
        return
    if not update.message:
        return

    rankings_text = build_rankings_text(user, 10)
    rankings_image_candidates = ("rankings.jpg", "rankings.JPG", "rankings.png")
    rankings_image = None
    for name in rankings_image_candidates:
        candidate = os.path.join(BASE_DIR, name)
        if os.path.isfile(candidate):
            rankings_image = candidate
            break
    if rankings_image:
        with open(rankings_image, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=rankings_text, reply_markup=main_menu_kb(user), parse_mode="HTML")
    else:
        await update.message.reply_text(rankings_text, reply_markup=main_menu_kb(user), parse_mode="HTML", disable_web_page_preview=True)


async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(user):
        await update.message.reply_text(nickname_required_text(user), reply_markup=naming_prompt_kb(), parse_mode="HTML")
        return
    if not update.message:
        return
    p = players[user]
    champ_key = p.get("champ")
    champ_txt = "None" if champ_key not in CHAMPS else champ_full_name_for_player(user, champ_key)
    balls = int(p.get("suiballs", 0))
    await update.message.reply_text(
        "🎒 Inventory\n\n"
        f"🧿 Suiballs: {balls}\n"
        f"📅 Daily refresh: {today_str()} (UTC)\n\n"
        "Suiballs heal your active champ to full HP:\n"
        "• /heal\n\n"
        f"Active champ: {champ_txt}",
        reply_markup=main_menu_kb(user)
    )

async def heal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(user):
        await update.message.reply_text(nickname_required_text(user), reply_markup=naming_prompt_kb(), parse_mode="HTML")
        return
    if not update.message:
        return
    p = players[user]
    champ_key = p.get("champ")
    if champ_key not in CHAMPS:
        await update.message.reply_text("You have no champ yet. Use /start", reply_markup=main_menu_kb(user))
        return
    lv = int(p.get("level", 1))
    mx = get_stats(champ_key, lv)["hp"]
    cur = get_or_init_current_hp(user)
    if cur >= mx:
        heal_image = resolve_heal_image_path()
        if heal_image:
            with open(heal_image, "rb") as photo:
                await update.message.reply_photo(photo=photo, caption="✅ Your champ is already at full HP.", reply_markup=main_menu_kb(user))
        else:
            await update.message.reply_text("✅ Your champ is already at full HP.", reply_markup=main_menu_kb(user))
        return
    balls = int(p.get("suiballs", 0))
    if balls <= 0:
        heal_image = resolve_heal_image_path()
        no_balls_text = f"❌ You have no Suiballs.\nYou get {DAILY_SUIBALLS} per day (cap {SUIBALL_CAP}).\nUse /inventory."
        if heal_image:
            with open(heal_image, "rb") as photo:
                await update.message.reply_photo(photo=photo, caption=no_balls_text, reply_markup=main_menu_kb(user))
        else:
            await update.message.reply_text(no_balls_text, reply_markup=main_menu_kb(user))
        return
    p["suiballs"] = balls - 1
    heal_to_full(user)
    save_players(players)
    champ = champ_from_key(champ_key)
    heal_text = (
        f"🧿 Used 1 Suiball on {champ_full_name_for_player(user, champ_key)}!\n"
        f"❤️ HP restored: {mx}/{mx}\n"
        f"Remaining Suiballs: {p['suiballs']}"
    )
    heal_image = resolve_heal_image_path()
    if heal_image:
        with open(heal_image, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=heal_text, reply_markup=main_menu_kb(user))
    else:
        await update.message.reply_text(heal_text, reply_markup=main_menu_kb(user))

async def cutforsuimon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if not update.message:
        return

    p = players[user]
    t = today_str()
    if p.get("last_cut") == t:
        await update.message.reply_text(
            "🩸 You already cut for the cult today. Come back tomorrow.",
            reply_markup=main_menu_kb(user)
        )
        return

    current = int(p.get("suiballs", 0))
    p["suiballs"] = min(get_suiball_cap(), current + 1)
    p["last_cut"] = t
    save_players(players)

    await update.message.reply_text(
        "🩸 You cut for the cult and earned 1 Suiball!",
        reply_markup=main_menu_kb(user)
    )

async def give_suiball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    giver = await _bootstrap_user(update)
    if not update.message or not update.effective_chat:
        return

    chat_id = int(update.effective_chat.id)
    if not await is_privileged_user(context.bot, chat_id, int(giver)):
        await update.message.reply_text("❌ Only allowed user IDs and the group owner can use this.")
        return

    target: Optional[str] = None
    amount: Optional[int] = None

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = str(update.message.reply_to_message.from_user.id)
        if context.args:
            try:
                amount = int(context.args[0])
            except Exception:
                amount = None
    else:
        target, amount = _parse_target_and_amount(chat_id, context.args)

    if not target or target not in players:
        await update.message.reply_text(
            """Usage:
• Reply to a player: <code>/givesuiball 1</code>
• Or use: <code>/givesuiball @name 2</code>""",
            parse_mode="HTML"
        )
        return

    if amount is None or amount <= 0:
        await update.message.reply_text("Please enter a valid amount, e.g. <code>/givesuiball @name 2</code>", parse_mode="HTML")
        return

    before = int(players[target].get("suiballs", 0))
    players[target]["suiballs"] = min(999, before + amount)
    save_players(players)

    await update.message.reply_text(
        f"✅ Gave <b>{amount}</b> Suiball{'s' if amount != 1 else ''} to <b>{html.escape(display_name(target))}</b>.\n"
        f"🎒 New total: <b>{players[target]['suiballs']}</b>",
        parse_mode="HTML"
    )


async def remove_suiball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    giver = await _bootstrap_user(update)
    if not update.message or not update.effective_chat:
        return

    chat_id = int(update.effective_chat.id)
    if not await is_privileged_user(context.bot, chat_id, int(giver)):
        await update.message.reply_text("❌ Only allowed user IDs and the group owner can use this.")
        return

    target: Optional[str] = None
    amount: Optional[int] = None

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = str(update.message.reply_to_message.from_user.id)
        if context.args:
            try:
                amount = int(context.args[0])
            except Exception:
                amount = None
    else:
        target, amount = _parse_target_and_amount(chat_id, context.args)

    if not target or target not in players:
        await update.message.reply_text(
            """Usage:
• Reply to a player: <code>/takesuiball 1</code>
• Or use: <code>/takesuiball @name 2</code>""",
            parse_mode="HTML"
        )
        return

    if amount is None or amount <= 0:
        await update.message.reply_text("Please enter a valid amount, e.g. <code>/takesuiball @name 2</code>", parse_mode="HTML")
        return

    before = int(players[target].get("suiballs", 0))
    players[target]["suiballs"] = max(0, before - amount)
    removed = before - players[target]["suiballs"]
    save_players(players)

    await update.message.reply_text(
        f"✅ Removed <b>{removed}</b> Suiball{'s' if removed != 1 else ''} from <b>{html.escape(display_name(target))}</b>.\n"
        f"🎒 New total: <b>{players[target]['suiballs']}</b>",
        parse_mode="HTML"
    )



# Pending reset confirmations: user_id -> timestamp
PENDING_RESETS: Dict[str, float] = {}

async def reset_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    caller = await _bootstrap_user(update)
    if not update.message or not update.effective_chat:
        return

    chat_id = int(update.effective_chat.id)
    if not await is_privileged_user(context.bot, chat_id, int(caller)):
        await update.message.reply_text("❌ Only allowed user IDs can use this.")
        return

    # Check if confirmation is pending
    pending_ts = PENDING_RESETS.get(caller)
    now = time.monotonic()
    if pending_ts and (now - pending_ts) < 30:
        # Confirmed — execute reset
        PENDING_RESETS.pop(caller, None)
        count = 0
        for uid, p in players.items():
            if p.get("champ") not in CHAMPS:
                continue
            champ_key = p.get("champ")
            champ_nickname = p.get("champ_nickname")
            # Reset everything except champ and name
            p["level"] = 1
            p["xp"] = 0
            p["wins"] = 0
            p["losses"] = 0
            p["suiballs"] = DAILY_SUIBALLS
            p["last_daily"] = None
            p["champ"] = champ_key
            p["champ_nickname"] = champ_nickname
            set_current_hp(uid, get_stats(champ_key, 1)["hp"])
            count += 1
        save_players(players)
        await update.message.reply_text(
            f"♻️ <b>Leaderboard reset complete!</b>\n\n"
            f"<b>{count}</b> trainers reset to Level 1.\n"
            "Champs and names were kept.",
            parse_mode="HTML"
        )
    else:
        # First call — ask for confirmation
        PENDING_RESETS[caller] = now
        await update.message.reply_text(
            "⚠️ <b>Are you sure?</b>\n\n"
            "This will reset <b>ALL players</b> to:\n"
            "• Level 1, 0 XP\n"
            "• 0 Wins / 0 Losses\n"
            "• Full HP\n"
            f"• {DAILY_SUIBALLS} Suiballs\n\n"
            "Champs and names will be kept.\n\n"
            "Type <code>/resetleaderboard</code> again within 30 seconds to confirm.",
            parse_mode="HTML"
        )



def award_battle_xp(winner: str, loser: str) -> Tuple[int, int]:
    winner_level = int(players[winner].get("level", 1))
    loser_level = int(players[loser].get("level", 1))
    level_diff = loser_level - winner_level  # positive = winner was lower level

    xp_winner = 45
    if level_diff >= 3:
        xp_winner = 75
    elif level_diff == 2:
        xp_winner = 65
    elif level_diff == 1:
        xp_winner = 55
    elif level_diff < 0:
        xp_winner = 35  # higher level beating lower level = less XP

    xp_loser = 20
    boost = get_xp_boost_multiplier()
    xp_winner = int(round(xp_winner * boost))
    xp_loser = int(round(xp_loser * boost))
    players[winner]["wins"] = int(players[winner].get("wins", 0)) + 1
    players[loser]["losses"] = int(players[loser].get("losses", 0)) + 1
    grant_xp_with_hp_adjust(winner, xp_winner)
    grant_xp_with_hp_adjust(loser, xp_loser)
    return xp_winner, xp_loser

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
    if remaining_uses <= 0:
        ball_label = f"🧿 Suiball (0/1 left)"
    elif balls <= 0:
        ball_label = f"🧿 Suiball (no balls · {remaining_uses}/1 left)"
    else:
        ball_label = f"🧿 Use Suiball ({balls} 🎒 · {remaining_uses}/1 left)"
    if can_heal:
        rows.append([InlineKeyboardButton(ball_label, callback_data=f"heal|{chat_id}")])
    else:
        # Disabled: use a no-op callback so Telegram accepts the button but nothing happens
        rows.append([InlineKeyboardButton(ball_label, callback_data=f"noop|{chat_id}")])
    rows.append([InlineKeyboardButton("🏳️ Forfeit", callback_data=f"ff|{chat_id}")])
    return InlineKeyboardMarkup(rows)

def _battle_hud_html(state: Dict[str, Any]) -> str:
    return f"<pre>{html.escape(battle_hud(state['c1_label'], state['champ1']['hp'], state['champ1']['max_hp'], state['c2_label'], state['champ2']['hp'], state['champ2']['max_hp']), quote=False)}</pre>"

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

async def _battle_push(chat_id: int, state: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE, line, delay: float = ACTION_DELAY, reply_markup: Optional[InlineKeyboardMarkup] = None, *, force_reposition: bool = False, raw_html: bool = False):
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
    # show a round header every 2 actions (start of new round)
    if state["actions"] % 2 == 0:
        state["round"] += 1
        await _battle_push(chat_id, state, context, f"━━━ Round {state['round']} ━━━", delay=0.35, force_reposition=False)
    name = _battle_turn_name(state)
    champ_key = _battle_turn_champ_key(state)
    turn_user = _battle_turn_user(state)
    champ_name = champ_display_for_player(turn_user, champ_key)
    kb = _battle_move_keyboard(chat_id, champ_key, turn_user, state)
    await _battle_push(chat_id, state, context, f"\n🎯 {name}'s turn — choose a move for {champ_name}:", delay=0.05, reply_markup=kb, force_reposition=True)

async def _end_battle(chat_id: int, state: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE, winner: str, loser: str):
    # Persist HP + XP
    
    set_current_hp(state["user"], int(max(state["champ1"]["hp"], 0)))
    xp_w, xp_l = award_battle_xp(winner, loser)
    save_players(players)

    w_name = display_name(winner, "Winner")
    w_champ = champ_display_for_player(winner, players[winner]["champ"])

    await _battle_push(chat_id, state, context, "The dust settles…", delay=0.45, reply_markup=None)
    await _battle_push(chat_id, state, context, f"🏆 Winner: {w_name} with {w_champ}!", delay=0.45, reply_markup=None)
    await _battle_push(chat_id, state, context, f"🎁 XP: {xp_w} (Winner) / {xp_l} (Loser)", delay=0.35, reply_markup=None)

    lvlups = []
    if players[state["user"]].get("just_leveled"):
        lvlups.append((state["p1_name"], players[state["user"]]["level"]))
        players[state["user"]]["just_leveled"] = False
    if players[state["opponent"]].get("just_leveled"):
        lvlups.append((state["p2_name"], players[state["opponent"]]["level"]))
        players[state["opponent"]]["just_leveled"] = False
    if lvlups:
        await _battle_push(chat_id, state, context, "📣 Level Up!", delay=0.25, reply_markup=None)
        for n, lv in lvlups:
            await _battle_push(chat_id, state, context, f"⭐ {n} is now Lv.{lv}!", delay=0.25, reply_markup=None)

    await _battle_push(chat_id, state, context, "✅ Battle complete.", delay=END_DELAY, reply_markup=None)

    save_players(players)

    # cleanup
    BATTLES.pop(chat_id, None)
    ACTIVE_BATTLES.discard(chat_id)

async def _start_battle(chat_id: int, user: str, opponent: str, context: ContextTypes.DEFAULT_TYPE):
    global players
    players = load_players()

    if chat_id in ACTIVE_BATTLES:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ A battle is already running in this chat. Please wait.")
        return

    if user not in players or opponent not in players:
        await context.bot.send_message(chat_id=chat_id, text="❌ One of the players is not registered. Use /start first.")
        return

    p1 = players[user]
    p2 = players[opponent]

    if p1.get("champ") not in CHAMPS or p2.get("champ") not in CHAMPS:
        await context.bot.send_message(chat_id=chat_id, text="❌ Both players must /choose a champ first.")
        return

    # Check fainted
    p1_cur_hp = get_or_init_current_hp(user)
    p2_cur_hp = get_or_init_current_hp(opponent)
    if p1_cur_hp <= 0:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ {display_name(user)} must /heal first (HP 0).")
        return
    if p2_cur_hp <= 0:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ {display_name(opponent)} must /heal first (HP 0).")
        return

    ACTIVE_BATTLES.add(chat_id)

    # create battle message
    msg = await context.bot.send_message(chat_id=chat_id, text="⚔️ SUIMON BATTLE (loading...)")
    message_id = msg.message_id

    c1_key = p1["champ"]
    c2_key = p2["champ"]
    c1 = champ_from_key(c1_key)
    c2 = champ_from_key(c2_key)

    lv1 = int(p1.get("level", 1))
    lv2 = int(p2.get("level", 1))
    s1 = get_stats(c1_key, lv1)
    s2 = get_stats(c2_key, lv2)

    champ1 = {"hp": int(p1_cur_hp), "max_hp": s1["hp"], "atk": s1["atk"], "def": s1["def"], "spd": s1["spd"], "burn_turns": 0, "sleep_turns": 0, "confuse_turns": 0, "poison_turns": 0, "wet_dream_turns": 0, "wet_dream_uses_left": 2 if c1_key == "suimander" else 0, "has_slept": False, "last_used_sleep": False}
    champ2 = {"hp": int(p2_cur_hp), "max_hp": s2["hp"], "atk": s2["atk"], "def": s2["def"], "spd": s2["spd"], "burn_turns": 0, "sleep_turns": 0, "confuse_turns": 0, "poison_turns": 0, "wet_dream_turns": 0, "wet_dream_uses_left": 2 if c2_key == "suimander" else 0, "has_slept": False, "last_used_sleep": False}

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
        "user": user,
        "opponent": opponent,
        "p1_name": p1_name,
        "p2_name": p2_name,
        "c1_key": c1_key,
        "c2_key": c2_key,
        "lv1": lv1,
        "lv2": lv2,
        "champ1": champ1,
        "champ2": champ2,
        "c1_label": f"{p1_name} - {champ_display_for_player(user, c1_key)} (Lv.{lv1})",
        "c2_label": f"{p2_name} - {champ_display_for_player(opponent, c2_key)} (Lv.{lv2})",
        "turn": 0,
        "round": 0,
        "actions": 0,
        "max_rounds": 24,
        "suiballs_used": {},  # tracks per-player suiball usage this battle
    }
    BATTLES[chat_id] = state

    await _battle_push(chat_id, state, context, "⚔️ BATTLE START ⚔️", delay=0.25, reply_markup=None, force_reposition=True)
    await _battle_push(chat_id, state, context, f"👤 {p1_name} sends out {champ_full_name_for_player(user, c1_key)}!", delay=0.30, reply_markup=None)
    await _battle_push(chat_id, state, context, f"👤 {p2_name} sends out {champ_full_name_for_player(opponent, c2_key)}!", delay=0.30, reply_markup=None)
    await _battle_push_hud(chat_id, state, context, delay=0.30, reply_markup=None)

    for t in ("3…", "2…", "1…", "GO!"):
        await _battle_push(chat_id, state, context, t, delay=COUNTDOWN_STEP_DELAY, reply_markup=None)

    first = pick_first_attacker(int(champ1["spd"]), int(champ2["spd"]))
    state["turn"] = first
    starter_name = champ_display_for_player(user, c1_key) if first == 0 else champ_display_for_player(opponent, c2_key)
    await _battle_push(chat_id, state, context, f"🏁 {starter_name} moves first!", delay=0.35, reply_markup=None)

    await _battle_prompt_turn(chat_id, state, context)

# =========================
# ADMIN: CHANGE CHAMP
# =========================

async def tournamenton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    admin = await _bootstrap_user(update)
    if not update.message or not update.effective_chat:
        return
    chat_id = int(update.effective_chat.id)
    if not await is_privileged_user(context.bot, chat_id, int(admin)):
        await update.message.reply_text("❌ Only privileged users can use this.")
        return

    tournament_state["active"] = True
    save_tournament(tournament_state)

    # Give everyone 200 suiballs
    named = []
    for uid, p in players.items():
        p["suiballs"] = 100
        if p.get("champ") in CHAMPS and p.get("champ_nickname"):
            named.append(display_name(uid))
    save_players(players)

    tournament_text = (
        "🏆 <b>TOURNAMENT HAS STARTED!</b> 🏆\n\n"
        "Every Trainer has received <b>100 Suiballs</b>!\n\n"
        "Play <b>100 games</b> and finish in the <b>TOP 3</b> to win the Prize.\n\n"
        "Remember — <b>#1</b> receives the coveted\n"
        "🔥 <b>Volcano Badge</b> 🔥\n\n"
        "Daily Suiballs are now <b>+10</b> during the Tournament.\n\n"
        "May the best Trainer win. Good luck! ⚔️"
    )
    tournament_image_candidates = ("tournament.jpg", "tournament.JPG", "tournament.png")
    tournament_image = None
    for name in tournament_image_candidates:
        candidate = os.path.join(BASE_DIR, name)
        if os.path.isfile(candidate):
            tournament_image = candidate
            break
    if tournament_image:
        with open(tournament_image, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=tournament_text, parse_mode="HTML")
    else:
        await update.message.reply_text(tournament_text, parse_mode="HTML")

async def tournamentoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    admin = await _bootstrap_user(update)
    if not update.message or not update.effective_chat:
        return
    chat_id = int(update.effective_chat.id)
    if not await is_privileged_user(context.bot, chat_id, int(admin)):
        await update.message.reply_text("❌ Only privileged users can use this.")
        return

    tournament_state["active"] = False
    save_tournament(tournament_state)

    # Reset all players' suiballs to normal cap
    for uid, p in players.items():
        if p.get("champ") in CHAMPS:
            p["suiballs"] = min(int(p.get("suiballs", 0)), SUIBALL_CAP)
    save_players(players)

    # Get leaderboard
    top = get_leaderboard(10)
    if not top:
        await update.message.reply_text("🏁 Tournament ended. No players found.")
        return

    # Award Cascade Badge to #1
    winner_id = top[0][0]
    winner_name = top[0][1]
    if "badges" not in players[winner_id]:
        players[winner_id]["badges"] = []
    if "cascade" not in players[winner_id]["badges"]:
        players[winner_id]["badges"].append("cascade")
    save_players(players)

    # Build leaderboard text
    lb_lines = []
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, name, xp, level, wins, losses) in enumerate(top):
        medal = medals[i] if i < 3 else f"{i+1}."
        lb_lines.append(f"{medal} <b>{html.escape(name)}</b> — Lv.{level} • {wins}W/{losses}L")

    congrats_text = (
        "🏁 <b>TOURNAMENT OVER!</b>\n\n"
        + "\n".join(lb_lines) +
        f"\n\n🔥🔥🔥\n"
        f"Congratulations <b>{html.escape(winner_name)}</b>!\n"
        f"You have won the <b>Volcano Badge</b>! 🔥\n"
        f"🔥🔥🔥"
    )
    congrats_image_candidates = ("congrats.jpg", "congrats.JPG", "congrats.png")
    congrats_image = None
    for name in congrats_image_candidates:
        candidate = os.path.join(BASE_DIR, name)
        if os.path.isfile(candidate):
            congrats_image = candidate
            break
    if congrats_image:
        with open(congrats_image, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=congrats_text, parse_mode="HTML")
    else:
        await update.message.reply_text(congrats_text, parse_mode="HTML")


async def change_champ(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    admin = await _bootstrap_user(update)
    if not update.message or not update.effective_chat:
        return

    chat_id = int(update.effective_chat.id)
    if not await is_privileged_user(context.bot, chat_id, int(admin)):
        await update.message.reply_text("❌ Only allowed user IDs and the group owner can use this.")
        return

    # Usage: /changechamp @user <champname>
    # or reply to a message: /changechamp <champname>
    target: Optional[str] = None
    champ_arg: Optional[str] = None

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = str(update.message.reply_to_message.from_user.id)
        champ_arg = context.args[0].strip() if context.args else None
    else:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "⚠️ Usage:\n"
                "<code>/changechamp @username champname</code>\n"
                "or reply to a message:\n"
                "<code>/changechamp champname</code>\n\n"
                "Valid champs: <code>suimander</code>, <code>suiqrtle</code>, <code>basaurimon</code>",
                parse_mode="HTML"
            )
            return
        target, _ = _parse_target_from_args(chat_id, context.args)
        champ_arg = context.args[1].strip() if len(context.args) > 1 else None

    if not target or target not in players:
        await update.message.reply_text("❌ Player not found.")
        return

    new_champ = champ_key_from_input(champ_arg or "")
    if not new_champ:
        await update.message.reply_text(
            f"❌ Unknown champ: <code>{html.escape(champ_arg or '')}</code>\n\n"
            "Valid champs: <code>suimander</code>, <code>suiqrtle</code>, <code>basaurimon</code>",
            parse_mode="HTML"
        )
        return

    old_champ_key = players[target].get("champ")
    old_champ_name = champ_from_key(old_champ_key)["display"] if old_champ_key in CHAMPS else "None"
    new_champ_data = champ_from_key(new_champ)
    level = int(players[target].get("level", 1))

    players[target]["champ"] = new_champ
    set_current_hp(target, get_stats(new_champ, level)["hp"])
    save_players(players)

    target_name = display_name(target)
    await update.message.reply_text(
        f"✅ <b>{html.escape(target_name)}</b>'s champ changed!\n\n"
        f"Old: <b>{html.escape(old_champ_name)}</b>\n"
        f"New: <b>{new_champ_data['display']}</b> {TYPE_EMOJI[new_champ_data['type']]}\n\n"
        f"⚠️ HP reset to full (Lv.{level}). Nickname kept.",
        parse_mode="HTML"
    )

async def xpboost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    admin = await _bootstrap_user(update)
    if not update.message or not update.effective_chat:
        return
    chat_id = int(update.effective_chat.id)
    if not await is_privileged_user(context.bot, chat_id, int(admin)):
        await update.message.reply_text("❌ Only privileged users can use this.")
        return

    duration_seconds = 2 * 60 * 60  # 2 hours
    expires = time.time() + duration_seconds
    tournament_state["xp_boost_expires"] = expires
    save_tournament(tournament_state)

    boost_text = (
        "⚡ <b>XP BOOST ACTIVATED!</b> ⚡\n\n"
        "All battles now grant <b>+50% XP</b> for the next <b>2 hours</b>!\n\n"
        "🏆 Grind hard — this won't last forever.\n"
        "⚔️ Get fighting!"
    )
    boost_image_candidates = ("xpboost.jpg", "xpboost.JPG", "xpboost.png")
    boost_image = None
    for name in boost_image_candidates:
        candidate = os.path.join(BASE_DIR, name)
        if os.path.isfile(candidate):
            boost_image = candidate
            break
    if boost_image:
        with open(boost_image, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=boost_text, parse_mode="HTML")
    else:
        await update.message.reply_text(boost_text, parse_mode="HTML")


async def endfight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    admin = await _bootstrap_user(update)
    if not update.message or not update.effective_chat:
        return
    chat_id = int(update.effective_chat.id)
    if not await is_privileged_user(context.bot, chat_id, int(admin)):
        await update.message.reply_text("❌ Only privileged users can use this.")
        return

    state = BATTLES.get(chat_id)
    if not state:
        await update.message.reply_text("❌ No active battle in this chat.")
        return

    # Usage: /endfight @winner
    target, _ = _parse_target_from_args(chat_id, context.args or [])
    if not target:
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            target = str(update.message.reply_to_message.from_user.id)

    if not target or target not in (state["user"], state["opponent"]):
        await update.message.reply_text(
            "⚠️ Usage: <code>/endfight @winner</code> or reply to winner's message.",
            parse_mode="HTML"
        )
        return

    winner = target
    loser = state["opponent"] if winner == state["user"] else state["user"]
    await update.message.reply_text(f"🛑 Admin ended the fight. Winner: <b>{html.escape(display_name(winner))}</b>", parse_mode="HTML")
    await _end_battle(chat_id, state, context, winner=winner, loser=loser)

# =========================
# PvP COMMANDS
# =========================

async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    user = await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(user):
        await update.message.reply_text(nickname_required_text(user), reply_markup=naming_prompt_kb(), parse_mode="HTML")
        return
    chat = update.effective_chat
    if not chat or not update.message:
        return
    chat_id = int(chat.id)

    if players[user].get("champ") not in CHAMPS:
        await update.message.reply_text("⚠️ Choose your champ first with /choose (or /start).", reply_markup=main_menu_kb(user))
        return

    eligible = [uid for uid in _eligible_players_in_chat(chat_id) if uid != user]
    if not eligible:
        await update.message.reply_text("No opponents in this chat yet. Ask someone to pick and name their champ first!", reply_markup=main_menu_kb(user))
        return

    target = _parse_target_user_id(update, context)
    if len(eligible) == 1:
        target = eligible[0]
    elif not target or target not in eligible:
        await update.message.reply_text(
            "⚔️ Multiple opponents found.\n"
            "Reply to a player's message with /fight, or use /fight @Name.",
            reply_markup=main_menu_kb(user)
        )
        return

    # Auto-expire any old pending challenge from this user in this chat
    now = time.monotonic()
    for k in list(PENDING_CHALLENGES.keys()):
        if k[0] == chat_id and PENDING_CHALLENGES[k].get("from") == user:
            if now - PENDING_CHALLENGES[k].get("ts_mono", 0) > CHALLENGE_TIMEOUT:
                PENDING_CHALLENGES.pop(k, None)

    # Check if target already has a pending challenge
    existing = PENDING_CHALLENGES.get((chat_id, target))
    if existing and now - existing.get("ts_mono", 0) < CHALLENGE_TIMEOUT:
        await update.message.reply_text(
            f"⏳ <b>{html.escape(display_name(target))}</b> already has a pending challenge. Wait for it to expire or be resolved.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(user)
        )
        return

    PENDING_CHALLENGES[(chat_id, target)] = {"from": user, "ts": datetime.now(TZ).isoformat(), "ts_mono": now}

    challenger_name = display_name(user, "Challenger")
    target_name = display_name(target, "Opponent")
    challenger_champ = champ_display_for_player(user, players[user].get("champ"))

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"suimon_accept|{user}|{target}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"suimon_decline|{user}|{target}"),
    ]])

    sent_msg = await update.message.reply_text(
        f"⚔️ <b>{html.escape(challenger_name)}</b> challenges <b>{html.escape(target_name)}</b>!\n"
        f"🧿 Champ: <b>{html.escape(challenger_champ)}</b>\n\n"
        f"<b>{html.escape(target_name)}</b>, do you accept this fight request?\n"
        f"⏳ Expires in {CHALLENGE_TIMEOUT} seconds.",
        reply_markup=kb,
        parse_mode="HTML",
    )

    # Schedule auto-expiry
    async def _expire_challenge():
        await asyncio.sleep(CHALLENGE_TIMEOUT)
        key = (chat_id, target)
        if PENDING_CHALLENGES.get(key, {}).get("from") == user:
            PENDING_CHALLENGES.pop(key, None)
            try:
                await sent_msg.edit_text(
                    f"⏰ <b>Challenge expired!</b>\n"
                    f"{html.escape(challenger_name)} challenged {html.escape(target_name)} but got no response.",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                pass

    asyncio.create_task(_expire_challenge())

async def challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()

    data = query.data or ""
    parts = data.split("|")
    if len(parts) < 3:
        await query.edit_message_text("Invalid challenge data.")
        return
    action, challenger, target = parts[0], parts[1], parts[2]

    chat_id = int(query.message.chat.id)
    clicker = str(query.from_user.id)

    # Only the challenged player may accept or decline
    if clicker != target:
        await query.answer("This challenge is not for you.", show_alert=True)
        return

    opponent = clicker

    key = (chat_id, opponent)
    payload = PENDING_CHALLENGES.get(key)
    if not payload:
        await query.edit_message_text("⚠️ Challenge expired or already handled.")
        return

    # Check timeout
    if time.monotonic() - payload.get("ts_mono", 0) > CHALLENGE_TIMEOUT:
        PENDING_CHALLENGES.pop(key, None)
        await query.edit_message_text("⏰ Challenge expired — too slow!")
        return

    expected = str(payload.get("from", ""))
    if expected != str(challenger):
        PENDING_CHALLENGES.pop(key, None)
        await query.edit_message_text("⚠️ Challenge mismatch. Please challenge again.")
        return

    PENDING_CHALLENGES.pop(key, None)

    if action.startswith("suimon_decline"):
        await query.edit_message_text("❌ Challenge declined.")
        return

    if not action.startswith("suimon_accept"):
        await query.edit_message_text("Invalid action.")
        return

    await query.edit_message_text("✅ Fight request accepted. Battle starting…")
    await _start_battle(chat_id, str(challenger), opponent, context)

# =========================
# CALLBACKS: MENU + MOVES
# =========================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user_id = str(query.from_user.id)
    ensure_player(user_id, (query.from_user.first_name or "Player").strip(), query.from_user.username)
    if query.message:
        _remember_chat(user_id, int(query.message.chat.id))
    ensure_daily(user_id)
    save_players(players)

    action = query.data.split("|", 1)[1] if "|" in query.data else "home"

    if action == "profile":
        p = players[user_id]
        champ_key = p.get("champ")
        if champ_key not in CHAMPS:
            await edit_menu_message(query, "You have no champ yet. Use /start", main_menu_kb(user_id))
            return
        champ = champ_from_key(champ_key)
        lv = int(p.get("level", 1))
        xp = int(p.get("xp", 0))
        need = xp_needed(lv)
        stats = get_stats(champ_key, lv)
        cur_hp = get_or_init_current_hp(user_id)
        w = int(p.get("wins", 0))
        l = int(p.get("losses", 0))
        balls = int(p.get("suiballs", 0))
        fainted = " (FAINTED)" if cur_hp <= 0 else ""
        badges_txt = get_badges_display(user_id)
        await edit_menu_message(
            query,
            "🪪 <b>Trainer Card</b>\n\n"
            f"👤 <b>{html.escape(display_name(user_id))}</b>\n"
            f"🏅 <b>Record:</b> {w}W / {l}L\n"
            + (f"🎖️ <b>Badges:</b> {badges_txt}\n" if badges_txt else "") +
            f"\n{TYPE_EMOJI[champ['type']]} <b>{html.escape(champ_full_name_for_player(user_id, champ_key))}</b> (Lv.<b>{lv}</b>){fainted}\n"
            f"❤️ <b>HP:</b> {cur_hp}/{stats['hp']} ({hp_bar(cur_hp, stats['hp'])})\n"
            f"✨ <b>XP:</b> {xp}/{need if lv < MAX_LEVEL else 0}\n"
            f"📈 <b>Stats:</b> ATK {stats['atk']} | DEF {stats['def']} | SPD {stats['spd']}\n\n"
            f"🎒 <b>Suiballs:</b> {balls} (daily +{get_daily_suiballs()}, cap {get_suiball_cap()})\n"
            f"🔒 <b>Max Level:</b> {MAX_LEVEL}",
            main_menu_kb(user_id)
        )
        return

    if action == "leaderboard":
        await edit_menu_message(query, build_rankings_text(user_id, 10), main_menu_kb(user_id), disable_web_page_preview=True)
        return

    if action == "inventory":
        p = players[user_id]
        balls = int(p.get("suiballs", 0))
        champ_key = p.get("champ")
        champ_text = champ_full_name_for_player(user_id, champ_key) if champ_key in CHAMPS else "No champ"
        await edit_menu_message(
            query,
            "🎒 <b>Inventory</b>\n\n"
            f"Trainer: <b>{html.escape(display_name(user_id))}</b>\n"
            f"Champ: <b>{html.escape(champ_text)}</b>\n\n"
            f"🧿 Suiballs: <b>{balls}</b>\n"
            f"Daily gain: +{DAILY_SUIBALLS}  |  Cap: {SUIBALL_CAP}\n"
            f"Max level: {MAX_LEVEL}",
            main_menu_kb(user_id)
        )
        return

    if action == "heal":
        p = players[user_id]
        champ_key = p.get("champ")
        if champ_key not in CHAMPS:
            await edit_menu_message(query, "You have no champ yet. Use /start", main_menu_kb(user_id))
            return
        lv = int(p.get("level", 1))
        mx = get_stats(champ_key, lv)["hp"]
        cur = get_or_init_current_hp(user_id)
        if cur >= mx:
            heal_image = resolve_heal_image_path()
            if heal_image and query.message:
                with open(heal_image, "rb") as photo:
                    await query.message.reply_photo(photo=photo, caption="✅ Your champ is already at full HP.", reply_markup=main_menu_kb(user_id))
            else:
                await edit_menu_message(query, "✅ Your champ is already at full HP.", main_menu_kb(user_id))
            return
        balls = int(p.get("suiballs", 0))
        if balls <= 0:
            heal_image = resolve_heal_image_path()
            no_balls_text = f"❌ You have no Suiballs.\nYou get {DAILY_SUIBALLS} per day (cap {SUIBALL_CAP}).\nUse /inventory."
            if heal_image and query.message:
                with open(heal_image, "rb") as photo:
                    await query.message.reply_photo(photo=photo, caption=no_balls_text, reply_markup=main_menu_kb(user_id))
            else:
                await edit_menu_message(query, no_balls_text, main_menu_kb(user_id))
            return
        p["suiballs"] = balls - 1
        heal_to_full(user_id)
        save_players(players)
        heal_text = (
            f"🧿 Used 1 Suiball on <b>{html.escape(champ_full_name_for_player(user_id, champ_key))}</b>!\n"
            f"❤️ <b>HP restored:</b> {mx}/{mx}\n"
            f"🎒 <b>Remaining Suiballs:</b> {p['suiballs']}"
        )
        heal_image = resolve_heal_image_path()
        if heal_image and query.message:
            with open(heal_image, "rb") as photo:
                await query.message.reply_photo(photo=photo, caption=heal_text, reply_markup=main_menu_kb(user_id), parse_mode="HTML")
        else:
            await edit_menu_message(query, heal_text, main_menu_kb(user_id))
        return

    if action == "namechamp":
        start_nickname_prompt(user_id)
        await edit_menu_message(
            query,
            "📝 <b>Name your champ</b>\n\n"
            "Use <code>/name YourName</code> in chat.\n"
            "Example: <code>/name Joyamon</code>",
            naming_prompt_kb()
        )
        return

    if action not in {"champs", "namechamp", "home"} and needs_nickname_prompt(user_id):
        await edit_menu_message(query, nickname_required_text(user_id), naming_prompt_kb())
        return

    if action == "champs":
        lines = ["📜 Starter Champs", ""]
        for _, c in CHAMPS.items():
            moves = ", ".join([m["name"] for m in c["moves"]])
            lines.append(f"{TYPE_EMOJI[c['type']]} {c['display']}  — type: {c['type']}")
            lines.append(f"   Moves: {moves}")
            lines.append("")
        await edit_menu_message(query, "🌟 <b>Choose your starter</b>\n\n" + "\n".join(lines), choose_champ_kb())
        return

    if action == "fight":
        await edit_menu_message(
            query,
            "⚔️ <b>Fight Menu</b>\n\n"
            "• Reply to a player with <code>/fight</code>\n"
            "• Or type <code>/fight @username</code>\n\n"
            "The challenged player must accept.\n"
            "During battle you pick moves with the buttons.\n"
            "Your champ name will be shown in the fight.",
            main_menu_kb(user_id)
        )
        return

    await edit_menu_message(query, fancy_menu_caption(user_id), main_menu_kb(user_id))

async def choose_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user = await _bootstrap_user(update)
    champ_key = query.data.split("|", 1)[1].strip() if query.data else ""
    if champ_key not in CHAMPS:
        await edit_menu_message(query, "Unknown champ.", main_menu_kb(user))
        return

    if players[user].get("champ") in CHAMPS:
        c = champ_from_key(players[user]["champ"])
        await edit_menu_message(query, f"⚠️ You already chose {c['display']}. This choice is permanent.", main_menu_kb(user))
        return

    players[user]["champ"] = champ_key
    players[user]["level"] = 1
    players[user]["xp"] = 0
    players[user]["wins"] = 0
    players[user]["losses"] = 0
    players[user]["champ_nickname"] = None
    set_current_hp(user, get_stats(champ_key, 1)["hp"])
    players[user]["suiballs"] = max(int(players[user].get("suiballs", 0)), 1)

    c = champ_from_key(champ_key)
    start_nickname_prompt(user)
    save_players(players)
    await edit_menu_message(
        query,
        "📝 <b>Starter selected</b>\n\n"
        f"You picked <b>{c['display']}</b> {TYPE_EMOJI[c['type']]}.\n\n"
        "🚫 You cannot fight yet. First give your champ a custom name.\n\n"
        "Use <code>/name YourName</code>\n"
        "Example: <code>/name Joyamon</code>",
        naming_prompt_kb()
    )

async def battle_move_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_allowed_chat(update, context):
        return
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()

    global players
    players = load_players()  # always read fresh suiball counts

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

    # Always answer query first so Telegram doesn't show loading spinner forever
    await query.answer()

    if kind == "noop":
        return

    if state.get("resolving"):
        # Auto-reset if stuck for more than 30 seconds (network issues)
        resolving_since = float(state.get("resolving_since", 0.0))
        if resolving_since > 0 and (time.monotonic() - resolving_since) > 30:
            state["resolving"] = False
            state["resolving_since"] = 0.0
        else:
            return

    if kind == "ff":
        # forfeit: must be a participant
        if clicker not in (state["user"], state["opponent"]):
            return
        winner = state["opponent"] if clicker == state["user"] else state["user"]
        loser = clicker
        await _battle_push(chat_id, state, context, f"🏳️ {display_name(clicker)} forfeits!", delay=0.25, reply_markup=None)
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
            save_players(players)  # persist suiball deduction immediately
            state["suiballs_used"][clicker] = state.get("suiballs_used", {}).get(clicker, 0) + 1
            healer_champ_state = _battle_turn_champ_state(state)
            healer_champ_state["hp"] = healer_champ_state["max_hp"]
            healer_name = champ_display_for_player(clicker, _battle_turn_champ_key(state))
            await _battle_reposition_message(context.bot, chat_id, state, _battle_render(state), reply_markup=None)
            await _battle_push(chat_id, state, context, f"🧿 {display_name(clicker)} used a Suiball on {healer_name}! HP fully restored!", delay=0.5, reply_markup=None)
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

    # validate turn
    turn_user = _battle_turn_user(state)
    if clicker != turn_user:
        # soft warning (no spam)
        await query.answer("Not your turn.", show_alert=False)
        return

    state["resolving"] = True
    state["resolving_since"] = time.monotonic()

    # Resolve a turn action
    attacker = _battle_turn_champ_state(state)
    defender = _battle_def_champ_state(state)
    a_key = _battle_turn_champ_key(state)
    d_key = _battle_def_champ_key(state)
    a_lvl = _battle_turn_level(state)
    a_name = champ_display_for_player(clicker, a_key)

    # Remove keyboard while resolving (prevents double clicks)
    await _battle_reposition_message(context.bot, chat_id, state, _battle_render(state), reply_markup=None)

    try:
            # status tick at start of turn
        for line in status_tick_lines(attacker, a_name):
            await _battle_push(chat_id, state, context, line, delay=0.45, reply_markup=None)
        if attacker["hp"] <= 0:
            # attacker died to burn
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
                line_out = ("html", f"{STATUS_EMOJI['confuse']} <b>{html.escape(a_name)}</b> {raw}" if "PCP" in str(raw) else f"{STATUS_EMOJI['sleep']} <b>{html.escape(a_name)}</b> {raw}")
            await _battle_push(chat_id, state, context, line_out, delay=0.55, reply_markup=None)
        else:
            # choose move by idx
            try:
                idx = int(parts[2])
            except Exception:
                idx = 0
            moves = champ_from_key(a_key)["moves"]
            idx = max(0, min(idx, len(moves) - 1))
            move = moves[idx]

            before_hp = int(defender["hp"])
            defender_user = state["opponent"] if clicker == state["user"] else state["user"]
            d_lvl = state["lv2"] if clicker == state["user"] else state["lv1"]
            for line in do_move(attacker, defender, a_key, d_key, a_lvl, move, attacker_name=a_name, defender_name=champ_display_for_player(defender_user, d_key), defender_level=d_lvl):
                await _battle_push(chat_id, state, context, line, delay=0.55, reply_markup=None)
            _ = max(0, before_hp - int(defender["hp"]))

        # HUD after action
        attacker["hp"] = max(0, int(attacker["hp"]))
        defender["hp"] = max(0, int(defender["hp"]))
        await _battle_push_hud(chat_id, state, context, delay=0.25, reply_markup=None)

        # Check end
        if state["champ1"]["hp"] <= 0 or state["champ2"]["hp"] <= 0:
            winner = state["user"] if state["champ1"]["hp"] > 0 else state["opponent"]
            loser = state["opponent"] if winner == state["user"] else state["user"]
            await _end_battle(chat_id, state, context, winner=winner, loser=loser)
            return

        state["actions"] += 1
        if state["round"] >= state["max_rounds"]:
            # decide by remaining HP
            if state["champ1"]["hp"] == state["champ2"]["hp"]:
                winner = state["user"] if random.random() < 0.5 else state["opponent"]
            else:
                winner = state["user"] if state["champ1"]["hp"] > state["champ2"]["hp"] else state["opponent"]
            loser = state["opponent"] if winner == state["user"] else state["user"]
            await _battle_push(chat_id, state, context, "⏱️ Time! Battle ends by decision.", delay=0.35, reply_markup=None)
            await _end_battle(chat_id, state, context, winner=winner, loser=loser)
            return

        # next turn
        _battle_next_turn(state)
        await _battle_prompt_turn(chat_id, state, context)
    finally:
        latest = BATTLES.get(chat_id)
        if latest is state:
            state["resolving"] = False

# =========================
# MAIN
# =========================

def main():
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN":
        raise RuntimeError("TOKEN is not set. Hardcode it or inject via env in CI.")

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
    app.add_handler(CallbackQueryHandler(battle_move_callback, pattern=r"^(mv|ff|heal|noop)\|"))

    print("Suimon Arena bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
