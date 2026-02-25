import random
import json
import os
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
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_players(players):
    with open(DATA_FILE, "w") as f:
        json.dump(players, f)

players = load_players()

# -------------------------

ELEMENTS = {
    "fire": {"strong": "earth", "weak": "water", "hp": 100, "atk": 22, "spd": 12},
    "water": {"strong": "fire", "weak": "earth", "hp": 100, "atk": 20, "spd": 10},
    "earth": {"strong": "water", "weak": "fire", "hp": 110, "atk": 18, "spd": 8},
}

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

    hp1 = ELEMENTS[p1["element"]]["hp"]
    hp2 = ELEMENTS[p2["element"]]["hp"]

    log = "⚔️ BATTLE START ⚔️\n\n"
    log += f"{p1['element'].upper()} vs {p2['element'].upper()}\n\n"

    round_counter = 1

    while hp1 > 0 and hp2 > 0:

        log += f"--- Round {round_counter} ---\n"

        # Player 1 attacks
        dmg1 = calculate_damage(p1["element"], p2["element"])
        hp2 -= dmg1
        log += f"Player A deals {dmg1} damage!\n"

        if hp2 <= 0:
            break

        # Player 2 attacks
        dmg2 = calculate_damage(p2["element"], p1["element"])
        hp1 -= dmg2
        log += f"Player B deals {dmg2} damage!\n"

        log += f"HP A: {max(hp1,0)} | HP B: {max(hp2,0)}\n\n"
        round_counter += 1

    if hp1 > 0:
        winner = user
        players[user]["wins"] += 1
    else:
        winner = opponent
        players[opponent]["wins"] += 1

    save_players(players)

    log += f"\n🏆 Winner: {players[winner]['element'].upper()} Suimon!"

    await update.message.reply_text(log)

# -------------------------

def calculate_damage(attacker, defender):
    base = random.randint(15, 30)

    if ELEMENTS[attacker]["strong"] == defender:
        base *= 1.5
    elif ELEMENTS[attacker]["weak"] == defender:
        base *= 0.5

    if random.random() < 0.1:
        base *= 2  # Crit

    return int(base)

# -------------------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("choose", choose))
app.add_handler(CommandHandler("fight", fight))

app.run_polling()