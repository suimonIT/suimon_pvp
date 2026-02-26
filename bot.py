import random
import json
import os
import asyncio
from typing import Dict, Tuple, List

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8429890592:AAHkdeR_2pGp4EOVTT-lBrYAlBlRjK2tW7Y"
DATA_FILE = "players.json"

# -------------------------
# Pacing / Animation
# -------------------------
# Make fights clearly readable (slower = more dramatic)
INTRO_DELAY = 2.2
COUNTDOWN_STEP_DELAY = 1.2
ACTION_DELAY = 2.4
ROUND_BREAK_DELAY = 1.8
MOMENTUM_DELAY = 1.6
LEVELUP_DELAY = 1.8

# Keep Telegram message length manageable
MAX_LINES_SHOWN = 55

# -------------------------
# Load / Save
# -------------------------

def load_players():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_players(players):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

players = load_players()

# -------------------------
# Elements + Base Stats
# -------------------------

ELEMENTS = {
    "fire":  {"strong": "earth", "weak": "water", "hp": 100, "atk": 22, "spd": 12},
    "water": {"strong": "fire",  "weak": "earth", "hp": 100, "atk": 20, "spd": 10},
    "earth": {"strong": "water", "weak": "fire",  "hp": 110, "atk": 18, "spd": 8},
}

EFFECT_EMOJI = {"strong": "💥", "weak": "🫧", "neutral": "⚔️"}

ATTACK_TEXTS = {
    "fire": [
        "casts **Flame Burst**",
        "unleashes **Inferno Slash**",
        "fires a **Cinder Shot**",
        "summons **Ember Wave**",
    ],
    "water": [
        "whips out **Tidal Whip**",
        "launches **Aqua Jet**",
        "calls **Riptide Crash**",
        "casts **Bubble Barrage**",
    ],
    "earth": [
        "slams with **Stone Smash**",
        "raises **Vine Snare**",
        "hurls a **Boulder Breaker**",
        "casts **Quake Pulse**",
    ],
}

# -------------------------
# Helpers
# -------------------------

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def display_name(player_id: str, fallback: str = "Player"):
    p = players.get(player_id, {})
    return p.get("name") or fallback

def hp_bar(current: int, max_hp: int, length: int = 12) -> str:
    current = max(0, min(current, max_hp))
    filled = int(round((current / max_hp) * length)) if max_hp else 0
    return "█" * filled + "░" * (length - filled)

def xp_needed(level: int) -> int:
    # Smooth scaling (fast early, slower later)
    # L1->2: 60, then grows
    return int(60 + (level - 1) * 35 + (level - 1) ** 2 * 6)

def get_stats(element: str, level: int) -> Dict[str, int]:
    """
    Stats scale with level.
    - HP grows more
    - ATK grows medium
    - SPD grows slowly
    """
    base = ELEMENTS[element]
    hp = base["hp"] + (level - 1) * 9
    atk = base["atk"] + (level - 1) * 2
    spd = base["spd"] + (level - 1) // 2
    return {"hp": hp, "atk": atk, "spd": spd}

def element_effect(attacker_element: str, defender_element: str) -> Tuple[float, str]:
    if ELEMENTS[attacker_element]["strong"] == defender_element:
        return 1.5, "strong"
    if ELEMENTS[attacker_element]["weak"] == defender_element:
        return 0.65, "weak"
    return 1.0, "neutral"

def pick_first_attacker(p1_spd: int, p2_spd: int) -> int:
    """Speed decides who starts; randomness to avoid always same."""
    roll1 = p1_spd + random.randint(0, 7)
    roll2 = p2_spd + random.randint(0, 7)
    return 0 if roll1 >= roll2 else 1

async def edit_battle(msg, lines: List[str], delay: float = 0.0):
    # show only the last MAX_LINES_SHOWN to avoid hitting message limits
    await msg.edit_text("\n".join(lines[-MAX_LINES_SHOWN:]), parse_mode="Markdown")
    if delay:
        await asyncio.sleep(delay)

async def countdown_animation(msg, lines: List[str]):
    # A simple readable countdown
    for t in ["3️⃣", "2️⃣", "1️⃣", "⚡"]:
        lines.append(f"⏳ {t}")
        await edit_battle(msg, lines, COUNTDOWN_STEP_DELAY)

def attack_phrase(element: str) -> str:
    return random.choice(ATTACK_TEXTS.get(element, ["attacks"]))

def action_line(attacker_name: str, attacker_elem: str, attack: dict) -> str:
    if attack["dodged"]:
        return f"💨 **{attacker_name}** {attack_phrase(attacker_elem)}… but it misses!"
    emoji = EFFECT_EMOJI.get(attack["effect"], "⚔️")
    crit_txt = " ✨**CRIT!**✨" if attack["crit"] else ""
    eff_txt = " — *super effective!*" if attack["effect"] == "strong" else (" — *not very effective…*" if attack["effect"] == "weak" else "")
    return f"{emoji} **{attacker_name}** {attack_phrase(attacker_elem)} and deals **{attack['dmg']}** damage{crit_txt}{eff_txt}"

def calculate_attack(attacker_elem: str, attacker_level: int, defender_elem: str, defender_spd: int) -> Dict:
    """
    Returns: dmg, crit, dodged, effect
    """
    # Dodge chance based on defender speed (capped)
    dodge_chance = clamp(defender_spd / 140, 0.04, 0.24)
    if random.random() < dodge_chance:
        return {"dmg": 0, "crit": False, "dodged": True, "effect": "neutral"}

    a_stats = get_stats(attacker_elem, attacker_level)

    # Base damage: attacker atk + level influence + randomness
    base = random.randint(7, 12) + int(round(a_stats["atk"] * 0.55)) + int(round(attacker_level * 1.4))
    # Small variance
    base = int(round(base * random.uniform(0.9, 1.1)))

    mult, eff = element_effect(attacker_elem, defender_elem)

    # Crit chance slightly scales with level, capped
    crit_chance = clamp(0.10 + attacker_level * 0.004, 0.10, 0.18)
    crit = random.random() < crit_chance
    if crit:
        mult *= 1.75

    dmg = max(1, int(round(base * mult)))
    return {"dmg": dmg, "crit": crit, "dodged": False, "effect": eff}

def grant_xp(player_id: str, amount: int) -> List[str]:
    """
    Adds XP, handles level-ups.
    Returns lines to announce level-ups.
    """
    p = players[player_id]
    p.setdefault("level", 1)
    p.setdefault("xp", 0)

    p["xp"] += int(amount)
    announcements = []

    while p["xp"] >= xp_needed(p["level"]):
        need = xp_needed(p["level"])
        p["xp"] -= need
        p["level"] += 1
        announcements.append(f"🌟 **{display_name(player_id)}** leveled up to **Lv.{p['level']}**!")

    return announcements

# -------------------------
# Commands
# -------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)

    if user in players:
        await update.message.reply_text(
            f"🔥 You already own a {players[user]['element'].upper()} Suimon.\n"
            "You cannot change it."
        )
        return

    await update.message.reply_text(
        "🔥 Welcome to Suimon Arena!\n\n"
        "⚠️ WARNING: Your choice is permanent!\n\n"
        "Choose wisely:\n"
        "/choose fire\n"
        "/choose water\n"
        "/choose earth"
    )

async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)

    if user in players:
        await update.message.reply_text("❌ You already chose your permanent Suimon.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /choose fire | water | earth")
        return

    element = context.args[0].lower()
    if element not in ELEMENTS:
        await update.message.reply_text("Invalid element!")
        return

    players[user] = {
        "name": update.effective_user.first_name or update.effective_user.username or f"User {user}",
        "element": element,
        "level": 1,
        "xp": 0,
        "wins": 0,
        "losses": 0,
    }
    save_players(players)

    await update.message.reply_text(
        f"✅ You permanently chose {element.upper()} Suimon!\n"
        "Your destiny is locked 🔒"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)
    if user not in players:
        await update.message.reply_text("You must choose a Suimon first with /start")
        return

    p = players[user]
    stats = get_stats(p["element"], p.get("level", 1))
    await update.message.reply_text(
        f"👤 **{display_name(user)}**\n"
        f"Element: **{p['element'].upper()}**\n"
        f"Level: **Lv.{p.get('level', 1)}**\n"
        f"XP: **{p.get('xp', 0)}/{xp_needed(p.get('level', 1))}**\n"
        f"Record: 🏆 {p.get('wins', 0)}W / 💀 {p.get('losses', 0)}L\n"
        f"Stats: ❤️ {stats['hp']} | 🗡️ {stats['atk']} | ⚡ {stats['spd']}",
        parse_mode="Markdown"
    )

# -------------------------
# Fight (animated, slower, with XP/level)
# -------------------------

async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)

    if user not in players:
        await update.message.reply_text("You must choose a Suimon first with /start")
        return

    opponents = [p for p in players if p != user]
    if not opponents:
        await update.message.reply_text("No opponents available!")
        return

    opponent = random.choice(opponents)

    p1 = players[user]
    p2 = players[opponent]

    p1_name = display_name(user, "Player A")
    p2_name = display_name(opponent, "Player B")

    p1_elem = p1["element"]
    p2_elem = p2["element"]

    p1_lvl = int(p1.get("level", 1))
    p2_lvl = int(p2.get("level", 1))

    s1 = get_stats(p1_elem, p1_lvl)
    s2 = get_stats(p2_elem, p2_lvl)

    max_hp1, max_hp2 = s1["hp"], s2["hp"]
    hp1, hp2 = max_hp1, max_hp2

    lines: List[str] = []
    lines.append("⚔️ **BATTLE START** ⚔️")
    lines.append(f"**{p1_name}** ({p1_elem.upper()} • Lv.{p1_lvl}) vs **{p2_name}** ({p2_elem.upper()} • Lv.{p2_lvl})")
    lines.append("")
    lines.append("🏟️ The crowd holds its breath…")
    msg = await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    await asyncio.sleep(INTRO_DELAY)

    # Little animation / build-up
    lines.append("🌫️ Dust rises in the arena…")
    await edit_battle(msg, lines, ROUND_BREAK_DELAY)

    await countdown_animation(msg, lines)

    # Initiative
    first = pick_first_attacker(s1["spd"], s2["spd"])
    starter = p1_name if first == 0 else p2_name
    lines.append(f"🏁 **{starter}** makes the first move!")
    await edit_battle(msg, lines, ROUND_BREAK_DELAY)

    round_counter = 1
    dmg1_total = 0
    dmg2_total = 0

    while hp1 > 0 and hp2 > 0 and round_counter <= 30:
        lines.append("")
        lines.append(f"━━━ **Round {round_counter}** ━━━")
        await edit_battle(msg, lines, ROUND_BREAK_DELAY)

        turn_order = [0, 1] if first == 0 else [1, 0]

        for who in turn_order:
            if hp1 <= 0 or hp2 <= 0:
                break

            if who == 0:
                atk = calculate_attack(p1_elem, p1_lvl, p2_elem, s2["spd"])
                lines.append(action_line(p1_name, p1_elem, atk))
                hp2 -= atk["dmg"]
                dmg1_total += atk["dmg"]
            else:
                atk = calculate_attack(p2_elem, p2_lvl, p1_elem, s1["spd"])
                lines.append(action_line(p2_name, p2_elem, atk))
                hp1 -= atk["dmg"]
                dmg2_total += atk["dmg"]

            hp1_disp = f"{hp_bar(hp1, max_hp1)} {max(hp1,0)}/{max_hp1}"
            hp2_disp = f"{hp_bar(hp2, max_hp2)} {max(hp2,0)}/{max_hp2}"
            lines.append(f"❤️ **{p1_name}:** {hp1_disp}")
            lines.append(f"💙 **{p2_name}:** {hp2_disp}")

            await edit_battle(msg, lines, ACTION_DELAY)

        # Momentum shift animation (rare)
        if hp1 > 0 and hp2 > 0 and random.random() < 0.16:
            first = 1 - first
            lines.append("🔄 **Momentum shifts!**")
            lines.append("…someone found an opening.")
            await edit_battle(msg, lines, MOMENTUM_DELAY)

        round_counter += 1

    # Decide winner
    if hp1 > 0 and hp2 <= 0:
        winner, loser = user, opponent
    elif hp2 > 0 and hp1 <= 0:
        winner, loser = opponent, user
    else:
        # Round cap: decide by remaining HP
        winner = user if hp1 >= hp2 else opponent
        loser = opponent if winner == user else user

    # Record
    players[winner]["wins"] = players[winner].get("wins", 0) + 1
    players[loser]["losses"] = players[loser].get("losses", 0) + 1

    # XP: winner gets more; both get something
    # Base by rounds + participation
    base_w = 40 + (round_counter * 3) + int((dmg1_total if winner == user else dmg2_total) * 0.05)
    base_l = 22 + (round_counter * 2) + int((dmg2_total if loser == user else dmg1_total) * 0.04)

    win_levelups = grant_xp(winner, base_w)
    lose_levelups = grant_xp(loser, base_l)

    save_players(players)

    win_name = display_name(winner, "Winner")
    win_elem = players[winner]["element"].upper()

    lines.append("")
    lines.append("🏟️ The dust settles…")
    await edit_battle(msg, lines, ROUND_BREAK_DELAY)

    lines.append(f"🏆 **Winner: {win_name} — {win_elem} Suimon!**")
    lines.append("")
    lines.append(f"🎁 XP gained: **{base_w}** (winner) / **{base_l}** (loser)")
    await edit_battle(msg, lines, ROUND_BREAK_DELAY)

    if win_levelups or lose_levelups:
        lines.append("")
        lines.append("📣 **Level Up!**")
        lines.extend(win_levelups)
        lines.extend(lose_levelups)
        await edit_battle(msg, lines, LEVELUP_DELAY)

    # Show quick post-fight profiles
    w_id, l_id = winner, loser
    w = players[w_id]
    l = players[l_id]
    w_stats = get_stats(w["element"], int(w.get("level", 1)))
    l_stats = get_stats(l["element"], int(l.get("level", 1)))

    lines.append("")
    lines.append(f"📈 **{display_name(w_id)}** — Lv.{w.get('level',1)}  XP {w.get('xp',0)}/{xp_needed(int(w.get('level',1)))}  (🏆 {w.get('wins',0)}W / 💀 {w.get('losses',0)}L)")
    lines.append(f"    Stats: ❤️ {w_stats['hp']} | 🗡️ {w_stats['atk']} | ⚡ {w_stats['spd']}")
    lines.append(f"📉 **{display_name(l_id)}** — Lv.{l.get('level',1)}  XP {l.get('xp',0)}/{xp_needed(int(l.get('level',1)))}  (🏆 {l.get('wins',0)}W / 💀 {l.get('losses',0)}L)")
    lines.append(f"    Stats: ❤️ {l_stats['hp']} | 🗡️ {l_stats['atk']} | ⚡ {l_stats['spd']}")
    await edit_battle(msg, lines, 0)

# -------------------------
# App
# -------------------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("choose", choose))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("fight", fight))

app.run_polling()
