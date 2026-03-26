# FINAL WORKING SUIMON BOT

import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "players.json"

CHAMPS = ["basaurimon", "suimander", "suiqrtle"]

def load_players():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_players(players):
    with open(DATA_FILE, "w") as f:
        json.dump(players, f, indent=2)

players = load_players()

def main_menu(user_id):
    p = players[user_id]
    name = p.get("champ_nickname") or "NoName"
    username = p.get("name")

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👤 {username} | {name}", callback_data="noop")],
        [InlineKeyboardButton("📜 Champs", callback_data="champs"),
         InlineKeyboardButton("⚔️ Fight", callback_data="fight")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    if uid not in players:
        players[uid] = {
            "name": update.effective_user.first_name,
            "champ": None,
            "champ_nickname": None,
            "xp": 0,
            "level": 1
        }
        save_players(players)

    await update.message.reply_text(
        "🔥 Welcome to Suimon Arena\n\n"
        "1️⃣ Menu → Champs\n"
        "2️⃣ /name YourName\n"
        "3️⃣ Reply with /fight",
        reply_markup=main_menu(uid)
    )

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    if not players[uid]["champ"]:
        return await update.message.reply_text("Pick champ first.")

    if not context.args:
        return await update.message.reply_text("Use /name YourName")

    players[uid]["champ_nickname"] = " ".join(context.args)
    save_players(players)

    await update.message.reply_text("✅ Name set.")

async def champs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(c, callback_data=f"pick|{c}")] for c in CHAMPS]
    await update.message.reply_text("Choose:", reply_markup=InlineKeyboardMarkup(kb))

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = str(q.from_user.id)

    if q.data.startswith("pick|"):
        champ = q.data.split("|")[1]

        if players[uid]["champ"]:
            return await q.edit_message_text("Already chosen.")

        players[uid]["champ"] = champ
        save_players(players)

        await q.edit_message_text(f"{champ} selected. Now /name")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_players = sorted(players.items(), key=lambda x: x[1]["xp"], reverse=True)

    text = "🏆 Leaderboard\n\n"
    for i, (uid, p) in enumerate(sorted_players[:10], 1):
        name = p.get("champ_nickname") or "NoName"
        text += f"{i}. {name} | XP {p['xp']}\n"

    await update.message.reply_text(text)

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("name", name))
app.add_handler(CommandHandler("rename", name))
app.add_handler(CommandHandler("menu", champs))
app.add_handler(CommandHandler("leaderboard", leaderboard))
app.add_handler(CallbackQueryHandler(callback))

app.run_polling()
