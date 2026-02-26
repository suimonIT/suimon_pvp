import random
import json
import os
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================
# CONFIG
# =========================
TOKEN = "YOUR_BOT_TOKEN"
DATA_FILE = "players.json"
TZ = timezone.utc  # UTC for all daily resets

# In-memory session state (resets if the bot restarts)
PENDING_CHALLENGES: Dict[Tuple[int, str], Dict] = {}
ACTIVE_BATTLES: set[int] = set()

# -------------------------
# Text pacing (seconds)
# Raise values to slow down
# -------------------------
INTRO_DELAY = 3.0
TEASER_DELAY = 1.6
COUNTDOWN_STEP_DELAY = 1.8
ACTION_DELAY = 3.0
ROUND_BREAK_DELAY = 2.2
STATUS_TICK_DELAY = 2.0
LEVELUP_DELAY = 2.2
END_DELAY = 2.0

# Keep Telegram message length manageable (old lines are trimmed)
MAX_LINES_SHOWN = 80

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
        "strong": "water",
        "weak": "fire",
        "base": {"hp": 110, "atk": 19, "def": 12, "spd": 9},
        "moves": [
            {
                "name": "Vine Whip",
                "kind": "damage",
                "power": 40,
                "acc": 0.95,
                "text": [
                    "lashes out with **Vine Whip**!",
                    "snaps its vines: **Vine Whip**!",
                    "whips the air — **Vine Whip**!",
                ],
            },
            {
                "name": "Razor Leaf",
                "kind": "damage_highcrit",
                "power": 46,
                "acc": 0.92,
                "crit_bonus": 0.08,
                "text": [
                    "fires spinning blades: **Razor Leaf**!",
                    "scatters sharp leaves — **Razor Leaf**!",
                    "cuts the field with **Razor Leaf**!",
                ],
            },
            {
                "name": "Leaf Storm",
                "kind": "damage",
                "power": 55,
                "acc": 0.88,
                "text": [
                    "unleashes **Leaf Storm** — razor leaves slice the air!",
                    "summons a vortex: **Leaf Storm**!",
                    "calls down a tempest: **Leaf Storm**!",
                ],
            },
            {
                "name": "Sleep Spore",
                "kind": "status_sleep",
                "power": 0,
                "acc": 0.75,
                "sleep_turns": (1, 2),
                "text": [
                    "scatters **Sleep Spore**… eyelids grow heavy.",
                    "swirls **Sleep Spore** across the arena!",
                    "releases a cloud — **Sleep Spore**!",
                ],
            },
        ],
    },
    "suimander": {
        "display": "Suimander",
        "type": "fire",
        "strong": "nature",
        "weak": "water",
        "base": {"hp": 102, "atk": 22, "def": 10, "spd": 12},
        "moves": [
            {
                "name": "Ember",
                "kind": "damage_burn",
                "power": 40,
                "acc": 0.95,
                "burn_chance": 0.30,
                "text": [
                    "spits sparks: **Ember**!",
                    "launches crackling flames — **Ember**!",
                    "lets embers rain down: **Ember**!",
                ],
            },
            {
                "name": "Flamethrower",
                "kind": "damage",
                "power": 55,
                "acc": 0.90,
                "text": [
                    "blasts a roaring stream: **Flamethrower**!",
                    "turns up the heat — **Flamethrower**!",
                    "scorches the arena with **Flamethrower**!",
                ],
            },
            {
                "name": "Inferno Claw",
                "kind": "damage_highcrit",
                "power": 48,
                "acc": 0.92,
                "crit_bonus": 0.10,
                "text": [
                    "slashes with **Inferno Claw** — glowing talons!",
                    "rips through the air: **Inferno Claw**!",
                    "carves a fiery arc — **Inferno Claw**!",
                ],
            },
            {
                "name": "Fire Fang",
                "kind": "damage",
                "power": 44,
                "acc": 0.94,
                "text": [
                    "bites in with **Fire Fang**!",
                    "lunges forward — **Fire Fang**!",
                    "snaps its jaws: **Fire Fang**!",
                ],
            },
        ],
    },
    "suiqrtle": {
        "display": "Suiqrtle",
        "type": "water",
        "strong": "fire",
        "weak": "nature",
        "base": {"hp": 115, "atk": 18, "def": 14, "spd": 8},
        "moves": [
            {
                "name": "Water Gun",
                "kind": "damage",
                "power": 40,
                "acc": 0.96,
                "text": [
                    "fires **Water Gun**!",
                    "blasts a jet — **Water Gun**!",
                    "sprays hard: **Water Gun**!",
                ],
            },
            {
                "name": "Bubble Beam",
                "kind": "damage",
                "power": 46,
                "acc": 0.93,
                "text": [
                    "releases shimmering bubbles: **Bubble Beam**!",
                    "floods the field with **Bubble Beam**!",
                    "bubbles burst everywhere — **Bubble Beam**!",
                ],
            },
            {
                "name": "Aqua Tail",
                "kind": "damage",
                "power": 52,
                "acc": 0.88,
                "text": [
                    "swings a crashing **Aqua Tail**!",
                    "spins and strikes — **Aqua Tail**!",
                    "whips up water: **Aqua Tail**!",
                ],
            },
            {
                "name": "Hydro Burst",
                "kind": "damage",
                "power": 60,
                "acc": 0.82,
                "text": [
                    "builds pressure… **Hydro Burst**!",
                    "unleashes a cannon-blast: **Hydro Burst**!",
                    "detonates a wave: **Hydro Burst**!",
                ],
            },
        ],
    },
}

TYPE_EMOJI = {"fire": "🔥", "water": "💧", "nature": "🌿"}
EFFECT_EMOJI = {"strong": "💥", "weak": "🫧", "neutral": "⚔️", "miss": "💨"}
STATUS_EMOJI = {"burn": "🔥", "sleep": "💤"}

# Type lookup helper
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
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_players(players: Dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)


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
    return p.get("name") or fallback



def md_escape(s: str) -> str:
    """Escape basic Markdown special chars for parse_mode='Markdown'."""
    if s is None:
        return ""
    # Escape characters that can break Markdown formatting
    for ch in ["_", "*", "`", "[", "]"]:
        s = s.replace(ch, f"\\{ch}")
    return s

def hp_bar(current: int, max_hp: int, length: int = 8) -> str:
    """Readable HP bar (text blocks)."""
    mx = max(1, int(max_hp))
    cur = max(0, min(int(current), mx))
    filled = int(round((cur / mx) * length))
    return "█" * filled + "░" * (length - filled)


def format_hp_line(label: str, current: int, max_hp: int) -> str:
    """Plain (non-markdown) HP line for HUD blocks."""
    mx = max(1, int(max_hp))
    cur = max(0, min(int(current), mx))
    return f"{label}
HP {cur:>3}/{mx:<3} [{hp_bar(cur, mx)}]"


def battle_hud(p1_label: str, hp1: int, max1: int, p2_label: str, hp2: int, max2: int) -> str:
    """Monospace HUD card."""
    return "```text
" + format_hp_line(p1_label, hp1, max1) + "

" + format_hp_line(p2_label, hp2, max2) + "
```"


def xp_needed(level: int) -> int:
    # Fast early, slower later
    return int(60 + (level - 1) * 18 + (level**2) * 3)


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
            # persistent resources
            "suiballs": 0,
            "last_daily": None,
            # persistent champ HP (0..max)
            "hp": None,
            # chats where the user is active
            "chats": [],
        }
    else:
        # keep name updated
        if tg_name and players[user_id].get("name") != tg_name:
            players[user_id]["name"] = tg_name


def ensure_daily(user_id: str) -> bool:
    """Grant daily Suiball once per day. Returns True if a ball was granted."""
    p = players[user_id]
    t = today_str()
    last = p.get("last_daily")
    if last == t:
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
    # If max HP changed due to level ups while user was at full/partial,
    # keep the same HP percentage (rounded), but never exceed max.
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
    p = players[user_id]
    champ_key = p.get("champ")
    lv = int(p.get("level", 1))
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
    legal = [m for m in champ["moves"] if m["kind"].startswith("damage") or m["kind"].startswith("status_")]
    return random.choice(legal)


def calc_damage(attacker_atk: int, defender_def: int, level: int,
                power: int, type_mult_: float, crit_mult: float) -> int:
    effective_def = max(1, int(defender_def))
    base = ((2 * level / 5) + 2) * power * attacker_atk / effective_def
    base = (base / 6) + 2
    base *= random.uniform(0.92, 1.08)
    dmg = int(round(base * type_mult_ * crit_mult))
    return max(1, dmg)


def format_effect(effect_key: str) -> str:
    if effect_key == "strong":
        return f" {EFFECT_EMOJI['strong']} **It's super effective!**"
    if effect_key == "weak":
        return f" {EFFECT_EMOJI['weak']} **It's not very effective…**"
    return ""


def status_tick_lines(champ_state: Dict, champ_display: str) -> List[str]:
    out: List[str] = []
    # Burn tick
    if champ_state.get("burn_turns", 0) > 0:
        champ_state["burn_turns"] -= 1
        burn_dmg = max(2, int(round(champ_state["max_hp"] * 0.06)))
        champ_state["hp"] -= burn_dmg
        out.append(f"{STATUS_EMOJI['burn']} **{champ_display}** is hurt by burn! (-{burn_dmg})")
    # Sleep countdown happens when trying to act
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

    # Accuracy check
    if random.random() > float(move.get("acc", 0.9)):
        out.append(f"{TYPE_EMOJI[a['type']]} **{a_name}** used **{move['name']}**!")
        out.append(f"{EFFECT_EMOJI['miss']} It missed!")
        return out

    # Narrative line
    out.append(f"{TYPE_EMOJI[a['type']]} **{a_name}** {random.choice(move.get('text', ['attacks!']))}")

    kind = move.get("kind", "damage")

    # Status: Sleep
    if kind == "status_sleep":
        if defender.get("sleep_turns", 0) > 0:
            out.append(f"{STATUS_EMOJI['sleep']} **{d_name}** is already asleep!")
            return out
        turns = move.get("sleep_turns", (1, 2))
        sleep_t = random.randint(int(turns[0]), int(turns[1]))
        defender["sleep_turns"] = sleep_t
        out.append(f"{STATUS_EMOJI['sleep']} **{d_name}** fell asleep! ({sleep_t} turn{'s' if sleep_t != 1 else ''})")
        return out

    # Damage
    power = int(move.get("power", 40))

    # Crit
    crit_chance = 0.08
    if kind == "damage_highcrit":
        crit_chance += float(move.get("crit_bonus", 0.08))
    crit = random.random() < crit_chance
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

    crit_txt = " **CRIT!**" if crit else ""
    out.append(f"💢 Hit: **{dmg}** damage{crit_txt}{format_effect(eff)}")

    # Burn application
    if kind == "damage_burn":
        if defender.get("burn_turns", 0) == 0 and random.random() < float(move.get("burn_chance", 0.25)):
            defender["burn_turns"] = 3
            out.append(f"{STATUS_EMOJI['burn']} **{d_name}** was burned! (3 turns)")

    return out


def grant_xp_with_hp_adjust(player_id: str, gained: int) -> List[str]:
    """Grant XP and handle level-ups. If max HP increases, current HP increases by the same delta."""
    p = players[player_id]

    # Capture old max HP for delta
    champ_key = p.get("champ")
    old_level = int(p.get("level", 1))
    old_max = get_stats(champ_key, old_level)["hp"] if champ_key in CHAMPS else 0
    cur_hp = get_or_init_current_hp(player_id)

    p["xp"] = int(p.get("xp", 0)) + int(gained)

    levelups: List[str] = []
    while p["xp"] >= xp_needed(int(p.get("level", 1))):
        need = xp_needed(int(p.get("level", 1)))
        p["xp"] -= need
        p["level"] = int(p.get("level", 1)) + 1

        new_level = int(p["level"])
        new_max = get_stats(champ_key, new_level)["hp"] if champ_key in CHAMPS else old_max
        # Increase current HP by the max HP increase (classic-feel reward)
        delta = max(0, new_max - old_max)
        cur_hp = min(new_max, cur_hp + delta)
        old_max = new_max

        set_current_hp(player_id, cur_hp)
        levelups.append(f"✨ **{display_name(player_id)}** reached **Lv.{p['level']}**!")

    # Persist current HP even without level-up
    set_current_hp(player_id, cur_hp)
    return levelups


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
    # Prefer reply target
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        return str(update.message.reply_to_message.from_user.id)
    # Then @mention argument (best-effort match by stored name)
    if context.args:
        arg = context.args[0].lstrip("@").lower()
        for uid, p in players.items():
            name = (p.get("name") or "").lower().replace(" ", "")
            if name == arg:
                return uid
    return None


# =========================
# UI HELPERS
# =========================

async def edit_battle(msg, lines: List[str], delay: float) -> None:
    if len(lines) > MAX_LINES_SHOWN:
        lines[:] = lines[-MAX_LINES_SHOWN:]
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    await asyncio.sleep(delay)


async def countdown_animation(msg, lines: List[str]) -> None:
    for t in ["3", "2", "1", "⚡"]:
        lines.append(f"⏳ {t}…")
        await edit_battle(msg, lines, COUNTDOWN_STEP_DELAY)


# =========================
# COMMANDS
# =========================

async def _bootstrap_user(update: Update) -> str:
    """Ensure the user exists, apply daily grant, and remember the chat."""
    global players
    # Always reload from disk so callbacks/commands share the latest state.
    players = load_players()

    user_id = str(update.effective_user.id)
    tg_name = (update.effective_user.first_name or "Player").strip()
    ensure_player(user_id, tg_name)

    # Track which chats this user is active in (important for /fight opponent discovery)
    if update.effective_chat:
        _remember_chat(user_id, int(update.effective_chat.id))

    granted = ensure_daily(user_id)
    if granted and update.message:
        # Keep daily grant silent by default to avoid spam
        pass
    save_players(players)
    return user_id

async def intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    p = players[user]

    lines = [
        "🎮 **Welcome to Suimon Arena (Classic)!**",
        "",
        "You are a Trainer. Your champ fights for you — **players do not attack directly**.",
        "",
        "━━━ **1) Pick your Starter** ━━━",
        "Choose **ONE** champ (permanent):",
        "• /choose basaurimon  — 🌿 Nature",
        "• /choose suimander   — 🔥 Fire",
        "• /choose suiqrtle    — 💧 Water",
        "",
        "Type chart:",
        "🔥 Fire > 🌿 Nature > 💧 Water > 🔥 Fire",
        "",
        "━━━ **2) Your Champ Has Persistent HP** ━━━",
        "After every battle, your champ keeps its **remaining HP**.",
        "If your HP reaches **0**, your champ **faints** and cannot battle until healed.",
        "",
        "━━━ **3) Daily Healing Item: Suiballs** ━━━",
        f"Every day you receive **{DAILY_SUIBALLS} Suiball** (max {SUIBALL_CAP} stored).",
        "Use one to heal your champ to full:",
        "• /heal",
        "Check your items:",
        "• /inventory",
        "",
        "━━━ **4) Battles in Groups** ━━━",
        "• If the group has **exactly 2 eligible players**, /fight starts instantly.",
        "• If there are **3+ players**, you must challenge someone:",
        "   – Reply to their message with /fight",
        "   – Or /fight @Name (best-effort)",
        "Then the opponent must **Accept**.",
        "",
        "━━━ **5) Battle System (Classic Feel)** ━━━",
        "• Speed influences who moves first",
        "• Accuracy & Misses",
        "• Critical hits",
        "• Status effects: **Burn** (damage over time) and **Sleep** (skip turns)",
        "• Pokémon-style effectiveness text",
        "",
        "━━━ **6) Progression** ━━━",
        "Win or lose, you gain XP.",
        "Level-ups increase your stats (including Max HP).",
        "",
        "━━━ **Commands** ━━━",
        "• /start — quick start",
        "• /intro — this tutorial",
        "• /champs — view champ info",
        "• /profile — your trainer card",
        "• /inventory — items",
        "• /heal — spend 1 Suiball to heal",
        "• /fight — battle!",
        "",
        "✨ Tip: The battle text speed can be tuned via the DELAY constants at the top of the file.",
    ]

    # If user hasn't picked, add a friendly note.
    if p.get("champ") not in CHAMPS:
        lines.insert(2, "⚠️ You haven't chosen a champ yet. Pick one with /choose.")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
            f"✅ You chose **{champ['display']}** ({TYPE_EMOJI[champ['type']]} {champ['type'].upper()}).\n"
            f"❤️ HP: **{cur}/{mx}**\n"
            f"Use /fight, /heal, /inventory, or /profile.",
            parse_mode="Markdown",
        )
        save_players(players)
        return

    await update.message.reply_text(
        "🔥 **Welcome to Suimon Arena!**\n\n"
        "Pick your permanent starter:\n"
        "/choose basaurimon\n"
        "/choose suimander\n"
        "/choose suiqrtle\n\n"
        "Need the full tutorial? Use /intro",
        parse_mode="Markdown",
    )


async def champs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _bootstrap_user(update)

    lines = ["📜 **Starter Champs**", ""]
    for k, c in CHAMPS.items():
        moves = ", ".join([m["name"] for m in c["moves"]])
        lines.append(f"{TYPE_EMOJI[c['type']]} **{c['display']}**  —  type: **{c['type']}**")
        lines.append(f"   Moves: {moves}")
        lines.append("")

    lines.append("Choose with: /choose basaurimon | suimander | suiqrtle")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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

    # Init HP at full
    set_current_hp(user, get_stats(champ_key, 1)["hp"])

    # Give a starter Suiball so they can learn healing
    players[user]["suiballs"] = max(int(players[user].get("suiballs", 0)), 1)

    save_players(players)

    c = champ_from_key(champ_key)
    await update.message.reply_text(
        f"✅ You chose **{c['display']}**! {TYPE_EMOJI[c['type']]}\n"
        f"You received **1 Suiball**. Use /heal when needed.\n\n"
        "Next: /fight in a group, or /intro for the full guide.",
        parse_mode="Markdown",
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
        "🪪 **Trainer Card**\n\n"
        f"👤 **{display_name(user)}**\n"
        f"🏅 Record: **{w}W / {l}L**\n\n"
        f"{TYPE_EMOJI[champ['type']]} **{champ['display']}** (Lv.{lv}){fainted}\n"
        f"❤️ HP: **{cur_hp}/{stats['hp']}**  ({hp_bar(cur_hp, stats['hp'])})\n"
        f"✨ XP: **{xp}/{need}**\n"
        f"📈 Stats: ATK **{stats['atk']}** | DEF **{stats['def']}** | SPD **{stats['spd']}**\n\n"
        f"🎒 Suiballs: **{balls}** (daily +{DAILY_SUIBALLS}, cap {SUIBALL_CAP})\n"
        "Use /inventory or /heal.",
        parse_mode="Markdown",
    )


async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _bootstrap_user(update)
    p = players[user]

    champ_key = p.get("champ")
    champ_txt = "None" if champ_key not in CHAMPS else champ_from_key(champ_key)["display"]

    granted = False
    # We already called ensure_daily in bootstrap, but don't spam notify. Here it's fine to show info.
    # Determine if they *would* have gotten one today by checking last_daily.
    # We'll just show current counts + today's date.

    balls = int(p.get("suiballs", 0))
    await update.message.reply_text(
        "🎒 **Inventory**\n\n"
        f"🧿 Suiballs: **{balls}**\n"
        f"📅 Daily refresh: **{today_str()}** (UTC)\n\n"
        "Suiballs heal your active champ to full HP:\n"
        "• /heal\n\n"
        f"Active champ: **{champ_txt}**",
        parse_mode="Markdown",
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
            "❌ You have no Suiballs.\n"
            f"You get **{DAILY_SUIBALLS}** per day (cap {SUIBALL_CAP}).\n"
            "Use /inventory to check your items.",
            parse_mode="Markdown",
        )
        return

    p["suiballs"] = balls - 1
    heal_to_full(user)
    save_players(players)

    champ = champ_from_key(champ_key)
    await update.message.reply_text(
        f"🧿 Used **1 Suiball** on **{champ['display']}**!\n"
        f"❤️ HP restored: **{mx}/{mx}**\n"
        f"Remaining Suiballs: **{p['suiballs']}**",
        parse_mode="Markdown",
    )


# =========================
# BATTLE ENGINE
# =========================

async def _run_battle(chat_id: int, user: str, opponent: str, context: ContextTypes.DEFAULT_TYPE):
    """Runs a full battle with paced, message-by-message narration (no giant edited wall)."""

    # Load latest player data (callbacks don't share locals)
    global players
    players = load_players()

    async def send_plain(text: str) -> None:
        await context.bot.send_message(chat_id=chat_id, text=text)

    async def send_md(text: str) -> None:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

    async def beat(text: str, *, md: bool = False, delay: float = 0.75) -> None:
        """Send 1 line, then wait a bit (cinematic pacing)."""
        if md:
            await send_md(text)
        else:
            await send_plain(text)
        if delay > 0:
            await asyncio.sleep(delay)

    if chat_id in ACTIVE_BATTLES:
        await send_plain("⚠️ A battle is already running in this chat. Please wait.")
        return

    ACTIVE_BATTLES.add(chat_id)
    try:
        p1 = players[user]
        p2 = players[opponent]

        p1_name_raw = display_name(user, "Player A")
        p2_name_raw = display_name(opponent, "Player B")

        # Markdown-safe trainer names for narration
        p1_name = md_escape(p1_name_raw)
        p2_name = md_escape(p2_name_raw)

        c1_key = p1["champ"]
        c2_key = p2["champ"]

        c1 = champ_from_key(c1_key)
        c2 = champ_from_key(c2_key)

        lv1 = int(p1.get("level", 1))
        lv2 = int(p2.get("level", 1))

        s1 = get_stats(c1_key, lv1)
        s2 = get_stats(c2_key, lv2)

        # Persistent HP
        p1_cur_hp = get_or_init_current_hp(user)
        p2_cur_hp = get_or_init_current_hp(opponent)

        if p1_cur_hp <= 0:
            await send_md(f"❌ **{p1_name}**'s **{c1['display']}** has fainted (HP 0). Use /heal first.")
            return
        if p2_cur_hp <= 0:
            await send_md(f"❌ **{p2_name}**'s **{c2['display']}** has fainted (HP 0). They must /heal first.")
            return

        champ1 = {"hp": int(p1_cur_hp), "max_hp": s1["hp"], "atk": s1["atk"], "def": s1["def"], "spd": s1["spd"], "burn_turns": 0, "sleep_turns": 0}
        champ2 = {"hp": int(p2_cur_hp), "max_hp": s2["hp"], "atk": s2["atk"], "def": s2["def"], "spd": s2["spd"], "burn_turns": 0, "sleep_turns": 0}

        # Trainer-tagged labels (important when both have same champ)
        c1_label_md = f"{p1_name}'s {c1['display']}"
        c2_label_md = f"{p2_name}'s {c2['display']}"
        c1_label_plain = f"{p1_name_raw} - {c1['display']} (Lv.{lv1})"
        c2_label_plain = f"{p2_name_raw} - {c2['display']} (Lv.{lv2})"

        # Intro (line by line)
        await beat("⚔️ **BATTLE START** ⚔️", md=True, delay=0.7)
        await beat(f"👤 **{p1_name}** sends out **{c1_label_md}**!", md=True, delay=0.8)
        await beat(f"👤 **{p2_name}** sends out **{c2_label_md}**!", md=True, delay=0.8)
        await send_plain(battle_hud(c1_label_plain, champ1["hp"], champ1["max_hp"], c2_label_plain, champ2["hp"], champ2["max_hp"]))
        await asyncio.sleep(0.9)

        # Countdown
        for t in ("3…", "2…", "1…", "GO!"):
            await beat(t, md=False, delay=0.6)

        first = pick_first_attacker(int(champ1["spd"]), int(champ2["spd"]))
        starter_name = c1["display"] if first == 0 else c2["display"]
        await beat(f"🏁 **{starter_name}** moves first!", md=True, delay=0.9)

        round_counter = 1
        dmg1_total = 0
        dmg2_total = 0

        while champ1["hp"] > 0 and champ2["hp"] > 0 and round_counter <= 30:
            await beat(f"━━━ **Round {round_counter}** ━━━", md=True, delay=0.7)

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

                # Burn / poison etc tick at start of turn
                tick = status_tick_lines(attacker, a_name)
                if tick:
                    for line in tick:
                        await beat(line, md=True, delay=0.75)
                    if attacker["hp"] <= 0:
                        break

                ok, sleep_lines = can_act(attacker)
                if not ok:
                    await beat(f"{STATUS_EMOJI['sleep']} **{a_name}** {sleep_lines[0]}", md=True, delay=0.9)
                else:
                    move = choose_move(a_key)
                    before_hp = defender["hp"]
                    out = do_move(attacker, defender, a_key, d_key, a_lvl, move)

                    # Send each outcome line individually
                    for line in out:
                        await beat(line, md=True, delay=0.75)

                    dealt = max(0, before_hp - defender["hp"])
                    if who == 0:
                        dmg1_total += dealt
                    else:
                        dmg2_total += dealt

                    # HUD after each action (readable, compact)
                    await send_plain(
                        battle_hud(
                            c1_label_plain, max(champ1["hp"], 0), champ1["max_hp"],
                            c2_label_plain, max(champ2["hp"], 0), champ2["max_hp"],
                        )
                    )
                    await asyncio.sleep(0.9)

            if champ1["hp"] > 0 and champ2["hp"] > 0 and random.random() < 0.12:
                await beat("The tension rises…", md=False, delay=0.8)

            round_counter += 1

        # Determine winner
        if champ1["hp"] > 0 and champ2["hp"] <= 0:
            winner, loser = user, opponent
            w_name, l_name = p1_name, p2_name
            w_champ = c1["display"]
        elif champ2["hp"] > 0 and champ1["hp"] <= 0:
            winner, loser = opponent, user
            w_name, l_name = p2_name, p1_name
            w_champ = c2["display"]
        else:
            # Timeout: higher total damage wins
            if dmg1_total >= dmg2_total:
                winner, loser = user, opponent
                w_name, l_name = p1_name, p2_name
                w_champ = c1["display"]
            else:
                winner, loser = opponent, user
                w_name, l_name = p2_name, p1_name
                w_champ = c2["display"]

        await beat("The dust settles…", md=False, delay=0.9)
        await beat(f"🏆 **Winner: {w_name}** with **{w_champ}**!", md=True, delay=0.9)

        # XP + Leveling (keep existing helper logic)
        xp_w, xp_l = award_battle_xp(winner, loser)
        await beat(f"🎁 XP: **{xp_w}** (Winner) / **{xp_l}** (Loser)", md=True, delay=0.8)

        # Persist HP
        set_current_hp(user, int(max(champ1["hp"], 0)))
        set_current_hp(opponent, int(max(champ2["hp"], 0)))
        save_players()

        max1_after = int(get_stats(c1_key, int(players[user].get("level", 1)))["hp"])
        max2_after = int(get_stats(c2_key, int(players[opponent].get("level", 1)))["hp"])

        await beat("📌 **Persistent HP saved**", md=True, delay=0.4)
        await beat(f"❤️ {c1['display']}: **{max(champ1['hp'],0)}/{max1_after}**", md=True, delay=0.4)
        await beat(f"💙 {c2['display']}: **{max(champ2['hp'],0)}/{max2_after}**", md=True, delay=0.6)

        # Level up announcements (if any)
        lvlups = []
        if players[user].get("just_leveled"):
            lvlups.append((p1_name, players[user]["level"]))
            players[user]["just_leveled"] = False
        if players[opponent].get("just_leveled"):
            lvlups.append((p2_name, players[opponent]["level"]))
            players[opponent]["just_leveled"] = False
        if lvlups:
            await beat("📣 **Level Up!**", md=True, delay=0.5)
            for n, lv in lvlups:
                await beat(f"⭐ **{n}** is now **Lv.{lv}**!", md=True, delay=0.6)

        save_players()

    finally:
        ACTIVE_BATTLES.discard(chat_id)

# =========================
# MAIN
# =========================

def main():
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
    app.run_polling()


if __name__ == "__main__":
    main()