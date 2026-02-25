import random
import json
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "YOUR_BOT_TOKEN"
DATA_FILE = "players.json"

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

ELEMENTS = {
    "fire":  {"strong": "earth", "weak": "water", "hp": 100, "atk": 22, "spd": 12},
    "water": {"strong": "fire",  "weak": "earth", "hp": 100, "atk": 20, "spd": 10},
    "earth": {"strong": "water", "weak": "fire",  "hp": 110, "atk": 18, "spd": 8},
}

EFFECT_EMOJI = {
    "strong": "💥",
    "weak": "🫧",
    "neutral": "⚔️",
}

# -------------------------

def display_name(player_id: str, fallback: str = "Player"):
    """Best-effort name for nicer battle text."""
    p = players.get(player_id, {})
    return p.get("name") or fallback

def hp_bar(current: int, max_hp: int, length: int = 12) -> str:
    current = max(0, min(current, max_hp))
    filled = int(round((current / max_hp) * length)) if max_hp else 0
    return "█" * filled + "░" * (length - filled)

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

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

# -------------------------

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
        "wins": 0
    }

    save_players(players)

    await update.message.reply_text(
        f"✅ You permanently chose {element.upper()} Suimon!\n"
        "Your destiny is locked 🔒"
    )

# -------------------------

def calculate_attack(attacker_element: str, defender_element: str, defender_spd: int):
    """
    Returns a dict with:
      dmg, crit(bool), dodged(bool), multiplier, effectiveness_label
    """
    # Dodge chance based on defender speed (capped)
    dodge_chance = clamp(defender_spd / 120, 0.03, 0.22)
    if random.random() < dodge_chance:
        return {"dmg": 0, "crit": False, "dodged": True, "multiplier": 0.0, "effect": "neutral"}

    # Base damage influenced slightly by attacker stats
    base = random.randint(14, 26)

    # Elemental effectiveness
    mult = 1.0
    effect = "neutral"
    if ELEMENTS[attacker_element]["strong"] == defender_element:
        mult = 1.5
        effect = "strong"
    elif ELEMENTS[attacker_element]["weak"] == defender_element:
        mult = 0.6
        effect = "weak"

    # Crit chance
    crit = random.random() < 0.12
    if crit:
        mult *= 1.8

    dmg = int(round(base * mult))
    return {"dmg": dmg, "crit": crit, "dodged": False, "multiplier": mult, "effect": effect}

def pick_first_attacker(p1_elem: str, p2_elem: str):
    """Speed decides who starts; small randomness to avoid always same."""
    spd1 = ELEMENTS[p1_elem]["spd"]
    spd2 = ELEMENTS[p2_elem]["spd"]
    roll1 = spd1 + random.randint(0, 6)
    roll2 = spd2 + random.randint(0, 6)
    return 0 if roll1 >= roll2 else 1

def action_line(attacker_name: str, attack: dict):
    if attack["dodged"]:
        return f"💨 {attacker_name} strikes… but the attack is dodged!"
    emoji = EFFECT_EMOJI.get(attack["effect"], "⚔️")
    crit_txt = " ✨CRIT!✨" if attack["crit"] else ""
    eff_txt = " (super effective!)" if attack["effect"] == "strong" else (" (not very effective…)" if attack["effect"] == "weak" else "")
    return f"{emoji} {attacker_name} hits for **{attack['dmg']}** damage{crit_txt}{eff_txt}"

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

    max_hp1 = ELEMENTS[p1_elem]["hp"]
    max_hp2 = ELEMENTS[p2_elem]["hp"]
    hp1 = max_hp1
    hp2 = max_hp2

    # Start message (we'll edit it to build suspense)
    lines = []
    lines.append("⚔️ **BATTLE START** ⚔️")
    lines.append(f"**{p1_name}** ({p1_elem.upper()}) vs **{p2_name}** ({p2_elem.upper()})")
    lines.append("")
    lines.append("🌩️ The arena goes silent…")
    msg = await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    await asyncio.sleep(1.1)

    # Who attacks first?
    first = pick_first_attacker(p1_elem, p2_elem)
    if first == 0:
        lines.append(f"🏁 **{p1_name}** makes the first move!")
    else:
        lines.append(f"🏁 **{p2_name}** makes the first move!")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    await asyncio.sleep(1.0)

    round_counter = 1
    # Safety max rounds
    while hp1 > 0 and hp2 > 0 and round_counter <= 25:
        lines.append("")
        lines.append(f"━━━ **Round {round_counter}** ━━━")

        turn_order = [0, 1] if first == 0 else [1, 0]

        for who in turn_order:
            if hp1 <= 0 or hp2 <= 0:
                break

            if who == 0:
                atk = calculate_attack(p1_elem, p2_elem, ELEMENTS[p2_elem]["spd"])
                lines.append(action_line(p1_name, atk))
                hp2 -= atk["dmg"]
            else:
                atk = calculate_attack(p2_elem, p1_elem, ELEMENTS[p1_elem]["spd"])
                lines.append(action_line(p2_name, atk))
                hp1 -= atk["dmg"]

            # HP display after each action
            hp1_disp = f"{hp_bar(hp1, max_hp1)} {max(hp1,0)}/{max_hp1}"
            hp2_disp = f"{hp_bar(hp2, max_hp2)} {max(hp2,0)}/{max_hp2}"
            lines.append(f"❤️ **{p1_name}:** {hp1_disp}")
            lines.append(f"💙 **{p2_name}:** {hp2_disp}")

            await msg.edit_text("\n".join(lines[-45:]), parse_mode="Markdown")
            await asyncio.sleep(1.0)

        # Next round: slight chance initiative flips to keep it dynamic
        if random.random() < 0.12:
            first = 1 - first
            lines.append("🔄 Momentum shifts!")
            await msg.edit_text("\n".join(lines[-45:]), parse_mode="Markdown")
            await asyncio.sleep(0.9)

        round_counter += 1

    # Decide winner
    if hp1 > 0 and hp2 <= 0:
        winner = user
        loser = opponent
    elif hp2 > 0 and hp1 <= 0:
        winner = opponent
        loser = user
    else:
        # Rare draw by round cap — decide by remaining HP
        winner = user if hp1 >= hp2 else opponent
        loser = opponent if winner == user else user

    players[winner]["wins"] = players[winner].get("wins", 0) + 1
    save_players(players)

    win_name = display_name(winner, "Winner")
    win_elem = players[winner]["element"].upper()

    lines.append("")
    lines.append("🏟️ The dust settles…")
    lines.append(f"🏆 **Winner: {win_name} — {win_elem} Suimon!**")
    lines.append(f"📈 Total wins: **{players[winner]['wins']}**")
    await msg.edit_text("\n".join(lines[-60:]), parse_mode="Markdown")

# -------------------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("choose", choose))
app.add_handler(CommandHandler("fight", fight))

app.run_polling()
