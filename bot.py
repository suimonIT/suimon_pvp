import random
import json
import os
import asyncio
import html
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================
# CONFIG
# =========================
# Du willst fürs Erste hardcoden können:
TOKEN = "8429890592:AAHkdeR_2pGp4EOVTT-lBrYAlBlRjK2tW7Y"

DATA_FILE = "players.json"
TZ = timezone.utc  # UTC for all daily resets

# In-memory session state (resets if the bot restarts)
# Keyed by (chat_id, target_user_id) -> {"from": challenger_id, "ts": iso}
PENDING_CHALLENGES: Dict[Tuple[int, str], Dict] = {}
ACTIVE_BATTLES: set[int] = set()

# -------------------------
# Text pacing (seconds)
# -------------------------
INTRO_DELAY = 0.8
COUNTDOWN_STEP_DELAY = 0.55
ACTION_DELAY = 0.70
HUD_DELAY = 0.45
END_DELAY = 0.8

# Keep Telegram message length manageable
MAX_LINES_SHOWN = 70
MAX_MESSAGE_CHARS = 3800  # keep under Telegram 4096 edit limit

# Daily items
DAILY_SUIBALLS = 1
SUIBALL_CAP = 5

# =========================
# CHAMPS (Suimon Starter Set)
# =========================
# Type cycle:
# Fire > Nature, Nature > Water, Water > Fire
CHAMPS: Dict[str, Dict] = {
    "basaurimon": {
        "display": "Basaurimon",
        "type": "nature",
        "base": {"hp": 110, "atk": 19, "def": 12, "spd": 9},
        "moves": [
            {"name": "Vine Whip", "kind": "damage", "power": 40, "acc": 0.95, "text": [
                "lashes out with Vine Whip!",
                "snaps its vines: Vine Whip!",
                "whips the air — Vine Whip!",
            ]},
            {"name": "Razor Leaf", "kind": "damage_highcrit", "power": 46, "acc": 0.92, "crit_bonus": 0.08, "text": [
                "fires spinning blades: Razor Leaf!",
                "scatters sharp leaves — Razor Leaf!",
                "cuts the field with Razor Leaf!",
            ]},
            {"name": "Leaf Storm", "kind": "damage", "power": 55, "acc": 0.88, "text": [
                "unleashes Leaf Storm — razor leaves slice the air!",
                "summons a vortex: Leaf Storm!",
                "calls down a tempest: Leaf Storm!",
            ]},
            {"name": "Sleep Spore", "kind": "status_sleep", "power": 0, "acc": 0.75, "sleep_turns": (1, 2), "text": [
                "scatters Sleep Spore… eyelids grow heavy.",
                "swirls Sleep Spore across the arena!",
                "releases a cloud — Sleep Spore!",
            ]},
        ],
    },
    "suimander": {
        "display": "Suimander",
        "type": "fire",
        "base": {"hp": 102, "atk": 22, "def": 10, "spd": 12},
        "moves": [
            {"name": "Ember", "kind": "damage_burn", "power": 40, "acc": 0.95, "burn_chance": 0.30, "text": [
                "spits sparks: Ember!",
                "launches crackling flames — Ember!",
                "lets embers rain down: Ember!",
            ]},
            {"name": "Flamethrower", "kind": "damage", "power": 55, "acc": 0.90, "text": [
                "blasts a roaring stream: Flamethrower!",
                "turns up the heat — Flamethrower!",
                "scorches the arena with Flamethrower!",
            ]},
            {"name": "Inferno Claw", "kind": "damage_highcrit", "power": 48, "acc": 0.92, "crit_bonus": 0.10, "text": [
                "slashes with Inferno Claw — glowing talons!",
                "rips through the air: Inferno Claw!",
                "carves a fiery arc — Inferno Claw!",
            ]},
            {"name": "Fire Fang", "kind": "damage", "power": 44, "acc": 0.94, "text": [
                "bites in with Fire Fang!",
                "lunges forward — Fire Fang!",
                "snaps its jaws: Fire Fang!",
            ]},
        ],
    },
    "suiqrtle": {
        "display": "Suiqrtle",
        "type": "water",
        "base": {"hp": 115, "atk": 18, "def": 14, "spd": 8},
        "moves": [
            {"name": "Water Gun", "kind": "damage", "power": 40, "acc": 0.96, "text": [
                "fires Water Gun!",
                "blasts a jet — Water Gun!",
                "sprays hard: Water Gun!",
            ]},
            {"name": "Bubble Beam", "kind": "damage", "power": 46, "acc": 0.93, "text": [
                "releases shimmering bubbles: Bubble Beam!",
                "floods the field with Bubble Beam!",
                "bubbles burst everywhere — Bubble Beam!",
            ]},
            {"name": "Aqua Tail", "kind": "damage", "power": 52, "acc": 0.88, "text": [
                "swings a crashing Aqua Tail!",
                "spins and strikes — Aqua Tail!",
                "whips up water: Aqua Tail!",
            ]},
            {"name": "Hydro Burst", "kind": "damage", "power": 60, "acc": 0.82, "text": [
                "builds pressure… Hydro Burst!",
                "unleashes a cannon-blast: Hydro Burst!",
                "detonates a wave: Hydro Burst!",
            ]},
        ],
    },
}

TYPE_EMOJI = {"fire": "🔥", "water": "💧", "nature": "🌿"}
STATUS_EMOJI = {"burn": "🔥", "sleep": "💤"}

CHAMPS_BY_TYPE = {
    "fire": {"strong_against": "nature", "weak_to": "water"},
    "water": {"strong_against": "fire", "weak_to": "nature"},
    "nature": {"strong_against": "water", "weak_to": "fire"},
}

# =========================
# STORAGE
# =========================

def load_players() -> Dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        # Corrupt JSON shouldn't brick the bot
        return {}

def save_players(players: Dict) -> None:
    # Atomic write to avoid broken json on crash
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

players: Dict = load_players()

# =========================
# CORE HELPERS
# =========================

def today_str() -> str:
    return datetime.now(TZ).date().isoformat()

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def champ_from_key(key: str) -> Dict:
    return CHAMPS[key]

def display_name(player_id: str, fallback: str = "Player") -> str:
    p = players.get(player_id, {})
    return (p.get("name") or fallback).strip()

def hp_bar(current: int, max_hp: int, length: int = 8) -> str:
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
    return int(60 + (level - 1) * 18 + (level ** 2) * 3)

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
    base = champ_from_key(champ_key)["base"]
    hp = int(round(base["hp"] + (level - 1) * 9))
    atk = int(round(base["atk"] + (level - 1) * 2))
    df = int(round(base["def"] + (level - 1) * 2))
    spd = int(round(base["spd"] + (level - 1) * 1))
    return {"hp": hp, "atk": atk, "def": df, "spd": spd}

def ensure_player(user_id: str, tg_name: str) -> None:
    if user_id not in players:
        players[user_id] = {
            "name": tg_name,
            "champ": None,
            "level": 1,
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "suiballs": 0,
            "last_daily": None,
            "hp": None,          # persistent HP
            "chats": [],         # chat ids where player is active
        }
    else:
        if tg_name and players[user_id].get("name") != tg_name:
            players[user_id]["name"] = tg_name

def ensure_daily(user_id: str) -> bool:
    p = players[user_id]
    t = today_str()
    if p.get("last_daily") == t:
        return False
    current = int(p.get("suiballs", 0))
    p["suiballs"] = min(SUIBALL_CAP, current + DAILY_SUIBALLS)
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
        return 1.5, "strong"
    if CHAMPS_BY_TYPE[attacker_type]["weak_to"] == defender_type:
        return 0.67, "weak"
    return 1.0, "neutral"

def pick_first_attacker(spd1: int, spd2: int) -> int:
    if spd1 == spd2:
        return 0 if random.random() < 0.5 else 1
    p = clamp(0.5 + (spd1 - spd2) / 40.0, 0.25, 0.75)
    return 0 if random.random() < p else 1

def choose_move(champ_key: str) -> Dict:
    champ = champ_from_key(champ_key)
    return random.choice(champ["moves"])

def calc_damage(attacker_atk: int, defender_def: int, level: int,
                power: int, type_mult_: float, crit_mult: float) -> int:
    effective_def = max(1, int(defender_def))
    base = ((2 * level / 5) + 2) * power * attacker_atk / effective_def
    base = (base / 6) + 2
    base *= random.uniform(0.92, 1.08)
    dmg = int(round(base * type_mult_ * crit_mult))
    return max(1, dmg)

def status_tick_lines(champ_state: Dict, champ_display: str) -> List[str]:
    out: List[str] = []
    if champ_state.get("burn_turns", 0) > 0:
        champ_state["burn_turns"] -= 1
        burn_dmg = max(2, int(round(champ_state["max_hp"] * 0.06)))
        champ_state["hp"] -= burn_dmg
        out.append(f"{STATUS_EMOJI['burn']} {champ_display} is hurt by burn! (-{burn_dmg})")
    return out

def can_act(champ_state: Dict) -> Tuple[bool, List[str]]:
    if champ_state.get("sleep_turns", 0) > 0:
        champ_state["sleep_turns"] -= 1
        return False, ["is asleep and can't move!"]
    return True, []

def do_move(attacker: Dict, defender: Dict, a_key: str, d_key: str, a_level: int, move: Dict) -> List[str]:
    out: List[str] = []

    a = champ_from_key(a_key)
    d = champ_from_key(d_key)
    a_name = a["display"]
    d_name = d["display"]

    if random.random() > float(move.get("acc", 0.9)):
        out.append(f"{TYPE_EMOJI[a['type']]} {a_name} used {move['name']}!")
        out.append("💨 It missed!")
        return out

    out.append(f"{TYPE_EMOJI[a['type']]} {a_name} {random.choice(move.get('text', ['attacks!']))}")

    kind = move.get("kind", "damage")

    if kind == "status_sleep":
        if defender.get("sleep_turns", 0) > 0:
            out.append(f"{STATUS_EMOJI['sleep']} {d_name} is already asleep!")
            return out
        turns = move.get("sleep_turns", (1, 2))
        sleep_t = random.randint(int(turns[0]), int(turns[1]))
        defender["sleep_turns"] = sleep_t
        out.append(f"{STATUS_EMOJI['sleep']} {d_name} fell asleep! ({sleep_t} turn{'s' if sleep_t != 1 else ''})")
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
    )
    defender["hp"] -= dmg

    eff_txt = ""
    if eff == "strong":
        eff_txt = " 💥 Super effective!"
    elif eff == "weak":
        eff_txt = " 🫧 Not very effective…"

    crit_txt = " CRIT!" if crit else ""
    out.append(f"💢 Hit: {dmg} damage{crit_txt}{eff_txt}")

    if kind == "damage_burn":
        if defender.get("burn_turns", 0) == 0 and random.random() < float(move.get("burn_chance", 0.25)):
            defender["burn_turns"] = 3
            out.append(f"{STATUS_EMOJI['burn']} {d_name} was burned! (3 turns)")

    return out

def grant_xp_with_hp_adjust(player_id: str, gained: int) -> None:
    p = players[player_id]
    champ_key = p.get("champ")
    old_level = int(p.get("level", 1))
    old_max = get_stats(champ_key, old_level)["hp"] if champ_key in CHAMPS else 0
    cur_hp = get_or_init_current_hp(player_id)

    p["xp"] = int(p.get("xp", 0)) + int(gained)

    leveled = False
    while p["xp"] >= xp_needed(int(p.get("level", 1))):
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
        if p.get("champ") in CHAMPS and chat_id in p.get("chats", []):
            out.append(uid)
    return out

def _parse_target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        return str(update.message.reply_to_message.from_user.id)
    if context.args:
        arg = context.args[0].lstrip("@").lower().replace(" ", "")
        for uid, p in players.items():
            name = (p.get("name") or "").lower().replace(" ", "")
            if name == arg:
                return uid
    return None

# =========================
# MESSAGE EDIT STREAM (anti-freeze)
# =========================

async def _safe_edit(bot, chat_id: int, message_id: int, text: str) -> None:
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[-MAX_MESSAGE_CHARS:]
    for _ in range(5):
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode='HTML', disable_web_page_preview=True)
            return
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
    ensure_player(user_id, tg_name)

    if update.effective_chat:
        _remember_chat(user_id, int(update.effective_chat.id))

    ensure_daily(user_id)
    save_players(players)
    return user_id

async def intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    p = players[user]
    lines = [
        "🎮 Welcome to Suimon Arena (Classic)!",
        "",
        "━━━ 1) Pick your Starter ━━━",
        "Choose ONE champ (permanent):",
        "• /choose basaurimon  — 🌿 Nature",
        "• /choose suimander   — 🔥 Fire",
        "• /choose suiqrtle    — 💧 Water",
        "",
        "Type chart: 🔥 > 🌿 > 💧 > 🔥",
        "",
        "━━━ 2) Persistent HP ━━━",
        "After every battle, your champ keeps its remaining HP.",
        "If HP hits 0, you must /heal before fighting again.",
        "",
        "━━━ 3) Daily Healing Item ━━━",
        f"Every day you receive {DAILY_SUIBALLS} Suiball (max {SUIBALL_CAP}).",
        "Use: /heal  |  Check: /inventory",
        "",
        "━━━ 4) PvP in Groups ━━━",
        "• If exactly 2 eligible players: /fight starts instantly",
        "• If 3+ eligible players: /fight must target someone (reply or /fight @Name)",
        "  Opponent must accept via buttons.",
        "",
        "━━━ Commands ━━━",
        "/start /intro /champs /choose /profile /inventory /heal /fight",
    ]
    if p.get("champ") not in CHAMPS:
        lines.insert(2, "⚠️ You haven't chosen a champ yet. Pick one with /choose.")
    await update.message.reply_text("\n".join(lines))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    p = players[user]
    champ_key = p.get("champ")
    if champ_key in CHAMPS:
        champ = champ_from_key(champ_key)
        lv = int(p.get("level", 1))
        cur = get_or_init_current_hp(user)
        mx = get_stats(champ_key, lv)["hp"]
        await update.message.reply_text(
            f"✅ You chose {champ['display']} ({TYPE_EMOJI[champ['type']]} {champ['type'].upper()}).\n"
            f"❤️ HP: {cur}/{mx}\n"
            "Use /fight, /heal, /inventory, or /profile."
        )
        save_players(players)
        return
    await update.message.reply_text(
        "🔥 Welcome to Suimon Arena!\n\n"
        "Pick your permanent starter:\n"
        "/choose basaurimon\n"
        "/choose suimander\n"
        "/choose suiqrtle\n\n"
        "Need the full tutorial? Use /intro"
    )

async def champs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _bootstrap_user(update)
    lines = ["📜 Starter Champs", ""]
    for _, c in CHAMPS.items():
        moves = ", ".join([m["name"] for m in c["moves"]])
        lines.append(f"{TYPE_EMOJI[c['type']]} {c['display']}  — type: {c['type']}")
        lines.append(f"   Moves: {moves}")
        lines.append("")
    lines.append("Choose with: /choose basaurimon | suimander | suiqrtle")
    await update.message.reply_text("\n".join(lines))

async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    if not context.args:
        await update.message.reply_text("Usage: /choose basaurimon | suimander | suiqrtle")
        return
    if players[user].get("champ") in CHAMPS:
        await update.message.reply_text("⚠️ You already chose a champ. This choice is permanent.")
        return
    champ_key = champ_key_from_input(context.args[0])
    if champ_key not in CHAMPS:
        await update.message.reply_text("Unknown champ. Use: /champs")
        return
    players[user]["champ"] = champ_key
    players[user]["level"] = 1
    players[user]["xp"] = 0
    players[user]["wins"] = 0
    players[user]["losses"] = 0
    set_current_hp(user, get_stats(champ_key, 1)["hp"])
    players[user]["suiballs"] = max(int(players[user].get("suiballs", 0)), 1)
    save_players(players)
    c = champ_from_key(champ_key)
    await update.message.reply_text(
        f"✅ You chose {c['display']}! {TYPE_EMOJI[c['type']]}\n"
        "You received 1 Suiball. Use /heal when needed.\n\n"
        "Next: /fight in a group, or /intro for the full guide."
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    p = players[user]
    champ_key = p.get("champ")
    if champ_key not in CHAMPS:
        await update.message.reply_text("You have no champ yet. Use /start")
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
    await update.message.reply_text(
        "🪪 Trainer Card\n\n"
        f"👤 {display_name(user)}\n"
        f"🏅 Record: {w}W / {l}L\n\n"
        f"{TYPE_EMOJI[champ['type']]} {champ['display']} (Lv.{lv}){fainted}\n"
        f"❤️ HP: {cur_hp}/{stats['hp']} ({hp_bar(cur_hp, stats['hp'])})\n"
        f"✨ XP: {xp}/{need}\n"
        f"📈 Stats: ATK {stats['atk']} | DEF {stats['def']} | SPD {stats['spd']}\n\n"
        f"🎒 Suiballs: {balls} (daily +{DAILY_SUIBALLS}, cap {SUIBALL_CAP})"
    )

async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    p = players[user]
    champ_key = p.get("champ")
    champ_txt = "None" if champ_key not in CHAMPS else champ_from_key(champ_key)["display"]
    balls = int(p.get("suiballs", 0))
    await update.message.reply_text(
        "🎒 Inventory\n\n"
        f"🧿 Suiballs: {balls}\n"
        f"📅 Daily refresh: {today_str()} (UTC)\n\n"
        "Suiballs heal your active champ to full HP:\n"
        "• /heal\n\n"
        f"Active champ: {champ_txt}"
    )

async def heal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    p = players[user]
    champ_key = p.get("champ")
    if champ_key not in CHAMPS:
        await update.message.reply_text("You have no champ yet. Use /start")
        return
    lv = int(p.get("level", 1))
    mx = get_stats(champ_key, lv)["hp"]
    cur = get_or_init_current_hp(user)
    if cur >= mx:
        await update.message.reply_text("✅ Your champ is already at full HP.")
        return
    balls = int(p.get("suiballs", 0))
    if balls <= 0:
        await update.message.reply_text(
            f"❌ You have no Suiballs.\nYou get {DAILY_SUIBALLS} per day (cap {SUIBALL_CAP}).\nUse /inventory."
        )
        return
    p["suiballs"] = balls - 1
    heal_to_full(user)
    save_players(players)
    champ = champ_from_key(champ_key)
    await update.message.reply_text(
        f"🧿 Used 1 Suiball on {champ['display']}!\n"
        f"❤️ HP restored: {mx}/{mx}\n"
        f"Remaining Suiballs: {p['suiballs']}"
    )

# =========================
# XP + BATTLE
# =========================

def award_battle_xp(winner: str, loser: str) -> Tuple[int, int]:
    xp_winner = 45
    xp_loser = 20
    players[winner]["wins"] = int(players[winner].get("wins", 0)) + 1
    players[loser]["losses"] = int(players[loser].get("losses", 0)) + 1
    grant_xp_with_hp_adjust(winner, xp_winner)
    grant_xp_with_hp_adjust(loser, xp_loser)
    return xp_winner, xp_loser

async def _run_battle(chat_id: int, user: str, opponent: str, context: ContextTypes.DEFAULT_TYPE):
    global players
    players = load_players()

    if chat_id in ACTIVE_BATTLES:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ A battle is already running in this chat. Please wait.")
        return

    ACTIVE_BATTLES.add(chat_id)
    try:
        msg = await context.bot.send_message(chat_id=chat_id, text="⚔️ SUIMON BATTLE")
        message_id = msg.message_id

        log_lines: List[str] = []
        last_edit_at: float = 0.0

        def esc(s: str) -> str:
            return html.escape(s, quote=False)

        def make_hud(c1_label: str, hp1: int, max1: int, c2_label: str, hp2: int, max2: int) -> str:
            hud_txt = battle_hud(c1_label, hp1, max1, c2_label, hp2, max2)
            return f"<pre>{html.escape(hud_txt, quote=False)}</pre>"

        def render() -> str:
            # Keep last N blocks, always valid HTML (each HUD is a self-contained <pre>..</pre>)
            if len(log_lines) > MAX_LINES_SHOWN:
                del log_lines[:-MAX_LINES_SHOWN]
            body = "\n".join(log_lines) if log_lines else "…"
            # Trim by chars
            while len(body) > MAX_MESSAGE_CHARS and len(log_lines) > 8:
                del log_lines[:3]
                body = "\n".join(log_lines)
            if len(body) > MAX_MESSAGE_CHARS:
                body = body[-MAX_MESSAGE_CHARS:]
            return body

        async def flush(delay: float = 0.0, force: bool = False) -> None:
            nonlocal last_edit_at
            # throttle edits a bit to reduce Telegram lag spikes
            now = asyncio.get_running_loop().time()
            if not force:
                min_gap = 0.55
                wait = (last_edit_at + min_gap) - now
                if wait > 0:
                    await asyncio.sleep(wait)

            body = render()
            await _safe_edit(context.bot, chat_id, message_id, body)
            last_edit_at = asyncio.get_running_loop().time()

            if delay > 0:
                await asyncio.sleep(delay)

        async def push(line: str, delay: float = ACTION_DELAY) -> None:
            # narrative line
            log_lines.append(esc(line))
            await flush(delay)

        async def push_blank(delay: float = 0.0) -> None:
            log_lines.append("")
            await flush(delay)

        async def push_hud(c1_label: str, hp1: int, max1: int, c2_label: str, hp2: int, max2: int, delay: float = HUD_DELAY) -> None:
            log_lines.append(make_hud(c1_label, hp1, max1, c2_label, hp2, max2))
            await flush(delay)

        if user not in players or opponent not in players:
            await push("❌ One of the players is not registered. Use /start first.", delay=0.1)
            return

        p1 = players[user]
        p2 = players[opponent]

        if p1.get("champ") not in CHAMPS or p2.get("champ") not in CHAMPS:
            await push("❌ Both players must /choose a champ first.", delay=0.1)
            return

        p1_name = display_name(user, "Player A")
        p2_name = display_name(opponent, "Player B")

        c1_key = p1["champ"]
        c2_key = p2["champ"]
        c1 = champ_from_key(c1_key)
        c2 = champ_from_key(c2_key)

        lv1 = int(p1.get("level", 1))
        lv2 = int(p2.get("level", 1))
        s1 = get_stats(c1_key, lv1)
        s2 = get_stats(c2_key, lv2)

        p1_cur_hp = get_or_init_current_hp(user)
        p2_cur_hp = get_or_init_current_hp(opponent)

        if p1_cur_hp <= 0:
            await push(f"❌ {p1_name}'s {c1['display']} has fainted (HP 0). Use /heal first.")
            return
        if p2_cur_hp <= 0:
            await push(f"❌ {p2_name}'s {c2['display']} has fainted (HP 0). They must /heal first.")
            return

        champ1 = {"hp": int(p1_cur_hp), "max_hp": s1["hp"], "atk": s1["atk"], "def": s1["def"], "spd": s1["spd"], "burn_turns": 0, "sleep_turns": 0}
        champ2 = {"hp": int(p2_cur_hp), "max_hp": s2["hp"], "atk": s2["atk"], "def": s2["def"], "spd": s2["spd"], "burn_turns": 0, "sleep_turns": 0}

        c1_label = f"{p1_name} - {c1['display']} (Lv.{lv1})"
        c2_label = f"{p2_name} - {c2['display']} (Lv.{lv2})"

        await push("⚔️ BATTLE START ⚔️", delay=0.35)
        await push(f"👤 {p1_name} sends out {c1['display']}!", delay=0.45)
        await push(f"👤 {p2_name} sends out {c2['display']}!", delay=0.45)
        await push_hud(c1_label, champ1["hp"], champ1["max_hp"], c2_label, champ2["hp"], champ2["max_hp"], delay=0.4)

        for t in ("3…", "2…", "1…", "GO!"):
            await push(t, delay=COUNTDOWN_STEP_DELAY)

        first = pick_first_attacker(int(champ1["spd"]), int(champ2["spd"]))
        starter_name = c1["display"] if first == 0 else c2["display"]
        await push(f"🏁 {starter_name} moves first!", delay=0.55)

        round_counter = 1
        MAX_ROUNDS = 24
        dmg1_total = 0
        dmg2_total = 0

        while champ1["hp"] > 0 and champ2["hp"] > 0 and round_counter <= MAX_ROUNDS:
            await push(f"━━━ Round {round_counter} ━━━", delay=0.55)

            turn_order = [0, 1] if first == 0 else [1, 0]
            for who in turn_order:
                if champ1["hp"] <= 0 or champ2["hp"] <= 0:
                    break

                attacker = champ1 if who == 0 else champ2
                defender = champ2 if who == 0 else champ1
                a_key = c1_key if who == 0 else c2_key
                d_key = c2_key if who == 0 else c1_key
                a_lvl = lv1 if who == 0 else lv2
                a_name = champ_from_key(a_key)["display"]

                for line in status_tick_lines(attacker, a_name):
                    await push(line, delay=0.65)
                if attacker["hp"] <= 0:
                    break

                ok, sleep_lines = can_act(attacker)
                if not ok:
                    await push(f"{STATUS_EMOJI['sleep']} {a_name} {sleep_lines[0]}", delay=0.7)
                else:
                    move = choose_move(a_key)
                    before_hp = defender["hp"]
                    for line in do_move(attacker, defender, a_key, d_key, a_lvl, move):
                        await push(line, delay=0.65)
                    dealt = max(0, before_hp - defender["hp"])
                    if who == 0:
                        dmg1_total += dealt
                    else:
                        dmg2_total += dealt

                await push_hud(
                    c1_label, max(champ1["hp"], 0), champ1["max_hp"],
                    c2_label, max(champ2["hp"], 0), champ2["max_hp"],
                    delay=0.35,
                )

            round_counter += 1

        if champ1["hp"] > 0 and champ2["hp"] <= 0:
            winner, loser = user, opponent
            w_name, w_champ = p1_name, c1["display"]
        elif champ2["hp"] > 0 and champ1["hp"] <= 0:
            winner, loser = opponent, user
            w_name, w_champ = p2_name, c2["display"]
        else:
            if dmg1_total >= dmg2_total:
                winner, loser = user, opponent
                w_name, w_champ = p1_name, c1["display"]
            else:
                winner, loser = opponent, user
                w_name, w_champ = p2_name, c2["display"]

        await push("The dust settles…", delay=0.6)
        await push(f"🏆 Winner: {w_name} with {w_champ}!", delay=0.6)

        xp_w, xp_l = award_battle_xp(winner, loser)
        await push(f"🎁 XP: {xp_w} (Winner) / {xp_l} (Loser)", delay=0.5)

        set_current_hp(user, int(max(champ1["hp"], 0)))
        set_current_hp(opponent, int(max(champ2["hp"], 0)))
        save_players(players)

        max1_after = int(get_stats(c1_key, int(players[user].get("level", 1)))["hp"])
        max2_after = int(get_stats(c2_key, int(players[opponent].get("level", 1)))["hp"])

        await push("📌 Persistent HP saved", delay=0.4)
        await push(f"❤️ {c1['display']}: {max(champ1['hp'],0)}/{max1_after}", delay=0.25)
        await push(f"💙 {c2['display']}: {max(champ2['hp'],0)}/{max2_after}", delay=0.4)

        lvlups = []
        if players[user].get("just_leveled"):
            lvlups.append((p1_name, players[user]["level"]))
            players[user]["just_leveled"] = False
        if players[opponent].get("just_leveled"):
            lvlups.append((p2_name, players[opponent]["level"]))
            players[opponent]["just_leveled"] = False
        if lvlups:
            await push("📣 Level Up!", delay=0.35)
            for n, lv in lvlups:
                await push(f"⭐ {n} is now Lv.{lv}!", delay=0.4)

        save_players(players)
        await push("✅ Battle complete.", delay=END_DELAY)

    finally:
        ACTIVE_BATTLES.discard(chat_id)

# =========================
# PvP COMMANDS
# =========================

async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    chat = update.effective_chat
    if not chat or not update.message:
        return
    chat_id = int(chat.id)

    if players[user].get("champ") not in CHAMPS:
        await update.message.reply_text("⚠️ Choose your champ first with /choose (or /start).")
        return

    eligible = [uid for uid in _eligible_players_in_chat(chat_id) if uid != user]
    if not eligible:
        await update.message.reply_text("No opponents in this chat yet. Ask someone to /choose first!")
        return

    if len(eligible) == 1:
        await _run_battle(chat_id, user, eligible[0], context)
        return

    target = _parse_target_user_id(update, context)
    if not target or target not in eligible:
        await update.message.reply_text(
            "Multiple opponents found.\n"
            "Reply to a player's message with /fight, or use /fight @Name."
        )
        return

    PENDING_CHALLENGES[(chat_id, target)] = {"from": user, "ts": datetime.now(TZ).isoformat()}

    challenger_name = display_name(user, "Challenger")
    target_name = display_name(target, "Opponent")

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"suimon_accept|{user}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"suimon_decline|{user}"),
    ]])

    await update.message.reply_text(
        f"⚔️ {challenger_name} challenges {target_name}!\n"
        f"{target_name}, do you accept?",
        reply_markup=kb,
    )

async def challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()

    data = query.data or ""
    try:
        action, challenger = data.split("|", 1)
    except ValueError:
        await query.edit_message_text("Invalid challenge data.")
        return

    chat_id = int(query.message.chat.id)
    opponent = str(query.from_user.id)

    key = (chat_id, opponent)
    payload = PENDING_CHALLENGES.get(key)
    if not payload:
        await query.edit_message_text("⚠️ Challenge expired or already handled.")
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

    await query.edit_message_text("✅ Accepted! Battle starting…")
    await _run_battle(chat_id, str(challenger), opponent, context)

# =========================
# MAIN
# =========================

def main():
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN":
        raise RuntimeError("TOKEN is not set. Hardcode it or inject via env in CI.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("intro", intro))
    app.add_handler(CommandHandler("champs", champs_cmd))
    app.add_handler(CommandHandler("choose", choose))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("inventory", inventory))
    app.add_handler(CommandHandler("heal", heal))
    app.add_handler(CommandHandler("fight", fight))
    app.add_handler(CallbackQueryHandler(challenge_callback, pattern=r"^suimon_(accept|decline)\|"))

    print("Suimon Arena bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
