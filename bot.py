import random, json, os, asyncio, html, time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)

TOKEN = "8429890592:AAHkdeR_2pGp4EOVTT-lBrYAlBlRjK2tW7Y"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "players.json")
ALLOWED_GROUP_IDS = {-1002664937769, -1003839722848, -1003407035529}
PRIVILEGED_USER_IDS = {1638084297, 7105730933, 6274470012}
MENU_IMAGE_CANDIDATES = ("logo.JPG", "logo.jpg", "logo.png", "menu.jpg", "menu.png")
RANKINGS_IMAGE_CANDIDATES = ("rankings.jpg", "rankings.JPG", "rankings.png")
EXPLORE_IMAGE_CANDIDATES = ("explore.png", "explore.jpg", "explore.JPG")

PENDING_CHALLENGES = {}
CHALLENGE_TIMEOUT = 60
ACTIVE_BATTLES = set()
BATTLES = {}
PENDING_SELECTION = {}

INTRO_DELAY = 0.8
REPOSITION_COOLDOWN = 3.5
AFK_TIMEOUT = 180
COUNTDOWN_STEP_DELAY = 0.55
ACTION_DELAY = 0.70
HUD_DELAY = 0.45
END_DELAY = 0.8
MAX_LINES_SHOWN = 25
MAX_MESSAGE_CHARS = 3800

DAILY_SUIBALLS = 2
DAILY_SUIBALLS_TOURNAMENT = 10
SUIBALL_CAP = 5
SUIBALL_CAP_TOURNAMENT = 100
MAX_LEVEL = 10
TZ = timezone.utc
DAILY_NETBALLS = 1
NETBALL_CAP = 3

TOURNAMENT_FILE = os.path.join(BASE_DIR, "tournament.json")

def load_tournament():
    if not os.path.exists(TOURNAMENT_FILE): return {"active": False}
    try: return json.load(open(TOURNAMENT_FILE, "r"))
    except: return {"active": False}
def save_tournament(data): json.dump(data, open(TOURNAMENT_FILE, "w"), indent=2)

tournament_state = load_tournament()
def is_tournament_active(): return tournament_state.get("active", False)
def is_xp_boost_active(): return time.time() < tournament_state.get("xp_boost_expires", 0)
def get_xp_boost_multiplier(): return 1.5 if is_xp_boost_active() else 1.0
def get_daily_suiballs(): return DAILY_SUIBALLS_TOURNAMENT if is_tournament_active() else DAILY_SUIBALLS
def get_suiball_cap(): return SUIBALL_CAP_TOURNAMENT if is_tournament_active() else SUIBALL_CAP

CHAMPS = {
    "basaurimon": {"display":"Basaurimon","type":"nature","base":{"hp":160,"atk":24,"def":11,"spd":9},"moves":[
        {"name":"Vine Whip","kind":"damage","power":48,"acc":0.95,"text":["whips out something long and flexible!","snaps its vine like a dominatrix!","lashes harder than a dealer!"]},
        {"name":"Needle Rain","kind":"damage_poison","power":36,"acc":0.92,"poison_chance":0.40,"poison_turns":[2,3],"crit_bonus":0.08,"text":["opens the vial!","launches a volley!","rains down!"]},
        {"name":"Leaf Storm","kind":"damage","power":55,"acc":0.88,"text":["unleashes Leaf Storm!","summons a vortex!","calls down a tempest!"]},
        {"name":"Sleep Spore","kind":"status_sleep","power":0,"acc":0.75,"sleep_turns":[1,2],"text":["pulls out Cannabis indica!","hotboxes the arena!","deploys Sleep Spore!"]}]},
    "suimander": {"display":"Suimander","type":"fire","base":{"hp":154,"atk":23,"def":11,"spd":12},"moves":[
        {"name":"Wet Dream","kind":"status_wet_dream","power":0,"acc":0.90,"wet_dream_turns":[3,4],"text":["slips something into their drink!","whispers in their ear!","exhales cult smoke!"]},
        {"name":"Flamethrower","kind":"damage","power":55,"acc":0.90,"text":["blasts a stream!","turns up the heat!","scorches everything!"]},
        {"name":"Inferno Claw","kind":"damage_highcrit","power":48,"acc":0.92,"crit_bonus":0.10,"text":["scratches marks!","carves deep!","rips through!"]},
        {"name":"Will-O-Wisp","kind":"status_burn","power":0,"acc":0.90,"burn_turns":[2,3],"text":["pulls out a crackpipe!","hotboxes the arena!","lights up a meth pipe!"]}]},
    "suiqrtle": {"display":"Suiqrtle","type":"water","base":{"hp":155,"atk":21,"def":12,"spd":8},"moves":[
        {"name":"Water Pulse","kind":"status_confuse","power":0,"acc":0.80,"confuse_turns":[1,2],"confuse_rare_chance":0.30,"text":["floods with PCP-laced water!","sprays pure PCP!","fires Water Pulse!"]},
        {"name":"Bubble Beam","kind":"damage","power":46,"acc":0.93,"text":["releases warm bubbles!","fires bubbles!","floods the field!"]},
        {"name":"Aqua Tail","kind":"damage","power":52,"acc":0.88,"text":["slaps with a wet tail!","swings something wet!","whips up water!"]},
        {"name":"Hydro Burst","kind":"damage","power":60,"acc":0.82,"text":["builds pressure!","releases fluids!","explodes!"]}]},
    "poolmon": {"display":"Poolmon","type":"water","base":{"hp":148,"atk":20,"def":12,"spd":8},"moves":[
        {"name":"Riptide","kind":"damage","power":60,"acc":0.82,"text":["drags the opponent into a swirling vortex of despair!","unleashes waves that hit like a bad hangover!","the current pulls harder than a debt collector!"]},
        {"name":"Sedated Gaze","kind":"status_confuse","power":0,"acc":0.78,"confuse_turns":[1,1],"text":["locks eyes with the opponent – pupils dilate immediately, and their head goes foggy!","a single glance that hits like a tranquilizer dart to the brain!","stares deep into the enemy's soul, and now they can't remember what they were doing!"]},
        {"name":"Abyssal Slam","kind":"damage_highcrit","power":44,"acc":0.88,"crit_bonus":0.12,"text":["bodychecks like a deep-sea freight train with no lights on!","crashes in from the darkness – you never saw it coming!","hits with the force of a pressure implosion at the bottom of the trench!"]},
        {"name":"Howling Haze","kind":"status_debuff","power":0,"acc":0.92,"atk_debuff_pct":0.30,"debuff_turns":2,"text":["releases a cloud of ketamine-laced mist – the opponent's strength melts away!","a haunting howl echoes through the arena, sapping muscle and will!","the air turns thick with something that burns the throat and weakens the body!"]}]},
    "suideer": {"display":"Suideer","type":"fire","base":{"hp":148,"atk":26,"def":10,"spd":14},"moves":[
        {"name":"Flame Burst","kind":"damage","power":50,"acc":0.92,"text":["erupts in flame!","explodes with heat!","fires a fireball!"]},
        {"name":"Bambi Blaze","kind":"damage","power":65,"acc":0.80,"text":["looks innocent!","the world burns!","sets the forest on fire!"]},
        {"name":"Ember Dash","kind":"damage","power":42,"acc":0.96,"text":["dashes forward!","a quick charge!","speeds through!"]},
        {"name":"Crack Surge","kind":"damage","power":48,"acc":0.88,"spd_boost_chance":0.25,"spd_boost":2,"text":["hits the pipe!","inhales a line!","addict's rush!"]}]},
    "jengacide": {"display":"Jengacide","type":"nature","base":{"hp":170,"atk":22,"def":14,"spd":7},"moves":[
        {"name":"Blunt Force Trauma","kind":"damage","power":52,"acc":0.85,"def_down_chance":0.18,"def_down_turns":2,"text":["slams forward!","clubs the enemy!","delivers a hit!"]},
        {"name":"Ketamine Quake","kind":"damage","power":44,"acc":0.82,"stun_chance":0.35,"stun_turns":1,"text":["stomps the ground!","unleashes a tremor!","wobbles reality!"]},
        {"name":"Molly Pressure","kind":"status_debuff","power":0,"acc":0.90,"def_speed_debuff":True,"debuff_turns":2,"text":["drops a pill!","the love drug hits!","sends waves!"]},
        {"name":"Jenga Joint Collapse","kind":"damage","power":70,"acc":0.75,"high_cooldown":3,"debuff_bonus":True,"text":["lines up the tower!","pulls the block!","ultimate betrayal!"]}]},
}

TYPE_EMOJI = {"fire":"🔥","water":"💧","nature":"🌿"}
STATUS_EMOJI = {"burn":"🔥","sleep":"💤","confuse":"🌀","poison":"☠️","wet_dream":"😨"}
CHAMPS_BY_TYPE = {"fire":{"strong_against":"nature","weak_to":"water"},"water":{"strong_against":"fire","weak_to":"nature"},"nature":{"strong_against":"water","weak_to":"fire"}}

WORLDS = {
    "sedative_abyss":{"name":"Sedative Abyss","emoji":"🌊","type":"water","suimon":["poolmon"],"flavor":"dark ocean trenches","encounter_chance":0.20},
    "crackspit_peaks":{"name":"Crackspit Peaks","emoji":"🔥","type":"fire","suimon":["suideer"],"flavor":"volcanic mountains","encounter_chance":0.20},
    "hash_highlands":{"name":"Hash Highlands","emoji":"🌍","type":"nature","suimon":["jengacide"],"flavor":"rolling hills","encounter_chance":0.20},
}

# ---------- HILFSFUNKTIONEN ----------
def resolve_menu_image_path():
    for n in MENU_IMAGE_CANDIDATES:
        if os.path.isfile(os.path.join(BASE_DIR,n)): return os.path.join(BASE_DIR,n)
    return None
def resolve_heal_image_path():
    for n in ("heal.jpg","heal.JPG","heal.png"):
        if os.path.isfile(os.path.join(BASE_DIR,n)): return os.path.join(BASE_DIR,n)
    return None
def resolve_rankings_image_path():
    for n in RANKINGS_IMAGE_CANDIDATES:
        if os.path.isfile(os.path.join(BASE_DIR,n)): return os.path.join(BASE_DIR,n)
    return None
def resolve_explore_image_path():
    for n in EXPLORE_IMAGE_CANDIDATES:
        if os.path.isfile(os.path.join(BASE_DIR,n)): return os.path.join(BASE_DIR,n)
    return None
def is_allowed_chat_id(cid): return cid in ALLOWED_GROUP_IDS
async def ensure_allowed_chat(update, context=None):
    cid = int(update.effective_chat.id) if update.effective_chat else None
    if is_allowed_chat_id(cid): return True
    msg = "🚫 <b>This bot only works in the official Suimon group.</b>"
    if update.callback_query:
        try: await update.callback_query.answer("This bot only works in the official Suimon group.", show_alert=True)
        except: pass
    elif update.effective_message:
        try: await update.effective_message.reply_text(msg, parse_mode="HTML")
        except: pass
    return False
async def is_privileged_user(bot, chat_id, user_id):
    if user_id in PRIVILEGED_USER_IDS: return True
    try: return (await bot.get_chat_member(chat_id, user_id)).status == ChatMember.OWNER
    except: return False

def _parse_target_from_args(chat_id, args):
    if not args: return None, 1
    first = args[0].strip()
    if not first: return None, 1
    if first.isdigit(): return first, 1
    lookup = first.lstrip('@').lower().replace(' ','')
    for uid, p in players.items():
        if chat_id not in p.get('chats',[]): continue
        if lookup in ((p.get('username','')).lower().lstrip('@'), (p.get('name','')).lower().replace(' ','')):
            return uid, 1
    return None, 1

def _parse_target_and_amount(chat_id, args):
    t, c = _parse_target_from_args(chat_id, args)
    return t, (int(args[c]) if len(args) > c else None)

async def send_menu_photo(msg, cap, markup):
    img = resolve_menu_image_path()
    if img:
        with open(img,"rb") as f: await msg.reply_photo(photo=f, caption=cap, reply_markup=markup, parse_mode="HTML")
    else: await msg.reply_text(cap, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

async def edit_menu_message(query, cap, markup, **kw):
    msg = query.message
    if msg and getattr(msg,"photo",None):
        try: await query.edit_message_caption(caption=cap, reply_markup=markup, parse_mode="HTML"); return
        except BadRequest: pass
    try: await query.edit_message_text(cap, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=kw.get("disable_web_page_preview",True))
    except BadRequest:
        try: await query.message.reply_text(cap, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=kw.get("disable_web_page_preview",True))
        except: pass

def load_players():
    if not os.path.exists(DATA_FILE): return {}
    try: return json.load(open(DATA_FILE,"r",encoding="utf-8"))
    except: return {}
def save_players(pd):
    json.dump(pd, open(DATA_FILE+".tmp","w",encoding="utf-8"), ensure_ascii=False, indent=2)
    os.replace(DATA_FILE+".tmp", DATA_FILE)

players = load_players()

def champ_from_key(k): return CHAMPS[k]
def td(): return datetime.now(TZ).date().isoformat()
def clamp(x,l,h): return max(l, min(h, x))
def hp_bar(cur,mx,ln=10):
    mx=max(1,int(mx)); cur=max(0,min(int(cur),mx)); f=int(round((cur/mx)*ln))
    return "█"*f + "░"*(ln-f)
def fmt_hp(lbl,cur,mx):
    mx=max(1,int(mx)); cur=max(0,min(int(cur),mx))
    return f"{lbl}\nHP {cur:>3}/{mx:<3} [{hp_bar(cur,mx)}]"
def battle_hud(l1,h1,m1,l2,h2,m2): return fmt_hp(l1,h1,m1)+"\n\n"+fmt_hp(l2,h2,m2)
def xp_needed(lv):
    lv = max(1, min(int(lv), MAX_LEVEL))
    return {1:450,2:720,3:1125,4:1710,5:2520,6:3600,7:5085,8:7110,9:9900}.get(lv,9900)
def ck_input(a):
    if not a: return None
    return {"basaur":"basaurimon","basaurimon":"basaurimon","suimander":"suimander","mander":"suimander","suiqrtle":"suiqrtle","squirtle":"suiqrtle","qrtle":"suiqrtle","poolmon":"poolmon","suideer":"suideer","jengacide":"jengacide"}.get(a.lower().strip())
def get_stats(k,lv):
    lv=max(1,min(int(lv),MAX_LEVEL)); b=CHAMPS[k]["base"]
    return {"hp":int(round(b["hp"]+(lv-1)*2)),"atk":int(round(b["atk"]+(lv-1)*0.25)),"def":int(round(b["def"]+(lv-1)*0.3)),"spd":int(round(b["spd"]+(lv-1)*1))}
def display_name(uid,fb="Player"): return (players.get(uid,{}).get("name") or fb).strip()
def get_active_suimon_index(uid):
    p=players.get(uid,{}); its=p.get("owned_suimon",[])
    return max(0, min(int(p.get("active_suimon",0)), len(its)-1)) if its else 0
def get_active_suimon(uid):
    its=players.get(uid,{}).get("owned_suimon",[]); idx=get_active_suimon_index(uid)
    return its[idx] if 0<=idx<len(its) else None
def get_owned_suimon_list(uid): return players.get(uid,{}).get("owned_suimon",[])
def suimon_display_name(s): return s.get("nickname") or CHAMPS.get(s["species"],{}).get("display","Unknown")
def suimon_full_name(s):
    n=s.get("nickname"); b=CHAMPS.get(s["species"],{}).get("display","Unknown")
    return f"{n} ({b})" if n else b
def sanitize_nick(raw):
    return " ".join("".join(c for c in raw.strip() if c.isalnum() or c in " _-").split())[:18].strip()
def has_named_champ(uid):
    s=get_active_suimon(uid); return s is not None and bool(s.get("nickname"))
def needs_nickname_prompt(uid):
    s=get_active_suimon(uid); return s is not None and not s.get("nickname")
def start_nickname_prompt(uid): players[uid]["_awaiting_nickname"]=True; save_players(players)
def clear_nickname_prompt(uid): players[uid]["_awaiting_nickname"]=False; save_players(players)
def get_badges_display(uid):
    b=players.get(uid,{}).get("badges",[])
    if not b: return ""
    m={"cascade":"🌊","volcano":"🔥","earth":"🌍"}
    return " ".join(m.get(x,"🏅") for x in b)

def migrate_players():
    changed=False
    for uid,p in players.items():
        if "owned_suimon" in p:
            for s in p["owned_suimon"]:
                if s.get("species") in CHAMPS:
                    s["hp"]=max(0,min(int(s.get("hp",get_stats(s["species"],int(s.get("level",1)))["hp"])),get_stats(s["species"],int(s.get("level",1)))["hp"]))
            for o in ("champ","champ_nickname","level","xp","hp","awaiting_nickname","just_leveled"): p.pop(o,None)
            continue
        oc=p.get("champ")
        if oc not in CHAMPS: p["owned_suimon"]=[]; p["active_suimon"]=0; changed=True
        else:
            p["owned_suimon"]=[{"species":oc,"nickname":p.get("champ_nickname"),"level":int(p.get("level",1)),"xp":int(p.get("xp",0)),"hp":int(p.get("hp") or get_stats(oc,int(p.get("level",1)))["hp"]),"wins":0,"losses":0}]
            p["active_suimon"]=0
        for o in ("champ","champ_nickname","level","xp","hp","awaiting_nickname","just_leveled"): p.pop(o,None)
        changed=True
    if changed: save_players(players)
migrate_players()

def ensure_player(uid, nm, un=None):
    if uid not in players:
        players[uid]={"name":nm,"username":un or "","suiballs":0,"last_daily":None,"wins":0,"losses":0,"chats":[],"badges":[],"net_balls":0,"last_netball_daily":None,"owned_suimon":[],"active_suimon":0}
    else:
        if nm: players[uid]["name"]=nm
        players[uid]["username"]=un or players[uid].get("username","")
        for k in ("net_balls","last_netball_daily","owned_suimon","active_suimon","wins","losses"): players[uid].setdefault(k,0 if k!="owned_suimon" else [])

def ensure_daily(uid):
    p=players[uid]; t=td(); changed=False
    if p.get("last_daily")!=t: p["suiballs"]=min(get_suiball_cap(),int(p.get("suiballs",0))+get_daily_suiballs()); p["last_daily"]=t; changed=True
    if p.get("last_netball_daily")!=t: p["net_balls"]=min(NETBALL_CAP,int(p.get("net_balls",0))+DAILY_NETBALLS); p["last_netball_daily"]=t; changed=True
    return changed

def get_active_suimon_hp(uid):
    s=get_active_suimon(uid)
    if not s: return 0
    mx=get_stats(s["species"],int(s.get("level",1)))["hp"]
    return max(0,min(int(s.get("hp",mx)),mx))

def set_active_suimon_hp(uid,nhp):
    s=get_active_suimon(uid)
    if s: s["hp"]=max(0,min(int(nhp),get_stats(s["species"],int(s.get("level",1)))["hp"]))

def heal_suimon_by_index(uid,idx):
    its=players[uid].get("owned_suimon",[])
    if 0<=idx<len(its):
        s=its[idx]; mx=get_stats(s["species"],int(s.get("level",1)))["hp"]; s["hp"]=mx
        return mx,mx
    return 0,0

def grant_xp_to_suimon(s,gained):
    if s["species"] not in CHAMPS: return
    ol=max(1,min(int(s.get("level",1)),MAX_LEVEL)); ch=int(s.get("hp",0)); mx=get_stats(s["species"],ol)["hp"]
    s["level"]=ol; s["xp"]=int(s.get("xp",0))+int(gained)
    leveled=False
    while int(s["level"])<MAX_LEVEL and s["xp"]>=xp_needed(int(s["level"])):
        s["xp"]-=xp_needed(int(s["level"])); s["level"]=int(s["level"])+1; leveled=True
        nmx=get_stats(s["species"],int(s["level"]))["hp"]; ch=min(nmx,ch+max(0,nmx-mx)); mx=nmx
    if int(s["level"])>=MAX_LEVEL: s["level"]=MAX_LEVEL; s["xp"]=0
    s["hp"]=max(0,min(ch,mx)); s["just_leveled"]=leveled

def award_battle_xp(wid,lid,wi,li):
    ws=players[wid]["owned_suimon"][wi]; ls=players[lid]["owned_suimon"][li]
    wl=int(ws.get("level",1)); ll=int(ls.get("level",1)); diff=ll-wl
    xpw=75 if diff>=3 else 65 if diff==2 else 55 if diff==1 else 35 if diff<0 else 45
    xpl=20; bst=get_xp_boost_multiplier(); xpw=int(round(xpw*bst)); xpl=int(round(xpl*bst))
    players[wid]["wins"]=int(players[wid].get("wins",0))+1
    players[lid]["losses"]=int(players[lid].get("losses",0))+1
    grant_xp_to_suimon(ws,xpw); grant_xp_to_suimon(ls,xpl)
    return xpw,xpl

def _remember_chat(uid,cid):
    if uid in players:
        chats=players[uid].setdefault("chats",[]);
        if cid not in chats: chats.append(cid)

def _eligible_players_in_chat(cid):
    return [uid for uid,p in players.items() if p.get("owned_suimon") and cid in p.get("chats",[])]

def _parse_target_user_id(update, context):
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        return str(update.message.reply_to_message.from_user.id)
    if context.args:
        arg=context.args[0].lstrip("@").lower().replace(" ","")
        for uid,p in players.items():
            if arg in ((p.get("name") or "").lower().replace(" ",""), (p.get("username") or "").lower().lstrip("@")):
                return uid
    return None

def ranking_sort_key(uid):
    p=players.get(uid,{}); return (-int(p.get("wins",0)), int(p.get("losses",0)), display_name(uid).lower(), uid)

def get_leaderboard(limit=10):
    r=[]
    for uid,p in players.items():
        if not p.get("owned_suimon"): continue
        r.append((uid,display_name(uid),sum(s.get("xp",0) for s in p["owned_suimon"]),max(s.get("level",1) for s in p["owned_suimon"]),int(p.get("wins",0)),int(p.get("losses",0))))
    r.sort(key=lambda x: ranking_sort_key(x[0]))
    return r[:limit]

def mention_html(uid,fb=None):
    return f'<a href="tg://user?id={uid}">{html.escape(fb or display_name(uid) or "Player")}</a>'

def build_rankings_text(uid=None,limit=10):
    top=get_leaderboard(limit)
    if not top: return "🏆 <b>RANKINGS</b>\n\nNo trainers ranked yet."
    lines=["🏆 <b>RANKINGS</b>",""]; medals={1:"🥇",2:"🥈",3:"🥉"}
    for rank,(pid,nm,_,_,w,l) in enumerate(top,1):
        s=get_active_suimon(pid); cn=html.escape(suimon_full_name(s)) if s else "Unknown"
        tot=w+l; wr=int(round((w/tot)*100)) if tot else 0; lnk=mention_html(pid,nm)
        if rank<=3:
            lines.append(f"{medals[rank]} <b>{lnk}</b> {TYPE_EMOJI.get(CHAMPS.get(s['species'],{}).get('type'),'✨') if s else '✨'}")
            lines.append(f"<code>{cn}</code> • Lv.<b>{s['level'] if s else '?'}</b>")
            lines.append(f"⚔️ <b>{w}W / {l}L</b> • <b>{wr}% WR</b>\n")
        else: lines.append(f"{rank}. <b>{lnk}</b> • Lv.<b>{s['level'] if s else '?'}</b>")
    if uid and get_active_suimon(uid):
        s=get_active_suimon(uid)
        sorted_uids = [u for u,p in players.items() if p.get("owned_suimon")]
        sorted_uids.sort(key=ranking_sort_key)
        try: rk = sorted_uids.index(uid) + 1
        except ValueError: rk = "?"
        lines.extend(["","━━━━━━━━━━",f"👤 <b>You:</b> #{rk} • Lv.<b>{s['level']}</b>"])
    return "\n".join(lines)

# ---------- KAMPFENGINE / MESSAGE EDIT ----------
def type_mult(at,df):
    if CHAMPS_BY_TYPE[at]["strong_against"]==df: return 1.08,"strong"
    if CHAMPS_BY_TYPE[at]["weak_to"]==df: return 0.95,"weak"
    return 1.0,"neutral"
def pick_first_attacker(sp1,sp2):
    if sp1==sp2: return 0 if random.random()<0.5 else 1
    return 0 if random.random()<clamp(0.5+(sp1-sp2)/40.0,0.25,0.75) else 1
def level_gap_miss_penalty(al,dl):
    gap=al-dl
    return min(0.15,gap*0.03) if gap>0 else 0.0
def calc_damage(aatk,ddef,lv,pwr,tmult,cmult,dlv=0):
    eatk=max(1,int(aatk)); edef=max(1,int(ddef)); elv=max(lv,5)
    lvf=1.0+(elv-3)*0.015; base=4.0*pwr*eatk/(edef*1.25); base=(base/8)+2
    base*=lvf*random.uniform(0.92,1.08)
    return max(1,int(round(base*tmult*cmult)))
def status_tick_lines(cs,cd):
    out=[]
    if cs.get("burn_turns",0)>0:
        cs["burn_turns"]-=1; dmg=max(2,int(round(cs["max_hp"]*random.uniform(0.08,0.09))))
        cs["hp"]-=dmg; out.append(random.choice([f"{STATUS_EMOJI['burn']} {cd} burns! (-{dmg})",f"{STATUS_EMOJI['burn']} {cd} is on fire! (-{dmg})"]))
    if cs.get("poison_turns",0)>0:
        cs["poison_turns"]-=1; dmg=max(1,int(round(cs["max_hp"]*random.uniform(0.04,0.05))))
        cs["hp"]-=dmg; out.append(random.choice([f"{STATUS_EMOJI['poison']} {cd} twitches! (-{dmg})",f"{STATUS_EMOJI['poison']} {cd} goes pale! (-{dmg})"]))
    if cs.get("wet_dream_turns",0)>0:
        cs["wet_dream_turns"]-=1
        if cs["wet_dream_turns"]==0: out.append(f"{STATUS_EMOJI['wet_dream']} {cd} comes back down.")
        else: out.append(random.choice([f"{STATUS_EMOJI['wet_dream']} {cd} is still seeing things!",f"{STATUS_EMOJI['wet_dream']} {cd} flinches!"]))
    return out
def can_act(cs):
    if cs.get("sleep_turns",0)>0:
        cs["sleep_turns"]-=1
        if cs["sleep_turns"]==0: cs["has_slept"]=True
        return False,[random.choice(["passed out!","is sleeping!","out cold!"])]
    if cs.get("confuse_turns",0)>0:
        cs["confuse_turns"]-=1; dmg=max(2,int(round(cs["max_hp"]*random.uniform(0.08,0.10))))
        cs["hp"]-=dmg
        return False,[("html_named",random.choice([f"<b>{{champ_name}}</b> tweaks on PCP! (-{dmg})",f"<b>{{champ_name}}</b> attacks itself! (-{dmg})"]))]
    if cs.get("stun_turns",0)>0:
        cs["stun_turns"]-=1; return False,["is stunned!"]
    return True,[]
def do_move(atk,dfd,ak,dk,alv,mv,an=None,dn=None,dlv=0):
    out=[]; a=CHAMPS[ak]; d=CHAMPS[dk]; an=an or a["display"]; dn=dn or d["display"]
    bmiss=1.0-float(mv.get("acc",0.9)); emiss=min(0.60,bmiss+level_gap_miss_penalty(alv,dlv))
    if random.random()<emiss:
        out.append(f"{TYPE_EMOJI[a['type']]} {an} used {mv['name']}!"); out.append("💨 Missed!")
        return out
    out.append(("html",f"{TYPE_EMOJI[a['type']]} <b>{html.escape(an)}</b> {random.choice(mv.get('text',['attacks!']))}"))
    kind=mv.get("kind","damage")
    if kind=="status_sleep":
        if dfd.get("sleep_turns",0)>0: out.append(f"Already sleeping!"); return out
        cd=atk.get("sleep_spore_cooldown",0)
        if cd>0: atk["sleep_spore_cooldown"]=cd-1; out.append(f"Sleep Spore recharging ({cd} turns)"); return out
        if atk.get("last_used_sleep",False): atk["sleep_turns"]=1; atk["last_used_sleep"]=False; out.append("Backfires!"); return out
        t=mv.get("sleep_turns",[1,2]); st=random.randint(t[0],t[1]); dfd["sleep_turns"]=st; dfd["has_slept"]=True
        atk["last_used_sleep"]=True; atk["sleep_spore_cooldown"]=3
        out.append(f"💤 {dn} asleep for {st} turns!"); return out
    if kind=="status_wet_dream":
        ul=atk.get("wet_dream_uses_left",0)
        if ul<=0: out.append("Used up!"); return out
        if dfd.get("wet_dream_turns",0)>0: out.append("Already frightened!"); return out
        mult,eff=type_mult(a["type"],d["type"])
        dmg=calc_damage(int(atk["atk"]),int(dfd["def"]),alv,28,mult,1.0,dlv)
        dfd["hp"]-=dmg; t=mv.get("wet_dream_turns",[2,3]); wdt=random.randint(t[0],t[1])
        dfd["wet_dream_turns"]=wdt; atk["wet_dream_uses_left"]=ul-1
        out.append(("html",f"😨 {dn} takes <b>{dmg} dmg</b>! Frightened for {wdt} turns!")); return out
    atk["last_used_sleep"]=False
    if atk.get("sleep_spore_cooldown",0)>0: atk["sleep_spore_cooldown"]-=1
    if kind=="status_burn":
        if dfd.get("burn_turns",0)>0: out.append("Already burning!"); return out
        t=mv.get("burn_turns",[2,3]); dfd["burn_turns"]=random.randint(t[0],t[1])
        out.append(f"🔥 {dn} burned!"); return out
    if kind=="status_confuse":
        if dfd.get("confuse_turns",0)>0: out.append("Already confused!"); return out
        rare=random.random()<float(mv.get("confuse_rare_chance",0.15)); ct=2 if rare else 1
        dfd["confuse_turns"]=ct; out.append(f"🌀 {dn} confused for {ct} turns!"); return out
    if kind=="status_debuff":
        if mv.get("atk_debuff_pct"):
            if not dfd.get("atk_debuff_turns",0):
                dfd["atk_debuff_turns"]=int(mv.get("debuff_turns",2))
                dfd["atk"]=int(dfd.get("atk",0)*(1-float(mv["atk_debuff_pct"])))
                out.append(f"📉 {dn}'s ATK dropped!")
            else: out.append(f"{dn} already debuffed!")
            return out
        if mv.get("def_speed_debuff"):
            if not dfd.get("def_speed_debuff_turns",0):
                dfd["def_speed_debuff_turns"]=int(mv.get("debuff_turns",2))
                dfd["def"]=int(dfd.get("def",0)*0.85); dfd["spd"]=int(dfd.get("spd",0)*0.85)
                out.append(f"💊 {dn}'s DEF and SPD dropped!")
            else: out.append(f"{dn} already pressured!")
            return out
    pwr=int(mv.get("power",40))
    crit_ch=0.08+float(mv.get("crit_bonus",0.0))
    crit=random.random()<crit_ch if kind=="damage_highcrit" else random.random()<0.08
    cmult=1.5 if crit else 1.0; mult,eff=type_mult(a["type"],d["type"])
    dmg=calc_damage(int(atk["atk"]),int(dfd["def"]),alv,pwr,mult,cmult,dlv)
    if atk.get("wet_dream_turns",0)>0: dmg=max(1,int(round(dmg*0.90)))
    if mv.get("debuff_bonus") and dfd.get("def_speed_debuff_turns",0)>0: dmg=int(round(dmg*1.25)); out.append("🧨 Debuff bonus!")
    dfd["hp"]-=dmg
    et=""; 
    if eff=="strong": et=" 💥 Super effective!"
    elif eff=="weak": et=" 🫧 Not very effective…"
    ct_=random.choice([" CRIT!"," CRIT — devastating!"," CRIT — dirty hit!"]) if crit else ""
    out.append(("html",f"💢 Hit: <b>{dmg} damage</b>{ct_}{et}"))
    if mv.get("spd_boost_chance") and random.random()<float(mv["spd_boost_chance"]):
        atk["spd"]=int(atk.get("spd",0))+int(mv.get("spd_boost",2)); out.append(f"⚡ SPD boosted!")
    if mv.get("def_down_chance") and random.random()<float(mv["def_down_chance"]):
        dfd["def"]=int(dfd.get("def",0)*0.85); dfd["def_down_turns"]=int(mv.get("def_down_turns",2)); out.append(f"🛡️ DEF dropped!")
    if mv.get("stun_chance") and random.random()<float(mv["stun_chance"]):
        dfd["stun_turns"]=int(mv.get("stun_turns",1)); out.append(f"🌀 Stunned!")
    return out

async def _safe_edit(bot,cid,mid,txt,markup=None):
    if len(txt)>MAX_MESSAGE_CHARS: txt=txt[-MAX_MESSAGE_CHARS:]
    for _ in range(5):
        try: await bot.edit_message_text(chat_id=cid,message_id=mid,text=txt,parse_mode='HTML',disable_web_page_preview=True,reply_markup=markup); return True
        except RetryAfter as e: await asyncio.sleep(float(getattr(e,"retry_after",1.5)))
        except (TimedOut,NetworkError): await asyncio.sleep(0.8)
        except BadRequest: txt="".join(ch for ch in txt if ch>=" " or ch in "\n\t"); await asyncio.sleep(0.25)
        except: await asyncio.sleep(0.5)
    return False

async def _battle_reposition_message(bot,cid,state,txt,markup=None,force=False):
    now=time.monotonic(); cd=float(state.get("reposition_cooldown",REPOSITION_COOLDOWN))
    if not force and (now-float(state.get("last_reposition",0.0)))<cd:
        if await _safe_edit(bot,cid,state["message_id"],txt,markup): state["last_rendered_text"]=txt; state["last_reply_markup"]=markup
        return
    for _ in range(3):
        try:
            nm=await bot.send_message(chat_id=cid,text=txt,parse_mode='HTML',disable_web_page_preview=True,reply_markup=markup)
            old=state["message_id"]; state["message_id"]=nm.message_id; state["last_reposition"]=now
            state["last_rendered_text"]=txt; state["last_reply_markup"]=markup
            asyncio.ensure_future(bot.delete_message(chat_id=cid,message_id=old)); return
        except RetryAfter as e: await asyncio.sleep(float(getattr(e,"retry_after",1.5)))
        except (TimedOut,NetworkError): await asyncio.sleep(0.8)
        except: await asyncio.sleep(0.4)
    await _safe_edit(bot,cid,state["message_id"],txt,markup)

def _battle_render(state):
    lines=state["log_lines"]
    if len(lines)>MAX_LINES_SHOWN: del lines[:-MAX_LINES_SHOWN]
    body="\n".join(lines) if lines else "…"
    while len(body)>MAX_MESSAGE_CHARS and len(lines)>8: del lines[:3]; body="\n".join(lines)
    if len(body)>MAX_MESSAGE_CHARS: body=body[-MAX_MESSAGE_CHARS:]
    return body

def _battle_hud_html(state):
    return f"<pre>{html.escape(battle_hud(state['c1_label'],state['champ1']['hp'],state['champ1']['max_hp'],state['c2_label'],state['champ2']['hp'],state['champ2']['max_hp']),quote=False)}</pre>"

async def _battle_push_message(cid,state,context,line,delay=ACTION_DELAY,markup=None,force_reposition=False,raw_html=False):
    if isinstance(line,tuple) and line[0]=="html": state["log_lines"].append(line[1])
    elif raw_html: state["log_lines"].append(line)
    else: state["log_lines"].append(html.escape(str(line),quote=False))
    txt=_battle_render(state); await _battle_reposition_message(context.bot,cid,state,txt,markup,force=force_reposition)
    if delay>0: await asyncio.sleep(delay)

async def _battle_push_hud(cid,state,context,delay=HUD_DELAY,markup=None,force_reposition=False):
    state["log_lines"].append(_battle_hud_html(state)); txt=_battle_render(state)
    await _battle_reposition_message(context.bot,cid,state,txt,markup,force=force_reposition)
    if delay>0: await asyncio.sleep(delay)

def _battle_turn_user(state): return state["user"] if state["turn"]==0 else state["opponent"]
def _battle_turn_name(state): return state["p1_name"] if state["turn"]==0 else state["p2_name"]
def _battle_turn_champ_key(state): return state["c1_key"] if state["turn"]==0 else state["c2_key"]
def _battle_turn_champ_state(state): return state["champ1"] if state["turn"]==0 else state["champ2"]
def _battle_def_champ_key(state): return state["c2_key"] if state["turn"]==0 else state["c1_key"]
def _battle_def_champ_state(state): return state["champ2"] if state["turn"]==0 else state["champ1"]
def _battle_turn_level(state): return state["lv1"] if state["turn"]==0 else state["lv2"]
def _battle_next_turn(state): state["turn"]=1-state["turn"]

async def _battle_prompt_turn(cid,state,context):
    if state["actions"]%2==0: state["round"]+=1; await _battle_push_message(cid,state,context,f"━━━ Round {state['round']} ━━━",delay=0.35)
    nm=_battle_turn_name(state); ck=_battle_turn_champ_key(state); tu=_battle_turn_user(state)
    cn=suimon_display_name(get_active_suimon(tu)) if get_active_suimon(tu) else "???"
    kb=_battle_move_keyboard(cid,ck,tu,state)
    await _battle_push_message(cid,state,context,f"\n🎯 {nm}'s turn — choose a move for {cn}:",delay=0.05,markup=kb,force_reposition=True)

async def _end_battle(cid,state,context,winner,loser):
    players[state["user"]]["owned_suimon"][state["u_idx"]]["hp"]=max(state["champ1"]["hp"],0)
    players[state["opponent"]]["owned_suimon"][state["o_idx"]]["hp"]=max(state["champ2"]["hp"],0)
    ui=state["u_idx"]; oi=state["o_idx"]; xpw,xpl=award_battle_xp(winner,loser,ui,oi)
    save_players(players)
    ws=players[winner]["owned_suimon"][ui if winner==state["user"] else oi]
    await _battle_push_message(cid,state,context,"The dust settles…",delay=0.45)
    await _battle_push_message(cid,state,context,f"🏆 Winner: {display_name(winner)} with {suimon_full_name(ws)}!",delay=0.45)
    await _battle_push_message(cid,state,context,f"🎁 XP: {xpw} (Winner) / {xpl} (Loser)",delay=0.35)
    lvlups=[]
    us=players[state["user"]]["owned_suimon"][ui]; os_=players[state["opponent"]]["owned_suimon"][oi]
    if us.get("just_leveled"): lvlups.append((state["p1_name"],us["level"])); us.pop("just_leveled",None)
    if os_.get("just_leveled"): lvlups.append((state["p2_name"],os_["level"])); os_.pop("just_leveled",None)
    if lvlups:
        await _battle_push_message(cid,state,context,"📣 Level Up!",delay=0.25)
        for n,lv in lvlups: await _battle_push_message(cid,state,context,f"⭐ {n} is now Lv.{lv}!",delay=0.25)
    await _battle_push_message(cid,state,context,"✅ Battle complete.",delay=END_DELAY)
    BATTLES.pop(cid,None); ACTIVE_BATTLES.discard(cid)

def _battle_move_keyboard(cid,ck,pid,state):
    moves=CHAMPS[ck]["moves"]; rows=[]; row=[]
    for idx,m in enumerate(moves[:4]):
        row.append(InlineKeyboardButton(m["name"],callback_data=f"mv|{cid}|{idx}"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    balls=int(players.get(pid,{}).get("suiballs",0)); used=state.get("suiballs_used",{}).get(pid,0)
    rem=max(0,1-used); can=balls>0 and rem>0
    bl=f"🧿 Use Suiball ({balls} 🎒 · {rem}/1 left)" if can else "🧿 Suiball (0 left)"
    rows.append([InlineKeyboardButton(bl,callback_data=f"battle_heal|{cid}" if can else f"noop|{cid}")])
    rows.append([InlineKeyboardButton("🏳️ Forfeit",callback_data=f"ff|{cid}")])
    return InlineKeyboardMarkup(rows)

async def battle_move_callback(update,context):
    if not await ensure_allowed_chat(update,context): return
    q=update.callback_query
    if not q or not q.message: return
    await q.answer()
    global players; players=load_players()
    data=q.data or ""; parts=data.split("|")
    if len(parts)<2: return
    kind=parts[0]
    try: cid=int(parts[1])
    except: return
    state=BATTLES.get(cid)
    if not state:
        try: await q.edit_message_reply_markup(reply_markup=None)
        except: pass
        return
    clicker=str(q.from_user.id); await q.answer()
    if kind=="noop": return
    if state.get("resolving"):
        if time.monotonic()-float(state.get("resolving_since",0.0))>30: state["resolving"]=False
        else: return
    if kind=="ff":
        if clicker not in (state["user"],state["opponent"]): return
        winner=state["opponent"] if clicker==state["user"] else state["user"]
        await _battle_push_message(cid,state,context,f"🏳️ {display_name(clicker)} forfeits!",delay=0.25)
        await _end_battle(cid,state,context,winner=winner,loser=clicker); return
    if kind=="battle_heal":
        tu=_battle_turn_user(state)
        if clicker!=tu: await q.answer("Not your turn.",show_alert=False); return
        balls=int(players.get(clicker,{}).get("suiballs",0))
        if balls<=0: await q.answer("No Suiballs!",show_alert=True); return
        used=state.get("suiballs_used",{}).get(clicker,0)
        if used>=1: return
        state["resolving"]=True; state["resolving_since"]=time.monotonic()
        try:
            players[clicker]["suiballs"]=balls-1; save_players(players)
            state["suiballs_used"][clicker]=used+1
            cs=_battle_turn_champ_state(state); cs["hp"]=cs["max_hp"]
            hn=suimon_display_name(get_active_suimon(clicker)) if get_active_suimon(clicker) else "???"
            await _battle_reposition_message(context.bot,cid,state,_battle_render(state),markup=None)
            await _battle_push_message(cid,state,context,f"🧿 {display_name(clicker)} used a Suiball on {hn}! HP fully restored!",delay=0.5)
            await _battle_push_hud(cid,state,context,delay=0.25)
            state["actions"]+=1; _battle_next_turn(state); await _battle_prompt_turn(cid,state,context)
        finally:
            if BATTLES.get(cid) is state: state["resolving"]=False
        return
    if kind!="mv" or len(parts)!=3: return
    tu=_battle_turn_user(state)
    if clicker!=tu: await q.answer("Not your turn.",show_alert=False); return
    state["resolving"]=True; state["resolving_since"]=time.monotonic(); state["last_move_ts"]=time.monotonic()
    atk=_battle_turn_champ_state(state); dfd=_battle_def_champ_state(state)
    ak=_battle_turn_champ_key(state); dk=_battle_def_champ_key(state)
    alv=_battle_turn_level(state)
    an=suimon_display_name(get_active_suimon(clicker)) if get_active_suimon(clicker) else "???"
    await _battle_reposition_message(context.bot,cid,state,_battle_render(state),markup=None)
    try:
        for line in status_tick_lines(atk,an): await _battle_push_message(cid,state,context,line,delay=0.45)

        # SOFORT prüfen, ob Angreifer durch Burn/Poison gestorben ist
        if atk["hp"]<=0:
            winner=state["opponent"] if clicker==state["user"] else state["user"]
            await _end_battle(cid,state,context,winner=winner,loser=clicker); return

        ok,sl=can_act(atk)
        if not ok:
            raw=sl[0]
            if isinstance(raw,tuple) and raw[0]=="html_named": line_out=("html",raw[1].format(champ_name=html.escape(an)))
            elif isinstance(raw,tuple) and raw[0]=="html": line_out=raw
            else: line_out=("html",f"{STATUS_EMOJI.get('confuse' if 'PCP' in str(raw) else 'sleep','💤')} <b>{html.escape(an)}</b> {raw}")
            await _battle_push_message(cid,state,context,line_out,delay=0.55)
        else:
            idx=max(0,min(int(parts[2]),len(CHAMPS[ak]["moves"])-1)); mv=CHAMPS[ak]["moves"][idx]
            du=state["opponent"] if clicker==state["user"] else state["user"]
            dlv=state["lv2"] if clicker==state["user"] else state["lv1"]
            dn=suimon_display_name(get_active_suimon(du)) if get_active_suimon(du) else "???"
            for line in do_move(atk,dfd,ak,dk,alv,mv,an,dn,dlv):
                await _battle_push_message(cid,state,context,line,delay=0.55)

        atk["hp"]=max(0,int(atk["hp"])); dfd["hp"]=max(0,int(dfd["hp"]))
        await _battle_push_hud(cid,state,context,delay=0.25)

        # SOFORT prüfen, ob Verteidiger gestorben ist
        if state["champ1"]["hp"]<=0 or state["champ2"]["hp"]<=0:
            winner=state["user"] if state["champ1"]["hp"]>0 else state["opponent"]
            loser=state["opponent"] if winner==state["user"] else state["user"]
            await _end_battle(cid,state,context,winner=winner,loser=loser); return

        state["actions"]+=1
        if state["round"]>=state["max_rounds"]:
            if state["champ1"]["hp"]==state["champ2"]["hp"]: winner=state["user"] if random.random()<0.5 else state["opponent"]
            else: winner=state["user"] if state["champ1"]["hp"]>state["champ2"]["hp"] else state["opponent"]
            loser=state["opponent"] if winner==state["user"] else state["user"]
            await _battle_push_message(cid,state,context,"⏱️ Time! Battle ends by decision.",delay=0.35)
            await _end_battle(cid,state,context,winner=winner,loser=loser); return

        _battle_next_turn(state); await _battle_prompt_turn(cid,state,context)
    finally:
        if BATTLES.get(cid) is state: state["resolving"]=False

async def _auto_move(cid,state,context):
    tu=_battle_turn_user(state); ak=_battle_turn_champ_key(state)
    moves=CHAMPS[ak]["moves"]; idx=random.randint(0,len(moves)-1)
    state["resolving"]=True; state["resolving_since"]=time.monotonic(); state["last_move_ts"]=time.monotonic()
    atk=_battle_turn_champ_state(state); dfd=_battle_def_champ_state(state)
    dk=_battle_def_champ_key(state); alv=_battle_turn_level(state)
    an=suimon_display_name(get_active_suimon(tu)) if get_active_suimon(tu) else "???"
    du=state["opponent"] if tu==state["user"] else state["user"]
    dlv=state["lv2"] if tu==state["user"] else state["lv1"]
    dn=suimon_display_name(get_active_suimon(du)) if get_active_suimon(du) else "???"
    try:
        await _battle_push_message(cid,state,context,f"⏰ {_battle_turn_name(state)} is AFK — auto-move triggered!",delay=0.4)
        for line in status_tick_lines(atk,an): await _battle_push_message(cid,state,context,line,delay=0.45)

        # SOFORT prüfen, ob Angreifer durch Status gestorben ist
        if atk["hp"]<=0:
            winner=state["opponent"] if tu==state["user"] else state["user"]
            await _end_battle(cid,state,context,winner=winner,loser=tu); return

        ok,sl=can_act(atk)
        if not ok:
            raw=sl[0]
            if isinstance(raw,tuple) and raw[0]=="html_named": line_out=("html",raw[1].format(champ_name=html.escape(an)))
            elif isinstance(raw,tuple) and raw[0]=="html": line_out=raw
            else: line_out=("html",f"{STATUS_EMOJI['sleep']} <b>{html.escape(an)}</b> {raw}")
            await _battle_push_message(cid,state,context,line_out,delay=0.55)
        else:
            for line in do_move(atk,dfd,ak,dk,alv,moves[idx],an,dn,dlv): await _battle_push_message(cid,state,context,line,delay=0.55)

        atk["hp"]=max(0,int(atk["hp"])); dfd["hp"]=max(0,int(dfd["hp"]))
        await _battle_push_hud(cid,state,context,delay=0.25)

        # SOFORT prüfen, ob Verteidiger gestorben ist
        if state["champ1"]["hp"]<=0 or state["champ2"]["hp"]<=0:
            winner=state["user"] if state["champ1"]["hp"]>0 else state["opponent"]
            loser=state["opponent"] if winner==state["user"] else state["user"]
            await _end_battle(cid,state,context,winner=winner,loser=loser); return

        state["actions"]+=1
        if state["round"]>=state["max_rounds"]:
            winner=state["user"] if random.random()<0.5 else state["opponent"] if state["champ1"]["hp"]==state["champ2"]["hp"] else (state["user"] if state["champ1"]["hp"]>state["champ2"]["hp"] else state["opponent"])
            loser=state["opponent"] if winner==state["user"] else state["user"]
            await _battle_push_message(cid,state,context,"⏱️ Time! Battle ends by decision.",delay=0.35)
            await _end_battle(cid,state,context,winner=winner,loser=loser); return

        _battle_next_turn(state); await _battle_prompt_turn(cid,state,context)
    finally:
        if BATTLES.get(cid) is state: state["resolving"]=False

async def _afk_watcher(context):
    now=time.monotonic()
    for cid,state in list(BATTLES.items()):
        if state.get("resolving"): continue
        if now-state.get("last_move_ts",now)>=AFK_TIMEOUT:
            state["last_move_ts"]=now
            try: await _auto_move(cid,state,context)
            except Exception as e: print(f"[AFK] Error {e}")

# ---------- MENÜS ----------
def main_menu_kb(uid=None):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Champs",callback_data="menu|champs"), InlineKeyboardButton("⚔️ Fight",callback_data="menu|fight")],
        [InlineKeyboardButton("🏆 Rankings",callback_data="menu|leaderboard"), InlineKeyboardButton("🪪 Profile",callback_data="menu|profile")],
        [InlineKeyboardButton("🎒 Inventory",callback_data="menu|inventory"), InlineKeyboardButton("🩹 Heal",callback_data="menu|heal")],
        [InlineKeyboardButton("🌍 Explore",callback_data="menu|explore")],
    ])

def choose_champ_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌿 Basaurimon",callback_data="choose|basaurimon")],
        [InlineKeyboardButton("🔥 Suimander",callback_data="choose|suimander")],
        [InlineKeyboardButton("💧 Suiqrtle",callback_data="choose|suiqrtle")],
        [InlineKeyboardButton("⬅️ Back",callback_data="menu|home")],
    ])

def naming_prompt_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data="menu|home")]])

def nickname_required_text(uid):
    s=get_active_suimon(uid)
    if not s: return "Choose your champ first with /choose."
    return f"📝 <b>Name required</b>\n\nYour starter is <b>{CHAMPS.get(s['species'],{}).get('display','Unknown')}</b>.\n\nUse <code>/name YourName</code>"

def fancy_menu_caption(uid):
    p=players.get(uid,{}); s=get_active_suimon(uid)
    title=f"🧭 <b>{html.escape(display_name(uid))}'s Menu</b>"
    if not s: return f"{title}\n\n🔥 <b>Welcome to Suimon Arena</b>\nPick your starter, name it and begin.\n\n• Open 📜 Champs\n• Pick your starter\n• Name it with /name\n• Challenge with /fight"
    lv=int(s.get("level",1)); xp=int(s.get("xp",0)); need=xp_needed(lv)
    w=int(s.get("wins",0)); l=int(s.get("losses",0))
    balls=int(p.get("suiballs",0)); nballs=int(p.get("net_balls",0))
    st=get_stats(s["species"],lv); chp=s.get("hp",st["hp"])
    cl=html.escape(suimon_full_name(s)); ti=TYPE_EMOJI.get(CHAMPS[s["species"]]["type"],"✨")
    ts=len(p.get("owned_suimon",[]))
    return f"{title}\n\n{ti} <b>{cl}</b> • Lv.<b>{lv}</b>\n❤️ <b>HP:</b> {chp}/{st['hp']}\n✨ <b>XP:</b> {xp}/{need if lv<MAX_LEVEL else 0}\n⚔️ <b>Record:</b> {w}W / {l}L\n🎒 <b>Suiballs:</b> {balls} | 🥅 <b>Net Balls:</b> {nballs}\n📦 <b>Team:</b> {ts} Suimon\n\nChoose your next move below."

# ---------- COMMANDS ----------
async def _bootstrap_user(update):
    global players; players=load_players()
    uid=str(update.effective_user.id); nm=(update.effective_user.first_name or "Player").strip()
    ensure_player(uid,nm,update.effective_user.username)
    if update.effective_chat: _remember_chat(uid,int(update.effective_chat.id))
    ensure_daily(uid); save_players(players); return uid

async def menu(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message: return
    await send_menu_photo(update.message,fancy_menu_caption(uid),main_menu_kb(uid))

async def intro(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    lines=["🎮 <b>Welcome to Suimon Arena</b>","","Turn based Telegram PvP.","","━━━ How to play ━━━","1. Pick a starter.","2. Name it with /name.","3. Challenge with /fight.","4. Explore with /explore.","5. Choose moves with buttons.","","Type chart: 🔥 > 🌿 > 💧 > 🔥",f"Daily: {DAILY_SUIBALLS} Suiballs, {DAILY_NETBALLS} Net Ball. Max Level {MAX_LEVEL}."]
    if not get_active_suimon(uid): lines.insert(2,"⚠️ You haven't chosen a champ yet.")
    await update.message.reply_text("\n".join(lines),reply_markup=main_menu_kb(uid),parse_mode="HTML")

async def start(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if update.message: await send_menu_photo(update.message,fancy_menu_caption(uid),main_menu_kb(uid))

async def champs_cmd(update,context):
    if not await ensure_allowed_chat(update,context): return
    await _bootstrap_user(update)
    lines=["📜 Starter Champs",""]
    for k in ["basaurimon","suimander","suiqrtle"]:
        c=CHAMPS[k]; moves=", ".join(m["name"] for m in c["moves"])
        lines.append(f"{TYPE_EMOJI[c['type']]} {c['display']} — {c['type']}\n   Moves: {moves}\n")
    if update.message: await update.message.reply_text("🌟 <b>Choose your starter</b>\n\n"+"\n".join(lines),choose_champ_kb(),parse_mode="HTML")

async def choose(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message: return
    if not context.args: await update.message.reply_text("Choose via Menu → 📜 Champs.",reply_markup=main_menu_kb(uid)); return
    if get_owned_suimon_list(uid): await update.message.reply_text("Already chose a starter.",reply_markup=main_menu_kb(uid)); return
    ck=ck_input(context.args[0])
    if ck not in ("basaurimon","suimander","suiqrtle"): await update.message.reply_text("Unknown champ.",reply_markup=main_menu_kb(uid)); return
    c=CHAMPS[ck]; players[uid]["owned_suimon"]=[{"species":ck,"nickname":None,"level":1,"xp":0,"hp":get_stats(ck,1)["hp"],"wins":0,"losses":0}]
    players[uid]["active_suimon"]=0; players[uid]["suiballs"]=max(int(players[uid].get("suiballs",0)),1)
    start_nickname_prompt(uid); save_players(players)
    await update.message.reply_text(f"📝 <b>Starter selected</b>\n\nYou picked <b>{c['display']}</b> {TYPE_EMOJI[c['type']]}.\n\nUse <code>/name YourName</code>",naming_prompt_kb(),parse_mode="HTML")

async def nickname(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message: return
    s=get_active_suimon(uid)
    if not s: await update.message.reply_text("Choose a champ first.",reply_markup=main_menu_kb(uid)); return
    raw=" ".join(context.args).strip()
    if not raw: start_nickname_prompt(uid); await update.message.reply_text(f"📝 Current: <b>{html.escape(suimon_full_name(s))}</b>\nUse <code>/name YourName</code>",naming_prompt_kb(),parse_mode="HTML"); return
    nick=sanitize_nick(raw)
    if len(nick)<2: start_nickname_prompt(uid); await update.message.reply_text("Too short.",reply_markup=naming_prompt_kb()); return
    s["nickname"]=nick; clear_nickname_prompt(uid); save_players(players)
    await update.message.reply_text(f"✅ <b>{CHAMPS[s['species']]['display']}</b> is now <b>{html.escape(nick)}</b>!",reply_markup=main_menu_kb(uid),parse_mode="HTML")

async def nickname_text_reply(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message or not players[uid].get("_awaiting_nickname"): return
    raw=(update.message.text or "").strip(); nick=sanitize_nick(raw)
    if len(nick)<2: start_nickname_prompt(uid); await update.message.reply_text("Too short.",reply_markup=naming_prompt_kb()); return
    s=get_active_suimon(uid)
    if s: s["nickname"]=nick; clear_nickname_prompt(uid); save_players(players); await update.message.reply_text(f"✅ Named <b>{html.escape(nick)}</b>!",reply_markup=main_menu_kb(uid),parse_mode="HTML")

async def profile(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(uid): await update.message.reply_text(nickname_required_text(uid),reply_markup=naming_prompt_kb(),parse_mode="HTML"); return
    if not update.message: return
    s=get_active_suimon(uid)
    if not s: await update.message.reply_text("No champ yet.",reply_markup=main_menu_kb(uid)); return
    p=players[uid]; cd=CHAMPS[s["species"]]; lv=int(s.get("level",1)); st=get_stats(s["species"],lv); chp=s.get("hp",st["hp"])
    w=int(s.get("wins",0)); lo=int(s.get("losses",0)); balls=int(p.get("suiballs",0)); nballs=int(p.get("net_balls",0))
    badges=get_badges_display(uid); fainted=" (FAINTED)" if chp<=0 else ""
    txt=f"🪪 <b>Trainer Card</b>\n\n👤 {display_name(uid)}\n🏅 Record: {w}W / {lo}L\n"
    if badges: txt+=f"🎖️ Badges: {badges}\n"
    txt+=f"\n{TYPE_EMOJI[cd['type']]} {suimon_full_name(s)} (Lv.{lv}){fainted}\n❤️ HP: {chp}/{st['hp']}\n✨ XP: {s.get('xp',0)}/{xp_needed(lv) if lv<MAX_LEVEL else 0}\n📈 Stats: ATK {st['atk']} | DEF {st['def']} | SPD {st['spd']}\n\n🎒 Suiballs: {balls} | 🥅 Net Balls: {nballs}\n📦 Team: {len(get_owned_suimon_list(uid))} Suimon"
    tl=[]
    for i,su in enumerate(get_owned_suimon_list(uid)):
        act="⭐" if i==get_active_suimon_index(uid) else "  "
        hp=su.get("hp",0); mx=get_stats(su["species"],int(su.get("level",1)))["hp"]
        tl.append(f"{act} {suimon_full_name(su)} Lv.{su.get('level',1)} HP {hp}/{mx}")
    txt+="\n\n<b>Your Suimon:</b>\n"+"\n".join(tl)
    await update.message.reply_text(txt,reply_markup=main_menu_kb(uid),parse_mode="HTML")

async def leaderboard(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message: return
    rankings_image = resolve_rankings_image_path()
    rankings_text = build_rankings_text(uid, 10)
    if rankings_image:
        with open(rankings_image, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=rankings_text, reply_markup=main_menu_kb(uid), parse_mode="HTML")
    else:
        await update.message.reply_text(rankings_text, reply_markup=main_menu_kb(uid), parse_mode="HTML", disable_web_page_preview=True)

async def inventory(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message: return
    p=players[uid]; balls=int(p.get("suiballs",0)); nballs=int(p.get("net_balls",0))
    tl=[]
    for i,s in enumerate(get_owned_suimon_list(uid)):
        act="⭐" if i==get_active_suimon_index(uid) else "  "
        hp=s.get("hp",0); mx=get_stats(s["species"],int(s.get("level",1)))["hp"]
        tl.append(f"{act} {suimon_full_name(s)} Lv.{s.get('level',1)} HP {hp}/{mx}")
    await update.message.reply_text(f"🎒 <b>Inventory</b>\n\n🧿 Suiballs: <b>{balls}</b> (daily +{get_daily_suiballs()})\n🥅 Net Balls: <b>{nballs}</b> (daily +{DAILY_NETBALLS})\n\n📦 <b>Team:</b>\n"+"\n".join(tl if tl else ["No Suimon."]),reply_markup=main_menu_kb(uid),parse_mode="HTML")

async def heal(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message: return
    its=get_owned_suimon_list(uid)
    if not its: await update.message.reply_text("No Suimon.",reply_markup=main_menu_kb(uid)); return
    balls=int(players[uid].get("suiballs",0))
    if balls<=0: await update.message.reply_text(f"❌ No Suiballs.",reply_markup=main_menu_kb(uid)); return
    kb=[]
    for i,s in enumerate(its):
        ch=s.get("hp",0); mx=get_stats(s["species"],int(s.get("level",1)))["hp"]
        st="✅" if ch>=mx else "❤️‍🩹"
        kb.append([InlineKeyboardButton(f"{st} {suimon_full_name(s)} ({ch}/{mx})",callback_data=f"heal_select|{i}")])
    kb.append([InlineKeyboardButton("⬅️ Back",callback_data="menu|home")])
    await update.message.reply_text("🏥 <b>Health Center</b>\nSelect a Suimon to heal (1 Suiball):",reply_markup=InlineKeyboardMarkup(kb),parse_mode="HTML")

async def heal_select_callback(update, context):
    q = update.callback_query
    if not q: return
    await q.answer()
    uid = str(q.from_user.id)
    global players
    players = load_players()
    ensure_player(uid, q.from_user.first_name or "", q.from_user.username)
    ensure_daily(uid)
    parts = q.data.split("|")
    if len(parts) < 2: return
    idx = int(parts[1])
    its = get_owned_suimon_list(uid)
    if idx < 0 or idx >= len(its):
        await edit_menu_message(q, "Invalid selection.", main_menu_kb(uid))
        return
    s = its[idx]
    mx = get_stats(s["species"], int(s.get("level", 1)))["hp"]
    if s.get("hp", 0) >= mx:
        await edit_menu_message(q, "Already full HP.", main_menu_kb(uid))
        return
    balls = int(players[uid].get("suiballs", 0))
    if balls <= 0:
        await edit_menu_message(q, "❌ No Suiballs.", main_menu_kb(uid))
        return
    players[uid]["suiballs"] = balls - 1
    heal_suimon_by_index(uid, idx)
    save_players(players)
    await edit_menu_message(q, f"🧿 <b>{suimon_full_name(s)}</b> healed to full HP ({mx}/{mx})!\nRemaining Suiballs: {players[uid]['suiballs']}", main_menu_kb(uid))

async def cutforsuimon(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message: return
    p=players[uid]; t=td()
    if p.get("last_cut")==t: await update.message.reply_text("🩸 Already cut today.",reply_markup=main_menu_kb(uid)); return
    p["suiballs"]=min(get_suiball_cap(),int(p.get("suiballs",0))+1); p["last_cut"]=t; save_players(players)
    await update.message.reply_text("🩸 +1 Suiball!",reply_markup=main_menu_kb(uid))

# ---------- EXPLORE ----------
async def explore(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if not update.message: return
    if not get_active_suimon(uid):
        await update.message.reply_text("❌ Need a Suimon.",reply_markup=main_menu_kb(uid))
        return
    kb=[]
    for k,w in WORLDS.items():
        last=players[uid].get(f"explore_{k}_date"); cd=last==td()
        kb.append([InlineKeyboardButton(f"{w['emoji']} {w['name']} {'✅' if cd else '🕒'}",callback_data=f"explore_world|{k}")])
    kb.append([InlineKeyboardButton("⬅️ Back",callback_data="menu|home")])
    caption = "🌍 <b>Choose a world to explore:</b>\n(Each world once per day)"
    img = resolve_explore_image_path()
    if img:
        with open(img, "rb") as f:
            await update.message.reply_photo(photo=f, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    else:
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def explore_world_callback(update, context):
    q = update.callback_query
    if not q: return
    await q.answer()
    uid = str(q.from_user.id)
    ensure_player(uid, q.from_user.first_name or "", q.from_user.username)
    ensure_daily(uid)
    parts = q.data.split("|")
    if len(parts) < 2: return
    wk = parts[1]
    w = WORLDS.get(wk)
    if not w:
        await edit_menu_message(q, "World not found.", main_menu_kb(uid))
        return
    p = players[uid]
    ck = f"explore_{wk}_date"
    if p.get(ck) == td():
        await edit_menu_message(q, f"⏳ Already explored {w['name']} today.", main_menu_kb(uid))
        return

    bot = context.bot
    chat_id = q.message.chat.id
    nm = html.escape(display_name(uid))

    flavor_texts = {
        "sedative_abyss": [f"{nm} dives into the dark ocean trenches...", "The water feels heavy, almost tranquilizing...", "Searching through the abyss..."],
        "crackspit_peaks": [f"{nm} climbs the volcanic mountains...", "The lava flows like a crack pipe, fumes everywhere...", "Looking around the peaks..."],
        "hash_highlands": [f"{nm} wanders through the rolling hills...", "Ancient cannabis fields stretch endlessly...", "Sniffing the air for something interesting..."]
    }

    texts = flavor_texts.get(wk, [f"{nm} explores...", "Searching...", "..."])
    status_msg = await bot.send_message(chat_id, texts[0])
    for txt in texts[1:]:
        await asyncio.sleep(1.2)
        try: await status_msg.edit_text(txt)
        except: pass

    await asyncio.sleep(0.8)
    if random.random() < w["encounter_chance"]:
        ws = random.choice(w["suimon"])
        wd = CHAMPS[ws]
        try: await status_msg.edit_text(f"{w['emoji']} A wild <b>{wd['display']}</b> appeared!\nType: {TYPE_EMOJI[wd['type']]}\n\nCatch it? (1 Net Ball, 50%)", parse_mode="HTML")
        except: pass
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Catch", callback_data=f"catch|{wk}|{ws}"),
             InlineKeyboardButton("🏃 Flee", callback_data=f"explore_flee|{wk}")]
        ])
        try: await status_msg.edit_reply_markup(reply_markup=kb)
        except: pass
    else:
        p[ck] = td()
        save_players(players)
        no_texts = ["Didn't find anything... too stoned!", "Nothing here but wasted time.", "Checked everywhere, but it's empty."]
        try: await status_msg.edit_text(f"{w['emoji']} {random.choice(no_texts)}", parse_mode="HTML")
        except: pass
        try: await status_msg.edit_reply_markup(reply_markup=main_menu_kb(uid))
        except: pass

async def catch_callback(update,context):
    q=update.callback_query
    if not q: return
    await q.answer()
    uid=str(q.from_user.id); p=players.setdefault(uid,{})
    _,wk,ws=q.data.split("|"); w=WORLDS.get(wk); ck=f"explore_{wk}_date"
    if p.get(ck)==td():
        await edit_menu_message(q, "Already completed today.", main_menu_kb(uid))
        return
    nb=int(p.get("net_balls",0))
    if nb<=0:
        await edit_menu_message(q, "❌ No Net Balls!", main_menu_kb(uid))
        return
    p["net_balls"]=nb-1; p[ck]=td()
    if random.random()<0.5:
        p.setdefault("owned_suimon",[]).append({"species":ws,"nickname":None,"level":1,"xp":0,"hp":get_stats(ws,1)["hp"],"wins":0,"losses":0})
        p["active_suimon"]=len(p["owned_suimon"])-1
        save_players(players)
        start_nickname_prompt(uid)
        await q.edit_message_text(f"🎉 <b>{CHAMPS[ws]['display']}</b> caught! Added to your team.\n\nUse <code>/name YourName</code> to give it a nickname.", parse_mode="HTML", reply_markup=naming_prompt_kb())
    else:
        save_players(players)
        await q.edit_message_text(f"💨 The wild <b>{CHAMPS[ws]['display']}</b> escaped! Better luck next time.", parse_mode="HTML", reply_markup=main_menu_kb(uid))

async def explore_flee_callback(update,context):
    q=update.callback_query
    if not q: return
    await q.answer()
    uid=str(q.from_user.id)
    wk=q.data.split("|")[1]
    players[uid][f"explore_{wk}_date"]=td()
    save_players(players)
    await q.edit_message_text("🏃 You fled. World complete for today.", reply_markup=main_menu_kb(uid))

# ---------- PVP ----------
async def fight(update,context):
    if not await ensure_allowed_chat(update,context): return
    uid=await _bootstrap_user(update)
    if update.message and needs_nickname_prompt(uid): await update.message.reply_text(nickname_required_text(uid),reply_markup=naming_prompt_kb(),parse_mode="HTML"); return
    chat=update.effective_chat
    if not chat or not update.message: return
    cid=int(chat.id)
    if not get_active_suimon(uid): await update.message.reply_text("⚠️ Need a named Suimon.",reply_markup=main_menu_kb(uid)); return
    eligible=[u for u in _eligible_players_in_chat(cid) if u!=uid]
    if not eligible: await update.message.reply_text("No opponents.",reply_markup=main_menu_kb(uid)); return
    target=_parse_target_user_id(update,context)
    if len(eligible)==1: target=eligible[0]
    elif not target or target not in eligible: await update.message.reply_text("⚔️ Multiple opponents. Reply or use /fight @Name.",reply_markup=main_menu_kb(uid)); return
    now=time.monotonic()
    for k in list(PENDING_CHALLENGES.keys()):
        if k[0]==cid and PENDING_CHALLENGES[k].get("from")==uid and now-PENDING_CHALLENGES[k].get("ts_mono",0)>CHALLENGE_TIMEOUT: PENDING_CHALLENGES.pop(k,None)
    if PENDING_CHALLENGES.get((cid,target)) and now-PENDING_CHALLENGES[(cid,target)].get("ts_mono",0)<CHALLENGE_TIMEOUT:
        await update.message.reply_text(f"⏳ {html.escape(display_name(target))} already has a pending challenge.",reply_markup=main_menu_kb(uid),parse_mode="HTML"); return
    PENDING_CHALLENGES[(cid,target)]={"from":uid,"ts":datetime.now(TZ).isoformat(),"ts_mono":now}
    cn=display_name(uid); tn=display_name(target)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Accept",callback_data=f"suimon_accept|{uid}|{target}"),InlineKeyboardButton("❌ Decline",callback_data=f"suimon_decline|{uid}|{target}")]])
    sm=await update.message.reply_text(f"⚔️ <b>{html.escape(cn)}</b> challenges <b>{html.escape(tn)}</b>!\n\n<b>{html.escape(tn)}</b>, accept?\n⏳ {CHALLENGE_TIMEOUT}s.",reply_markup=kb,parse_mode="HTML")
    async def exp():
        await asyncio.sleep(CHALLENGE_TIMEOUT)
        if PENDING_CHALLENGES.get((cid,target),{}).get("from")==uid:
            PENDING_CHALLENGES.pop((cid,target),None)
            try: await sm.edit_text(f"⏰ Challenge expired!",reply_markup=None,parse_mode="HTML")
            except: pass
    asyncio.create_task(exp())

async def challenge_callback(update,context):
    if not await ensure_allowed_chat(update,context): return
    q=update.callback_query
    if not q or not q.message: return
    await q.answer()
    act, chal, tgt = q.data.split("|")
    cid=int(q.message.chat.id); clicker=str(q.from_user.id)
    if clicker!=tgt: await q.answer("Not for you.",show_alert=True); return
    payload=PENDING_CHALLENGES.get((cid,clicker))
    if not payload or time.monotonic()-payload.get("ts_mono",0)>CHALLENGE_TIMEOUT:
        await edit_menu_message(q,"Expired.",main_menu_kb(clicker)); return
    if str(payload.get("from"))!=chal:
        await edit_menu_message(q,"Mismatch.",main_menu_kb(clicker)); return
    PENDING_CHALLENGES.pop((cid,clicker),None)
    if act.startswith("suimon_decline"):
        await edit_menu_message(q,"❌ Declined.",main_menu_kb(clicker)); return
    await edit_menu_message(q,"✅ Accepted! Challenger, choose your Suimon first...",main_menu_kb(clicker))
    PENDING_SELECTION[cid]={"challenger":chal,"opponent":clicker,"challenger_suimon":None,"opponent_suimon":None}
    its=get_owned_suimon_list(chal); kb=[]
    for i,s in enumerate(its):
        fnt="💀" if s["hp"]<=0 else ""
        kb.append([InlineKeyboardButton(f"{suimon_full_name(s)} Lv.{s['level']} ({s['hp']}/{get_stats(s['species'],s['level'])['hp']}) {fnt}",callback_data=f"select_suimon|challenger|{i}")])
    try: await q.message.reply_text(f"🎯 <b>{html.escape(display_name(chal))}</b>, choose your Suimon:",reply_markup=InlineKeyboardMarkup(kb),parse_mode="HTML")
    except: pass

async def select_suimon_callback(update,context):
    q=update.callback_query
    if not q: return
    await q.answer(); uid=str(q.from_user.id); _,role,idx=q.data.split("|"); idx=int(idx); cid=int(q.message.chat.id)
    sel=PENDING_SELECTION.get(cid)
    if not sel: await q.edit_message_text("Expired."); return
    if (role=="challenger" and uid!=sel["challenger"]) or (role=="opponent" and uid!=sel["opponent"]): await q.answer("Not your selection.",show_alert=True); return
    its=get_owned_suimon_list(uid)
    if idx<0 or idx>=len(its): await q.answer("Invalid."); return
    if its[idx]["hp"]<=0: await q.answer("Fainted! Choose another.",show_alert=True); return
    sel[f"{role}_suimon"]=idx
    if role=="challenger":
        opp=sel["opponent"]; its2=get_owned_suimon_list(opp); kb=[]
        for i,s in enumerate(its2):
            fnt="💀" if s["hp"]<=0 else ""
            kb.append([InlineKeyboardButton(f"{suimon_full_name(s)} Lv.{s['level']} ({s['hp']}/{get_stats(s['species'],s['level'])['hp']}) {fnt}",callback_data=f"select_suimon|opponent|{i}")])
        await q.edit_message_text(f"✅ Challenger selected {suimon_full_name(its[idx])}!\n\n🎯 <b>{html.escape(display_name(opp))}</b>, choose:",reply_markup=InlineKeyboardMarkup(kb),parse_mode="HTML")
    else:
        await q.edit_message_text("✅ Both selected! Battle starting...")
        await _start_battle_with_suimon(cid,sel,context)

async def _start_battle_with_suimon(cid,sel,context):
    global players; players=load_players()
    u=sel["challenger"]; o=sel["opponent"]; ui=sel["challenger_suimon"]; oi=sel["opponent_suimon"]
    if cid in ACTIVE_BATTLES: await context.bot.send_message(cid,"⚠️ Battle already running."); return
    us=players[u]["owned_suimon"][ui]; os_=players[o]["owned_suimon"][oi]
    if us["hp"]<=0 or os_["hp"]<=0: await context.bot.send_message(cid,"❌ Fainted Suimon."); return
    ACTIVE_BATTLES.add(cid); msg=await context.bot.send_message(cid,"⚔️ BATTLE START (loading...)"); mid=msg.message_id
    c1k=us["species"]; c2k=os_["species"]; lv1=int(us["level"]); lv2=int(os_["level"]); s1=get_stats(c1k,lv1); s2=get_stats(c2k,lv2)
    c1={"hp":int(us["hp"]),"max_hp":s1["hp"],"atk":s1["atk"],"def":s1["def"],"spd":s1["spd"],"burn_turns":0,"sleep_turns":0,"confuse_turns":0,"poison_turns":0,"wet_dream_turns":0,"wet_dream_uses_left":2 if c1k=="suimander" else 0,"has_slept":False,"last_used_sleep":False,"stun_turns":0}
    c2={"hp":int(os_["hp"]),"max_hp":s2["hp"],"atk":s2["atk"],"def":s2["def"],"spd":s2["spd"],"burn_turns":0,"sleep_turns":0,"confuse_turns":0,"poison_turns":0,"wet_dream_turns":0,"wet_dream_uses_left":2 if c2k=="suimander" else 0,"has_slept":False,"last_used_sleep":False,"stun_turns":0}
    p1=display_name(u); p2=display_name(o)
    state={"message_id":mid,"log_lines":[],"last_reposition":0.0,"reposition_cooldown":REPOSITION_COOLDOWN,"last_rendered_text":"","last_reply_markup":None,"resolving":False,"resolving_since":0.0,"user":u,"opponent":o,"u_idx":ui,"o_idx":oi,"p1_name":p1,"p2_name":p2,"c1_key":c1k,"c2_key":c2k,"lv1":lv1,"lv2":lv2,"champ1":c1,"champ2":c2,"c1_label":f"{p1} - {suimon_full_name(us)} (Lv.{lv1})","c2_label":f"{p2} - {suimon_full_name(os_)} (Lv.{lv2})","turn":0,"round":0,"actions":0,"max_rounds":24,"suiballs_used":{},"last_move_ts":time.monotonic()}
    BATTLES[cid]=state
    await _battle_push_message(cid,state,context,"⚔️ BATTLE START ⚔️",delay=0.25,force_reposition=True)
    await _battle_push_message(cid,state,context,f"👤 {p1} sends out {suimon_full_name(us)}!",delay=0.30)
    await _battle_push_message(cid,state,context,f"👤 {p2} sends out {suimon_full_name(os_)}!",delay=0.30)
    await _battle_push_hud(cid,state,context,delay=0.30)
    for t in ("3…","2…","1…","GO!"): await _battle_push_message(cid,state,context,t,delay=COUNTDOWN_STEP_DELAY)
    first=pick_first_attacker(int(c1["spd"]),int(c2["spd"])); state["turn"]=first
    sn=suimon_full_name(us) if first==0 else suimon_full_name(os_)
    await _battle_push_message(cid,state,context,f"🏁 {sn} moves first!",delay=0.35)
    await _battle_prompt_turn(cid,state,context)

# ---------- ADMIN ----------
async def change_champ(update,context):
    if not await ensure_allowed_chat(update,context): return
    adm=await _bootstrap_user(update)
    if not update.message or not update.effective_chat: return
    if not await is_privileged_user(context.bot,int(update.effective_chat.id),int(adm)): await update.message.reply_text("❌ Only privileged users."); return
    target=_parse_target_user_id(update,context)
    if not target or target not in players: await update.message.reply_text("Player not found."); return
    if not context.args or len(context.args)<1: await update.message.reply_text("Usage: /changechamp @user champname"); return
    nc=ck_input(context.args[-1])
    if not nc: await update.message.reply_text("Unknown champ."); return
    its=players[target].setdefault("owned_suimon",[])
    if its: active=get_active_suimon_index(target); its[active]["species"]=nc; its[active]["hp"]=get_stats(nc,int(its[active].get("level",1)))["hp"]
    else: its.append({"species":nc,"nickname":None,"level":1,"xp":0,"hp":get_stats(nc,1)["hp"],"wins":0,"losses":0})
    save_players(players); await update.message.reply_text(f"✅ {display_name(target)}'s active Suimon changed.")

async def tournamenton(update,context):
    if not await ensure_allowed_chat(update,context): return
    adm=await _bootstrap_user(update)
    if not update.message or not update.effective_chat or not await is_privileged_user(context.bot,int(update.effective_chat.id),int(adm)): await update.message.reply_text("❌ Only privileged."); return
    tournament_state["active"]=True; save_tournament(tournament_state)
    for uid in players: players[uid]["suiballs"]=100
    save_players(players); await update.message.reply_text("🏆 TOURNAMENT STARTED! Everyone gets 100 Suiballs.",parse_mode="HTML")

async def tournamentoff(update,context):
    if not await ensure_allowed_chat(update,context): return
    adm=await _bootstrap_user(update)
    if not update.message or not update.effective_chat or not await is_privileged_user(context.bot,int(update.effective_chat.id),int(adm)): await update.message.reply_text("❌ Only privileged."); return
    tournament_state["active"]=False; save_tournament(tournament_state)
    top=get_leaderboard(10)
    if top:
        wid=top[0][0]; players[wid].setdefault("badges",[]).append("earth"); save_players(players)
        await update.message.reply_text(f"🏁 Winner: {display_name(wid)} gets Earth Badge! 🌍",parse_mode="HTML")
    else: await update.message.reply_text("Tournament ended. No players.")

async def xpboost(update,context):
    if not await ensure_allowed_chat(update,context): return
    adm=await _bootstrap_user(update)
    if not await is_privileged_user(context.bot,int(update.effective_chat.id),int(adm)): await update.message.reply_text("❌ Only privileged."); return
    tournament_state["xp_boost_expires"]=time.time()+7200; save_tournament(tournament_state)
    await update.message.reply_text("⚡ XP BOOST 2h!")

async def endfight(update,context):
    if not await ensure_allowed_chat(update,context): return
    adm=await _bootstrap_user(update)
    if not await is_privileged_user(context.bot,int(update.effective_chat.id),int(adm)): await update.message.reply_text("❌ Only privileged."); return
    state=BATTLES.get(int(update.effective_chat.id))
    if not state: await update.message.reply_text("No active battle."); return
    wid=state["user"]
    if context.args:
        t,_=_parse_target_from_args(int(update.effective_chat.id),context.args)
        if t in (state["user"],state["opponent"]): wid=t
    lid=state["opponent"] if wid==state["user"] else state["user"]
    await _end_battle(int(update.effective_chat.id),state,context,winner=wid,loser=lid)
    await update.message.reply_text(f"🛑 Ended. Winner: {display_name(wid)}")

async def give_suiball(update,context):
    if not await ensure_allowed_chat(update,context): return
    giver=await _bootstrap_user(update)
    if not update.message or not update.effective_chat or not await is_privileged_user(context.bot,int(update.effective_chat.id),int(giver)): await update.message.reply_text("❌ Only privileged."); return
    t,amt=_parse_target_and_amount(int(update.effective_chat.id),context.args)
    if not t or amt is None or amt<=0: await update.message.reply_text("Usage: /givesuiball @user amount"); return
    players[t]["suiballs"]=min(999,int(players.get(t,{}).get("suiballs",0))+amt); save_players(players)
    await update.message.reply_text(f"✅ Gave {amt} Suiballs to {display_name(t)}.")

async def remove_suiball(update,context):
    if not await ensure_allowed_chat(update,context): return
    giver=await _bootstrap_user(update)
    if not update.message or not update.effective_chat or not await is_privileged_user(context.bot,int(update.effective_chat.id),int(giver)): await update.message.reply_text("❌ Only privileged."); return
    t,amt=_parse_target_and_amount(int(update.effective_chat.id),context.args)
    if not t or amt is None or amt<=0: await update.message.reply_text("Usage: /takesuiball @user amount"); return
    players[t]["suiballs"]=max(0,int(players.get(t,{}).get("suiballs",0))-amt); save_players(players)
    await update.message.reply_text(f"✅ Removed {amt} Suiballs from {display_name(t)}.")

PENDING_RESETS = {}
async def reset_leaderboard(update,context):
    if not await ensure_allowed_chat(update,context): return
    caller=await _bootstrap_user(update)
    if not update.message or not update.effective_chat or not await is_privileged_user(context.bot,int(update.effective_chat.id),int(caller)): await update.message.reply_text("❌ Only privileged."); return    now=time.monotonic()
    if PENDING_RESETS.get(caller) and now-PENDING_RESETS[caller]<30:
        PENDING_RESETS.pop(caller,None)
        for uid,p in players.items():
            for s in p.get("owned_suimon",[]): s["level"]=1; s["xp"]=0; s["wins"]=0; s["losses"]=0; s["hp"]=get_stats(s["species"],1)["hp"]
            p["suiballs"]=DAILY_SUIBALLS; p["wins"]=0; p["losses"]=0
        save_players(players); await update.message.reply_text("♻️ Reset complete.")
    else: PENDING_RESETS[caller]=now; await update.message.reply_text("Type /resetleaderboard again within 30s.")

# ---------- MENU CALLBACKS ----------
async def menu_callback(update,context):
    if not await ensure_allowed_chat(update,context): return
    q=update.callback_query
    if not q or not q.data: return
    await q.answer()
    uid=str(q.from_user.id); ensure_player(uid,(q.from_user.first_name or "Player").strip(),q.from_user.username)
    if q.message: _remember_chat(uid,int(q.message.chat.id))
    ensure_daily(uid); save_players(players)
    action=q.data.split("|",1)[1] if "|" in q.data else "home"

    if action=="profile":
        s=get_active_suimon(uid)
        if not s: await edit_menu_message(q,"No Suimon yet.",main_menu_kb(uid)); return
        p=players[uid]; cd=CHAMPS[s["species"]]; lv=int(s.get("level",1)); st=get_stats(s["species"],lv); chp=s.get("hp",st["hp"])
        w=int(s.get("wins",0)); lo=int(s.get("losses",0)); balls=int(p.get("suiballs",0)); nballs=int(p.get("net_balls",0))
        badges=get_badges_display(uid); fainted=" (FAINTED)" if chp<=0 else ""
        txt=f"🪪 <b>Trainer Card</b>\n\n👤 {display_name(uid)}\n🏅 Record: {w}W / {lo}L\n"
        if badges: txt+=f"🎖️ Badges: {badges}\n"
        txt+=f"\n{TYPE_EMOJI[cd['type']]} {suimon_full_name(s)} (Lv.{lv}){fainted}\n❤️ HP: {chp}/{st['hp']}\n✨ XP: {s.get('xp',0)}/{xp_needed(lv) if lv<MAX_LEVEL else 0}\n📈 Stats: ATK {st['atk']} | DEF {st['def']} | SPD {st['spd']}\n\n🎒 Suiballs: {balls} | 🥅 Net Balls: {nballs}\n📦 Team: {len(get_owned_suimon_list(uid))} Suimon"
        tl=[]
        for i,su in enumerate(get_owned_suimon_list(uid)):
            act="⭐" if i==get_active_suimon_index(uid) else "  "
            hp=su.get("hp",0); mx=get_stats(su["species"],int(su.get("level",1)))["hp"]
            tl.append(f"{act} {suimon_full_name(su)} Lv.{su.get('level',1)} HP {hp}/{mx}")
        txt+="\n\n<b>Your Suimon:</b>\n"+"\n".join(tl)
        await edit_menu_message(q,txt,main_menu_kb(uid)); return
    if action=="leaderboard":
        await q.answer()
        rankings_image = resolve_rankings_image_path()
        rankings_text = build_rankings_text(uid, 10)
        if rankings_image:
            with open(rankings_image, "rb") as photo:
                await context.bot.send_photo(chat_id=q.message.chat.id, photo=photo, caption=rankings_text, reply_markup=main_menu_kb(uid), parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=q.message.chat.id, text=rankings_text, reply_markup=main_menu_kb(uid), parse_mode="HTML", disable_web_page_preview=True)
        return
    if action=="inventory":
        p=players[uid]; balls=int(p.get("suiballs",0)); net=int(p.get("net_balls",0))
        await edit_menu_message(q,f"🎒 Inventory\n🧿 Suiballs: {balls}\n🥅 Net Balls: {net}",main_menu_kb(uid)); return
    if action=="heal":
        its=get_owned_suimon_list(uid)
        if not its: await edit_menu_message(q,"No Suimon.",main_menu_kb(uid)); return
        balls=int(players[uid].get("suiballs",0))
        if balls<=0: await edit_menu_message(q,f"❌ No Suiballs.",main_menu_kb(uid)); return
        kb=[]
        for i,s in enumerate(its):
            ch=s.get("hp",0); mx=get_stats(s["species"],int(s.get("level",1)))["hp"]
            st="✅" if ch>=mx else "❤️‍🩹"
            kb.append([InlineKeyboardButton(f"{st} {suimon_full_name(s)} ({ch}/{mx})",callback_data=f"heal_select|{i}")])
        kb.append([InlineKeyboardButton("⬅️ Back",callback_data="menu|home")])
        await edit_menu_message(q,"🏥 <b>Health Center</b>\nSelect a Suimon to heal (1 Suiball):",InlineKeyboardMarkup(kb)); return
    if action=="explore":
        await q.answer()
        if not get_active_suimon(uid):
            await edit_menu_message(q, "❌ Need a Suimon.", main_menu_kb(uid))
            return
        kb=[]
        for k,w in WORLDS.items():
            last=players[uid].get(f"explore_{k}_date"); cd=last==td()
            kb.append([InlineKeyboardButton(f"{w['emoji']} {w['name']} {'✅' if cd else '🕒'}",callback_data=f"explore_world|{k}")])
        kb.append([InlineKeyboardButton("⬅️ Back",callback_data="menu|home")])
        caption = "🌍 <b>Choose a world to explore:</b>\n(Each world once per day)"
        img = resolve_explore_image_path()
        if img:
            with open(img, "rb") as f:
                await context.bot.send_photo(chat_id=q.message.chat.id, photo=f, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=q.message.chat.id, text=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        return
    if action=="champs":
        lines=["📜 Starter Champs",""]
        for k in ["basaurimon","suimander","suiqrtle"]:
            c=CHAMPS[k]; moves=", ".join(m["name"] for m in c["moves"])
            lines.append(f"{TYPE_EMOJI[c['type']]} {c['display']} — {c['type']}\n   Moves: {moves}\n")
        await edit_menu_message(q,"🌟 Choose your starter\n\n"+"\n".join(lines),choose_champ_kb()); return
    if action=="fight": await edit_menu_message(q,"⚔️ Use /fight @username to challenge someone.",main_menu_kb(uid)); return
    await edit_menu_message(q,fancy_menu_caption(uid),main_menu_kb(uid))

async def choose_callback(update,context):
    if not await ensure_allowed_chat(update,context): return
    q=update.callback_query
    if not q: return
    await q.answer()
    uid=await _bootstrap_user(update); ck=q.data.split("|",1)[1].strip()
    if ck not in ("basaurimon","suimander","suiqrtle"): await edit_menu_message(q,"Unknown champ.",main_menu_kb(uid)); return
    if get_owned_suimon_list(uid): await edit_menu_message(q,"Already have a starter.",main_menu_kb(uid)); return
    c=CHAMPS[ck]; players[uid]["owned_suimon"]=[{"species":ck,"nickname":None,"level":1,"xp":0,"hp":get_stats(ck,1)["hp"],"wins":0,"losses":0}]
    players[uid]["active_suimon"]=0; players[uid]["suiballs"]=max(int(players[uid].get("suiballs",0)),1)
    start_nickname_prompt(uid); save_players(players)
    await edit_menu_message(q,f"📝 Selected {c['display']}!\nUse /name YourName.",naming_prompt_kb())

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("menu",menu))
    app.add_handler(CommandHandler("intro",intro))
    app.add_handler(CommandHandler("champs",champs_cmd))
    app.add_handler(CommandHandler("choose",choose))
    app.add_handler(CommandHandler("profile",profile))
    app.add_handler(CommandHandler("name",nickname))
    app.add_handler(CommandHandler("nickname",nickname))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,nickname_text_reply))
    app.add_handler(CommandHandler(["rankings","leaderboard"],leaderboard))
    app.add_handler(CommandHandler("inventory",inventory))
    app.add_handler(CommandHandler("heal",heal))
    app.add_handler(CommandHandler("explore",explore))
    app.add_handler(CommandHandler("cutforsuimon",cutforsuimon))
    app.add_handler(CommandHandler("givesuiball",give_suiball))
    app.add_handler(CommandHandler("takesuiball",remove_suiball))
    app.add_handler(CommandHandler("resetleaderboard",reset_leaderboard))
    app.add_handler(CommandHandler("tournamenton",tournamenton))
    app.add_handler(CommandHandler("tournamentoff",tournamentoff))
    app.add_handler(CommandHandler("changechamp",change_champ))
    app.add_handler(CommandHandler("xpboost",xpboost))
    app.add_handler(CommandHandler("endfight",endfight))
    app.add_handler(CommandHandler("fight",fight))

    app.add_handler(CallbackQueryHandler(heal_select_callback, pattern=r"^heal_select\|"))
    app.add_handler(CallbackQueryHandler(explore_world_callback, pattern=r"^explore_world\|"))
    app.add_handler(CallbackQueryHandler(catch_callback, pattern=r"^catch\|"))
    app.add_handler(CallbackQueryHandler(explore_flee_callback, pattern=r"^explore_flee\|"))
    app.add_handler(CallbackQueryHandler(select_suimon_callback, pattern=r"^select_suimon\|"))
    app.add_handler(CallbackQueryHandler(challenge_callback, pattern=r"^suimon_(accept|decline)\|"))
    app.add_handler(CallbackQueryHandler(battle_move_callback, pattern=r"^(mv|ff|battle_heal|noop)\|"))
    app.add_handler(CallbackQueryHandler(choose_callback, pattern=r"^choose\|"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu(?:\||$)"))

    async def _afk_loop(application):
        while True:
            await asyncio.sleep(30)
            try: await _afk_watcher(application)
            except Exception as e: print(f"[AFK] {e}")

    async def post_init(application): asyncio.create_task(_afk_loop(application))
    app.post_init = post_init

    print("Suimon Arena bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()