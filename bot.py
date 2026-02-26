import random
import json
import os
import asyncio
from typing import Dict, List, Optional, Tuple

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# CONFIG
# =========================
TOKEN = "YOUR_BOT_TOKEN"
DATA_FILE = "players.json"

# -------------------------
# Text pacing (seconds)
# Make it readable: raise numbers to slow down
# -------------------------
INTRO_DELAY = 3.0
TEASER_DELAY = 2.4
COUNTDOWN_STEP_DELAY = 1.8
ACTION_DELAY = 3.0
ROUND_BREAK_DELAY = 2.2
STATUS_TICK_DELAY = 2.0
LEVELUP_DELAY = 2.2
END_DELAY = 2.0

# Keep Telegram message length manageable (old lines are trimmed)
MAX_LINES_SHOWN = 70

# =========================
# CHAMPS (Suimon Starter Set)
# =========================
# Typing cycle:
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
                    "schlägt with **Vine Whip** zu!",
                    "whips its vines: **Vine Whip**!",
                    "sends out **Vine Whip** ein!",
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
                ],
            },
            {
                "name": "Synthesis",
                "kind": "heal",
                "power": 0,
                "acc": 1.0,
                "heal_pct": 0.22,
                "text": [
                    "nutzt **Synthesis** und sammelt Sonnenenergie!",
                    "sends out **Synthesis** ein — grüne Energie flackert auf!",
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
                    "spuckt Funken: **Ember**!",
                    "sends out **Ember** ein — die Luft knistert!",
                ],
            },
            {
                "name": "Flamethrower",
                "kind": "damage",
                "power": 55,
                "acc": 0.90,
                "text": [
                    "schleudert **Flamethrower** — eine Feuerlanze!",
                    "sends out **Flamethrower** ein!",
                ],
            },
            {
                "name": "Fire Sprint",
                "kind": "buff_spd",
                "power": 0,
                "acc": 1.0,
                "stages": 1,
                "text": [
                    "zündet **Fire Sprint** — schneller als der Blick!",
                    "nutzt **Fire Sprint** und bekommt Tempo!",
                ],
            },
            {
                "name": "Inferno Claw",
                "kind": "damage_highcrit",
                "power": 48,
                "acc": 0.92,
                "crit_bonus": 0.10,
                "text": [
                    "reißt with **Inferno Claw** durch die Verteidigung!",
                    "sends out **Inferno Claw** ein — glühende Krallen!",
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
                    "schießt **Water Gun**!",
                    "sends out **Water Gun** ein — Wasser prasselt!",
                ],
            },
            {
                "name": "Hydro Burst",
                "kind": "damage",
                "power": 60,
                "acc": 0.82,
                "text": [
                    "lädt Druck auf… **Hydro Burst**!",
                    "sends out **Hydro Burst** ein — eine Wasserwucht!",
                ],
            },
            {
                "name": "Shell Wall",
                "kind": "buff_def",
                "power": 0,
                "acc": 1.0,
                "stages": 1,
                "text": [
                    "braces itself: **Shell Wall**!",
                    "nutzt **Shell Wall** — die Verteidigung steigt!",
                ],
            },
            {
                "name": "Healing Spring",
                "kind": "heal",
                "power": 0,
                "acc": 1.0,
                "heal_pct": 0.18,
                "text": [
                    "ruft eine **Healing Spring** — Wasser glitzert beruhigend!",
                    "sends out **Healing Spring** ein und regeneriert!",
                ],
            },
        ],
    },
}

TYPE_EMOJI = {"fire": "🔥", "water": "💧", "nature": "🌿"}
EFFECT_EMOJI = {"strong": "💥", "weak": "🫧", "neutral": "⚔️", "miss": "💨"}
STATUS_EMOJI = {"burn": "🔥", "sleep": "💤"}

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
# HELPERS
# =========================
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def display_name(player_id: str, fallback: str = "Player") -> str:
    p = players.get(player_id, {})
    return p.get("name") or fallback

def hp_bar(current: int, max_hp: int, length: int = 12) -> str:
    current = max(0, min(current, max_hp))
    filled = int(round((current / max_hp) * length)) if max_hp else 0
    return "█" * filled + "░" * (length - filled)

def xp_needed(level: int) -> int:
    # Fast early, slower later
    return int(60 + (level - 1) * 18 + (level ** 2) * 3)

def type_effect(attacker_type: str, defender_type: str) -> Tuple[float, str]:
    # returns (multiplier, effect_key)
    if attacker_type == CHAMPS_BY_TYPE[defender_type]["weak_to"]:
        # defender is weak to attacker
        return 1.5, "strong"
    if attacker_type == CHAMPS_BY_TYPE[defender_type]["strong_against"]:
        # defender resists attacker (attacker is weak to defender)
        return 0.67, "weak"
    return 1.0, "neutral"

def champ_from_key(key: str) -> Dict:
    return CHAMPS[key]

def champ_key_from_input(arg: str) -> Optional[str]:
    if not arg:
        return None
    a = arg.lower().strip()
    # allow short aliases
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
    # simple scaling (balanced)
    # Every level: +6% hp total across levels, +4% atk/def/spd-ish via additive
    hp = int(round(base["hp"] + (level - 1) * 9))
    atk = int(round(base["atk"] + (level - 1) * 2))
    df  = int(round(base["def"] + (level - 1) * 2))
    spd = int(round(base["spd"] + (level - 1) * 1))
    return {"hp": hp, "atk": atk, "def": df, "spd": spd}

async def edit_battle(msg, lines: List[str], delay: float) -> None:
    # trim old lines so Telegram edits stay safe
    if len(lines) > MAX_LINES_SHOWN:
        lines[:] = lines[-MAX_LINES_SHOWN:]
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    await asyncio.sleep(delay)

async def countdown_animation(msg, lines: List[str]) -> None:
    for t in ["3", "2", "1", "⚡"]:
        lines.append(f"⏳ {t}…")
        await edit_battle(msg, lines, COUNTDOWN_STEP_DELAY)

def pick_first_attacker(spd1: int, spd2: int) -> int:
    # 0 -> champ1 first, 1 -> champ2 first
    if spd1 == spd2:
        return 0 if random.random() < 0.5 else 1
    # weighted by speed
    p = clamp(0.5 + (spd1 - spd2) / 40.0, 0.25, 0.75)
    return 0 if random.random() < p else 1

def choose_move(champ_key: str, hp: int, max_hp: int) -> Dict:
    champ = champ_from_key(champ_key)
    moves = champ["moves"]

    # light "AI":
    # - If low HP, more likely to heal
    # - Otherwise mostly damage
    heal_moves = [m for m in moves if m["kind"] == "heal"]
    buff_moves = [m for m in moves if m["kind"].startswith("buff_")]
    dmg_moves  = [m for m in moves if m["kind"].startswith("damage") or m["kind"].startswith("status_")]

    if hp <= int(max_hp * 0.38) and heal_moves and random.random() < 0.60:
        return random.choice(heal_moves)
    if buff_moves and random.random() < 0.18:
        return random.choice(buff_moves)
    return random.choice(dmg_moves)

def calc_damage(attacker_stats: Dict[str,int], defender_stats: Dict[str,int], level: int,
                power: int, type_mult: float, crit_mult: float, def_stage: int) -> int:
    # Defense stage reduces damage (each stage ~ 12%)
    def_mult = 1.0 + (0.12 * max(0, def_stage))
    effective_def = max(1, int(round(defender_stats["def"] * def_mult)))

    # Pokémon-ish feel (simple):
    # base = ( (2*L/5 + 2) * Power * ATK / DEF ) / 6 + 2
    base = ((2 * level / 5) + 2) * power * attacker_stats["atk"] / effective_def
    base = (base / 6) + 2

    # small randomness
    base *= random.uniform(0.92, 1.08)
    dmg = int(round(base * type_mult * crit_mult))
    return max(1, dmg)

def try_apply_burn() -> bool:
    return True

# Build type lookup helper (so we can compute resist/weak easily)
CHAMPS_BY_TYPE = {
    "fire":   {"strong_against": "nature", "weak_to": "water"},
    "water":  {"strong_against": "fire",   "weak_to": "nature"},
    "nature": {"strong_against": "water",  "weak_to": "fire"},
}

def type_mult(attacker_type: str, defender_type: str) -> Tuple[float, str]:
    if CHAMPS_BY_TYPE[attacker_type]["strong_against"] == defender_type:
        return 1.5, "strong"
    if CHAMPS_BY_TYPE[attacker_type]["weak_to"] == defender_type:
        return 0.67, "weak"
    return 1.0, "neutral"

def attack_prefix(champ_key: str) -> str:
    c = champ_from_key(champ_key)
    return TYPE_EMOJI[c["type"]]

def grant_xp(player_id: str, gained: int) -> List[str]:
    p = players[player_id]
    p["xp"] = int(p.get("xp", 0)) + int(gained)
    levelups: List[str] = []
    while p["xp"] >= xp_needed(int(p.get("level", 1))):
        need = xp_needed(int(p.get("level", 1)))
        p["xp"] -= need
        p["level"] = int(p.get("level", 1)) + 1
        levelups.append(f"✨ **{display_name(player_id)}** reached **Lv.{p['level']}**!")
    return levelups

# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)

    if user in players:
        champ_key = players[user].get("champ")
        if champ_key in CHAMPS:
            champ = champ_from_key(champ_key)
            await update.message.reply_text(
                f"✅ You already chose **{champ['display']}** ({TYPE_EMOJI[champ['type']]} {champ['type'].upper()}).\n"
                f"Use /profile or /fight.",
                parse_mode="Markdown"
            )
            return

    await update.message.reply_text(
        "🔥 **Welcome to Suimon Arena!**\n\n"
        "⚠️ Your choice is **permanent**!\n\n"
        "Choose your champ:\n"
        "/choose basaurimon\n"
        "/choose suimander\n"
        "/choose suiqrtle\n\n"
        "Tip: /champs shows info.",
        parse_mode="Markdown"
    )

async def champs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["📜 **Starter Champs**", ""]
    for k, c in CHAMPS.items():
        t = c["type"]
        lines.append(f"{TYPE_EMOJI[t]} **{c['display']}** — Type: **{t.upper()}**")
        lines.append(f"   Strong vs: **{CHAMPS_BY_TYPE[t]['strong_against'].upper()}** | Weak vs: **{CHAMPS_BY_TYPE[t]['weak_to'].upper()}**")
    lines.append("")
    lines.append("Choose: /choose basaurimon | suimander | suiqrtle")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)

    if user in players and players[user].get("champ") in CHAMPS:
        await update.message.reply_text("❌ You already picked a permanent champ.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /choose basaurimon | suimander | suiqrtle")
        return

    champ_key = champ_key_from_input(context.args[0])
    if champ_key not in CHAMPS:
        await update.message.reply_text("Invalid! Use: /choose basaurimon | suimander | suiqrtle")
        return

    players[user] = {
        "name": update.effective_user.first_name or update.effective_user.username or f"User {user}",
        "champ": champ_key,
        "level": 1,
        "xp": 0,
        "wins": 0,
        "losses": 0,
    }
    save_players(players)

    champ = champ_from_key(champ_key)
    await update.message.reply_text(
        f"✅ You chose **{champ['display']}**! {TYPE_EMOJI[champ['type']]}\n"
        "Your fate is sealed 🔒",
        parse_mode="Markdown"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)
    if user not in players or players[user].get("champ") not in CHAMPS:
        await update.message.reply_text("You must choose a champ first: /start")
        return

    p = players[user]
    champ = champ_from_key(p["champ"])
    lvl = int(p.get("level", 1))
    stats = get_stats(p["champ"], lvl)
    need = xp_needed(lvl)

    moves = champ["moves"]
    move_lines = []
    for m in moves:
        move_lines.append(f"• **{m['name']}**")

    await update.message.reply_text(
        f"👤 **{display_name(user)}**\n"
        f"Champ: **{champ['display']}** {TYPE_EMOJI[champ['type']]}\n"
        f"Level: **{lvl}** | XP: **{p.get('xp',0)}/{need}**\n"
        f"W/L: **{p.get('wins',0)}**/**{p.get('losses',0)}**\n\n"
        f"❤️ HP: **{stats['hp']}**\n"
        f"🗡 ATK: **{stats['atk']}**  🛡 DEF: **{stats['def']}**  🥾 SPD: **{stats['spd']}**\n\n"
        f"🎯 Moves:\n" + "\n".join(move_lines),
        parse_mode="Markdown"
    )

# =========================
# BATTLE SYSTEM
# =========================
def status_tick_lines(state: Dict, champ_name: str) -> List[str]:
    lines: List[str] = []
    # Burn tick
    if state.get("burn_turns", 0) > 0:
        state["burn_turns"] -= 1
        dmg = int(round(state["max_hp"] * 0.06))
        state["hp"] -= dmg
        lines.append(f"{STATUS_EMOJI['burn']} **{champ_name}** is burning! −**{dmg}** HP.")
        if state["burn_turns"] == 0:
            lines.append(f"{STATUS_EMOJI['burn']} The flames on **{champ_name}** go out.")
    return lines

def can_act(state: Dict) -> Tuple[bool, List[str]]:
    if state.get("sleep_turns", 0) > 0:
        state["sleep_turns"] -= 1
        if state["sleep_turns"] > 0:
            return False, [f"{STATUS_EMOJI['sleep']} …**is asleep** weiter und kann nicht angreifen!"]
        return False, [f"{STATUS_EMOJI['sleep']} wakes up groggy and misses the turn!"]
    return True, []

def crit_multiplier(base_chance: float) -> Tuple[float, bool]:
    crit = random.random() < base_chance
    return (1.75 if crit else 1.0), crit

def format_effect(effect_key: str) -> str:
    if effect_key == "strong":
        return " — **SUPER effective!**"
    if effect_key == "weak":
        return " — not very effective…"
    return ""

def do_move(attacker: Dict, defender: Dict, attacker_key: str, defender_key: str,
            attacker_level: int, move: Dict) -> List[str]:
    out: List[str] = []
    a_champ = champ_from_key(attacker_key)
    d_champ = champ_from_key(defender_key)

    a_name = a_champ["display"]
    d_name = d_champ["display"]

    # Accuracy check
    if random.random() > float(move.get("acc", 1.0)):
        out.append(f"{EFFECT_EMOJI['miss']} **{a_name}** tries **{move['name']}**… but misses!")
        return out

    # Flavor text
    out.append(f"{attack_prefix(attacker_key)} **{a_name}** {random.choice(move['text'])}")

    kind = move["kind"]

    # Heal
    if kind == "heal":
        heal = int(round(attacker["max_hp"] * float(move.get("heal_pct", 0.2))))
        attacker["hp"] = min(attacker["max_hp"], attacker["hp"] + heal)
        out.append(f"✨ **{a_name}** heals **+{heal}** HP.")
        return out

    # Buffs
    if kind == "buff_spd":
        attacker["spd_stage"] = int(clamp(attacker.get("spd_stage", 0) + int(move.get("stages", 1)), 0, 3))
        out.append(f"🥾 Speed rises! (Stufe {attacker['spd_stage']})")
        return out

    if kind == "buff_def":
        attacker["def_stage"] = int(clamp(attacker.get("def_stage", 0) + int(move.get("stages", 1)), 0, 3))
        out.append(f"🛡 Defense rises! (Stufe {attacker['def_stage']})")
        return out

    # Sleep status
    if kind == "status_sleep":
        # small chance to resist if defender is faster
        resist = clamp((defender["spd"] - attacker["spd"]) / 50.0, 0.0, 0.22)
        if random.random() < resist:
            out.append(f"💨 **{d_name}** shakes off the spores!")
            return out
        turns = move.get("sleep_turns", (1, 2))
        defender["sleep_turns"] = random.randint(int(turns[0]), int(turns[1]))
        out.append(f"{STATUS_EMOJI['sleep']} **{d_name}** is asleep ein! ({defender['sleep_turns']} turn(s))")
        return out

    # Damage kinds
    power = int(move.get("power", 40))
    a_type = a_champ["type"]
    d_type = d_champ["type"]
    mult, eff = type_mult(a_type, d_type)

    base_crit = 0.10 + attacker_level * 0.004
    base_crit = clamp(base_crit, 0.10, 0.18)
    if kind == "damage_highcrit":
        base_crit = clamp(base_crit + float(move.get("crit_bonus", 0.08)), 0.10, 0.28)

    crit_mult, crit = crit_multiplier(base_crit)

    dmg = calc_damage(
        attacker_stats={"atk": attacker["atk"]},
        defender_stats={"def": defender["def"]},
        level=attacker_level,
        power=power,
        type_mult=mult,
        crit_mult=crit_mult,
        def_stage=defender.get("def_stage", 0),
    )
    defender["hp"] -= dmg

    crit_txt = " **CRIT!**" if crit else ""
    out.append(f"💢 Treffer: **{dmg}** Schaden{crit_txt}{format_effect(eff)}")

    # Burn application
    if kind == "damage_burn":
        if defender.get("burn_turns", 0) == 0 and random.random() < float(move.get("burn_chance", 0.25)):
            defender["burn_turns"] = 3
            out.append(f"{STATUS_EMOJI['burn']} **{d_name}** was burned! (3 turns)")

    return out

async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)

    if user not in players or players[user].get("champ") not in CHAMPS:
        await update.message.reply_text("You must choose a champ first: /start")
        return

    opponents = [p for p in players if p != user and players[p].get("champ") in CHAMPS]
    if not opponents:
        await update.message.reply_text("No opponents available!")
        return

    opponent = random.choice(opponents)

    # Player champs
    p1 = players[user]
    p2 = players[opponent]

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

    champ1 = {
        "hp": s1["hp"], "max_hp": s1["hp"],
        "atk": s1["atk"], "def": s1["def"], "spd": s1["spd"],
        "def_stage": 0, "spd_stage": 0,
        "burn_turns": 0, "sleep_turns": 0,
    }
    champ2 = {
        "hp": s2["hp"], "max_hp": s2["hp"],
        "atk": s2["atk"], "def": s2["def"], "spd": s2["spd"],
        "def_stage": 0, "spd_stage": 0,
        "burn_turns": 0, "sleep_turns": 0,
    }

    lines: List[str] = []
    lines.append("⚔️ **BATTLE START** ⚔️")
    lines.append(f"👤 **{p1_name}** sends out **{c1['display']}** ein!  (Lv.{lv1})")
    lines.append(f"👤 **{p2_name}** sends out **{c2['display']}** ein!  (Lv.{lv2})")
    lines.append("")
    lines.append("🏟️ The crowd falls silent…")
    msg = await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    await asyncio.sleep(INTRO_DELAY)

    # teaser animation
    lines.append("🌫️ Dust swirls. Footsteps echo.")
    await edit_battle(msg, lines, TEASER_DELAY)
    lines.append("🎥 The camera zooms in…")
    await edit_battle(msg, lines, TEASER_DELAY)

    await countdown_animation(msg, lines)

    # Initiative (speed + stage)
    spd1 = champ1["spd"] * (1.0 + 0.15 * champ1["spd_stage"])
    spd2 = champ2["spd"] * (1.0 + 0.15 * champ2["spd_stage"])
    first = pick_first_attacker(int(spd1), int(spd2))
    starter_name = c1["display"] if first == 0 else c2["display"]
    lines.append(f"🏁 **{starter_name}**** takes the first move!")
    await edit_battle(msg, lines, ROUND_BREAK_DELAY)

    round_counter = 1
    dmg1_total = 0
    dmg2_total = 0

    while champ1["hp"] > 0 and champ2["hp"] > 0 and round_counter <= 30:
        lines.append("")
        lines.append(f"━━━ **Round {round_counter}** ━━━")
        await edit_battle(msg, lines, ROUND_BREAK_DELAY)

        turn_order = [0, 1] if first == 0 else [1, 0]

        for who in turn_order:
            if champ1["hp"] <= 0 or champ2["hp"] <= 0:
                break

            attacker = champ1 if who == 0 else champ2
            defender = champ2 if who == 0 else champ1
            a_key = c1_key if who == 0 else c2_key
            d_key = c2_key if who == 0 else c1_key
            a_lvl = lv1 if who == 0 else lv2

            # Status ticks at start of acting
            a_name = champ_from_key(a_key)["display"]
            tick = status_tick_lines(attacker, a_name)
            if tick:
                lines.extend(tick)
                await edit_battle(msg, lines, STATUS_TICK_DELAY)
                if attacker["hp"] <= 0:
                    break

            # Sleep check
            ok, sleep_lines = can_act(attacker)
            if not ok:
                lines.extend(sleep_lines)
                await edit_battle(msg, lines, ACTION_DELAY)
            else:
                move = choose_move(a_key, attacker["hp"], attacker["max_hp"])
                before_hp = defender["hp"]
                out = do_move(attacker, defender, a_key, d_key, a_lvl, move)
                lines.extend(out)

                # Track damage totals for XP calculation
                dealt = max(0, before_hp - defender["hp"])
                if who == 0:
                    dmg1_total += dealt
                else:
                    dmg2_total += dealt

                # Show HP bars
                h1 = f"{hp_bar(champ1['hp'], champ1['max_hp'])} {max(champ1['hp'],0)}/{champ1['max_hp']}"
                h2 = f"{hp_bar(champ2['hp'], champ2['max_hp'])} {max(champ2['hp'],0)}/{champ2['max_hp']}"
                lines.append(f"❤️ **{c1['display']}:** {h1}")
                lines.append(f"💙 **{c2['display']}:** {h2}")

                await edit_battle(msg, lines, ACTION_DELAY)

        # Small chance momentum shifts (purely flavor)
        if champ1["hp"] > 0 and champ2["hp"] > 0 and random.random() < 0.14:
            first = 1 - first
            lines.append("🔄 **Momentum Shift!** One mistake… one opening…")
            await edit_battle(msg, lines, ROUND_BREAK_DELAY)

        round_counter += 1

    # Winner
    if champ1["hp"] > 0 and champ2["hp"] <= 0:
        winner, loser = user, opponent
    elif champ2["hp"] > 0 and champ1["hp"] <= 0:
        winner, loser = opponent, user
    else:
        winner = user if champ1["hp"] >= champ2["hp"] else opponent
        loser = opponent if winner == user else user

    # Record W/L
    players[winner]["wins"] = players[winner].get("wins", 0) + 1
    players[loser]["losses"] = players[loser].get("losses", 0) + 1

    # XP (both get some, winner more)
    base_rounds = max(1, round_counter - 1)
    w_dmg = dmg1_total if winner == user else dmg2_total
    l_dmg = dmg2_total if loser == user else dmg1_total

    xp_w = int(50 + base_rounds * 4 + w_dmg * 0.06)
    xp_l = int(28 + base_rounds * 3 + l_dmg * 0.05)

    win_levelups = grant_xp(winner, xp_w)
    lose_levelups = grant_xp(loser, xp_l)

    save_players(players)

    lines.append("")
    lines.append("🏟️ The dust settles…")
    await edit_battle(msg, lines, END_DELAY)

    w_name = display_name(winner, "Winner")
    w_champ = champ_from_key(players[winner]["champ"])["display"]
    lines.append(f"🏆 **Winner: {w_name}** with **{w_champ}**!")
    lines.append(f"🎁 XP: **{xp_w}** (Winner) / **{xp_l}** (Loser)")
    await edit_battle(msg, lines, END_DELAY)

    if win_levelups or lose_levelups:
        lines.append("")
        lines.append("📣 **Level Up!**")
        lines.extend(win_levelups)
        lines.extend(lose_levelups)
        await edit_battle(msg, lines, LEVELUP_DELAY)

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("champs", champs_cmd))
    app.add_handler(CommandHandler("choose", choose))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("fight", fight))

    print("Suimon bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()