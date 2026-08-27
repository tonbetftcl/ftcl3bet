import asyncio
import html
import json
import logging
import random
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ================= CONFIGURATION =================
BOT_TOKEN = "8774151987:AAGhhtt1gdWIvi07OWzGv2hBhGhQZ2jSh_0"      
BOT_USERNAME = "@ftcl3bet_bot"          

CHANNEL_ID = -1004329989649             
CHANNEL_URL = "https://t.me/ftcl3bet_log" 

CHANNEL_2_ID = -1003863595353          
CHANNEL_2_URL = "https://t.me/Ftcl3News"

ADMIN_IDS = [1866813859]                 
DB_NAME = "mifl_stake.db"

logging.basicConfig(level=logging.INFO)

# ================= DATABASE SETUP =================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('line_open', '1')")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 1000.0,
        is_banned INTEGER DEFAULT 0,
        last_bonus TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS team_stats (
        team_name TEXT PRIMARY KEY,
        games_played INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        draws INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        goals_scored INTEGER DEFAULT 0,
        goals_conceded INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        home_team TEXT,
        away_team TEXT,
        kef_p1 REAL,
        kef_x REAL,
        kef_p2 REAL,
        kef_tb REAL DEFAULT 1.85,
        kef_tm REAL DEFAULT 1.85,
        kef_oz_yes REAL DEFAULT 1.85,
        kef_oz_no REAL DEFAULT 1.85,
        kef_exact_score REAL DEFAULT 2.80,
        status TEXT DEFAULT 'OPEN',
        score_home INTEGER DEFAULT NULL,
        score_away INTEGER DEFAULT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        match_id INTEGER,
        outcome TEXT,
        kef REAL,
        amount REAL,
        status TEXT DEFAULT 'PENDING',
        payout REAL DEFAULT 0.0,
        channel_msg_id INTEGER DEFAULT NULL,
        original_text TEXT DEFAULT NULL,
        is_express INTEGER DEFAULT 0,
        express_details TEXT DEFAULT NULL,
        express_matches TEXT DEFAULT NULL
    )
    """)

    cursor.execute("PRAGMA table_info(bets)")
    b_cols = [c[1] for c in cursor.fetchall()]
    if "express_matches" not in b_cols:
        cursor.execute("ALTER TABLE bets ADD COLUMN express_matches TEXT DEFAULT NULL")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promo_codes (
        code TEXT PRIMARY KEY,
        reward REAL,
        max_uses INTEGER,
        current_uses INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS used_promos (
        user_id INTEGER,
        code TEXT,
        PRIMARY KEY (user_id, code)
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= HELPERS & LOGGING =================
def get_user_display_name(username: str | None, first_name: str | None = None, fallback_id: int | None = None) -> str:
    if username:
        clean = username.lstrip('@')
        return f"@{html.escape(clean)}"
    if first_name:
        return html.escape(first_name)
    return f"Игрок {fallback_id}" if fallback_id else "Игрок"

def log_action(user_id: int, action: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_logs (user_id, action) VALUES (?, ?)", (user_id, action))
    conn.commit()
    conn.close()

def is_line_open() -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'line_open'")
    res = cursor.fetchone()
    conn.close()
    return res[0] == "1" if res else True

def set_line_status(status: bool):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'line_open'", ("1" if status else "0",))
    conn.commit()
    conn.close()

def get_user(user_id: int, username: str = ""):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance, is_banned, last_bonus FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        clean_username = username.lstrip('@') if username else ""
        cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, clean_username))
        conn.commit()
        cursor.execute("SELECT user_id, username, balance, is_banned, last_bonus FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    else:
        if username and user[1] != username.lstrip('@'):
            cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username.lstrip('@'), user_id))
            conn.commit()
            user = (user[0], username.lstrip('@'), user[2], user[3], user[4])
    conn.close()
    return user

def update_balance(user_id: int, amount: float):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def set_balance(user_id: int, new_balance: float):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'line_open'", ("1",))
    cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    conn.commit()
    conn.close()

async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member1 = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        member2 = await bot.get_chat_member(chat_id=CHANNEL_2_ID, user_id=user_id)
        
        status1 = member1.status in ["creator", "administrator", "member"]
        status2 = member2.status in ["creator", "administrator", "member"]
        return status1 and status2
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return True

# --- ДИНАМИЧЕСКИЙ РАСЧЕТ КОЭФФИЦИЕНТОВ НА ОСНОВЕ СТАТИСТИКИ ---
def calculate_team_odds(home_team: str, away_team: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    def get_stats(team):
        cursor.execute("SELECT games_played, wins, goals_scored, goals_conceded FROM team_stats WHERE team_name = ?", (team,))
        res = cursor.fetchone()
        if not res or res[0] == 0:
            return {
                "factor": 1.0,
                "avg_scored": 1.25,
                "avg_conceded": 1.25,
                "games": 0
            }
        gp, w, gs, gc = res
        winrate = w / gp
        g_diff = gs - gc
        factor = 1.0 + (winrate - 0.5) * 0.4 + (g_diff * 0.02)
        return {
            "factor": max(0.5, min(1.5, factor)),
            "avg_scored": gs / gp,
            "avg_conceded": gc / gp,
            "games": gp
        }

    st_home = get_stats(home_team)
    st_away = get_stats(away_team)
    conn.close()

    f_home = st_home["factor"] * 1.05
    f_away = st_away["factor"]
    base_kef = 1.85
    kef_p1 = round(base_kef / f_home * f_away, 2)
    kef_p2 = round(base_kef / f_away * f_home, 2)
    kef_x = round(3.10 + abs(kef_p1 - kef_p2) * 0.3, 2)

    expected_goals = (st_home["avg_scored"] + st_away["avg_conceded"] + st_away["avg_scored"] + st_home["avg_conceded"]) / 2
    if st_home["games"] == 0 and st_away["games"] == 0:
        expected_goals = 2.5

    base_tb = 1.85
    kef_tb = round(base_tb * (2.5 / max(0.8, expected_goals)), 2)
    kef_tm = round(base_tb * (max(0.8, expected_goals) / 2.5), 2)

    prob_home_scores = min(0.9, max(0.1, st_home["avg_scored"] / (st_home["avg_scored"] + st_away["avg_conceded"] + 0.1) * 1.2))
    prob_away_scores = min(0.9, max(0.1, st_away["avg_scored"] / (st_away["avg_scored"] + st_home["avg_conceded"] + 0.1) * 1.2))
    both_score_prob = prob_home_scores * prob_away_scores

    if st_home["games"] == 0 and st_away["games"] == 0:
        both_score_prob = 0.50

    raw_oz_yes = round(1.0 / max(0.15, min(0.85, both_score_prob)), 2)
    raw_oz_no = round(1.0 / max(0.15, min(0.85, 1.0 - both_score_prob)), 2)

    kef_oz_yes = max(1.20, min(1.90, raw_oz_yes))
    kef_oz_no = max(1.80, min(2.45, raw_oz_no))

    return (
        max(1.05, kef_p1),
        max(2.10, kef_x),
        max(1.05, kef_p2),
        max(1.10, min(5.0, kef_tb)),
        max(1.10, min(5.0, kef_tm)),
        kef_oz_yes,
        kef_oz_no
    )

def recalculate_dynamic_odds(match_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT home_team, away_team FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        conn.close()
        return

    p1_b, x_b, p2_b, tb_b, tm_b, oz_y_b, oz_n_b = calculate_team_odds(match[0], match[1])

    cursor.execute("SELECT outcome, SUM(amount) FROM bets WHERE match_id = ? AND is_express = 0 GROUP BY outcome", (match_id,))
    pools = dict(cursor.fetchall())

    def adjust_kef(base_kef, outcome_key, factor=0.00005, min_val=1.05, max_val=5.0):
        staked = pools.get(outcome_key, 0)
        new_kef = base_kef / (1 + staked * factor)
        return max(min_val, min(max_val, round(new_kef, 2)))

    k_p1 = adjust_kef(p1_b, "P1")
    k_x = adjust_kef(x_b, "X")
    k_p2 = adjust_kef(p2_b, "P2")
    k_tb = adjust_kef(tb_b, "TB")
    k_tm = adjust_kef(tm_b, "TM")
    k_oz_yes = adjust_kef(oz_y_b, "OZ_YES", factor=0.00003, min_val=1.20, max_val=1.90)
    k_oz_no = adjust_kef(oz_n_b, "OZ_NO", factor=0.00003, min_val=1.80, max_val=2.45)

    cursor.execute("""
        UPDATE matches 
        SET kef_p1 = ?, kef_x = ?, kef_p2 = ?, kef_tb = ?, kef_tm = ?, kef_oz_yes = ?, kef_oz_no = ?
        WHERE id = ?
    """, (k_p1, k_x, k_p2, k_tb, k_tm, k_oz_yes, k_oz_no, match_id))

    conn.commit()
    conn.close()

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ УПРАВЛЕНИЯ КОМАНДАМИ =================
def get_all_teams():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT name FROM (
            SELECT team_name AS name FROM team_stats
            UNION
            SELECT home_team AS name FROM matches
            UNION
            SELECT away_team AS name FROM matches
        ) WHERE name IS NOT NULL AND name != '' ORDER BY name ASC
    """)
    teams = [r[0] for r in cursor.fetchall()]
    conn.close()
    return teams

def update_express_details_for_team(cursor, old_name: str, new_name: str):
    cursor.execute("SELECT id, express_details FROM bets WHERE is_express = 1 AND express_details LIKE ?", (f"%{old_name}%",))
    exp_bets = cursor.fetchall()
    for b_id, details in exp_bets:
        if details:
            new_details = details.replace(old_name, new_name)
            cursor.execute("UPDATE bets SET express_details = ? WHERE id = ?", (new_details, b_id))

def trigger_recalc_for_team(cursor, team_name: str):
    cursor.execute("SELECT id FROM matches WHERE status = 'OPEN' AND (home_team = ? OR away_team = ?)", (team_name, team_name))
    matches = cursor.fetchall()
    for m in matches:
        recalculate_dynamic_odds(m[0])

# ================= FSM STATES =================
class AdminStates(StatesGroup):
    add_match_teams = State()
    edit_kefs = State()
    edit_teams = State()
    finish_score = State()
    user_set_balance = State()
    user_add_balance = State()
    waiting_promo_name = State()
    waiting_promo_reward = State()
    waiting_promo_uses = State()
    waiting_broadcast_message = State()
    # Состояния команд
    rename_team_input = State()
    merge_teams_new_name = State()

class UserStates(StatesGroup):
    enter_bet_amount = State()
    enter_exact_score = State()
    enter_promo_code = State()
    express_pick_outcomes = State()
    express_enter_amount = State()

# ================= ROUTERS & MIDDLEWARE =================
router = Router()

@router.message.outer_middleware()
@router.callback_query.outer_middleware()
async def ban_check_middleware(handler, event, data):
    user_id = event.from_user.id
    user = get_user(user_id)
    if user[3] == 1:
        if isinstance(event, Message):
            await event.answer("❌ <b>Ваш аккаунт заблокирован администратором.</b>")
        elif isinstance(event, CallbackQuery):
            await event.answer("❌ Ваш аккаунт заблокирован!", show_alert=True)
        return
    return await handler(event, data)

# ================= KEYBOARDS =================
def sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Канал 1: Ставки & Логи", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="📢 Канал 2: Новости FTCL³", url=CHANNEL_2_URL)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")]
    ])

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚽ Линия матчей", callback_data="menu_line_type")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"), InlineKeyboardButton(text="📊 Топ Каперов", callback_data="menu_leaderboard")],
        [InlineKeyboardButton(text="📜 Мои ставки", callback_data="menu_my_bets"), InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="menu_bonus")],
        [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="menu_promo")]
    ])

def admin_main_kb():
    line_str = "❌ Закрыть Линию" if is_line_open() else "✅ Открыть Линию"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚽ Управление матчами", callback_data="admin_matches")],
        [InlineKeyboardButton(text="📋 Команды", callback_data="admin_teams_0")],
        [InlineKeyboardButton(text="📦 Архив матчей", callback_data="admin_archive_matches")],
        [InlineKeyboardButton(text="👥 Управление игроками", callback_data="admin_users_0")],
        [InlineKeyboardButton(text="📢 Массовая Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔥 Ставка Дня", callback_data="admin_daily_bet")],
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text=line_str, callback_data="admin_toggle_line")]
    ])

def cancel_bet_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu_line_type")]
    ])

# ================= USER HANDLERS =================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    get_user(message.from_user.id, message.from_user.username)
    log_action(message.from_user.id, "Запустил бота /start")

    if not await check_subscription(bot, message.from_user.id):
        await message.answer(
            "⚠️ Для работы с ботом необходимо подписаться на оба наших канала!",
            reply_markup=sub_kb()
        )
        return

    await message.answer(
        "🏆 <b>Добро пожаловать в FTCL³ BET!</b>\n\nДелайте ставки на матчи лиги FTCL³, собирайте экспрессы, зарабатывайте монеты и возглавляйте топ каперов!",
        reply_markup=main_menu_kb()
    )

@router.callback_query(F.data == "check_subscription")
async def cb_check_sub(call: CallbackQuery, bot: Bot):
    if await check_subscription(bot, call.from_user.id):
        await call.message.delete()
        await call.message.answer(
            "✅ Подписка подтверждена! Добро пожаловать в FTCL³ BET!",
            reply_markup=main_menu_kb()
        )
    else:
        await call.answer("❌ Вы не подписались на оба канала!", show_alert=True)

@router.callback_query(F.data == "menu_main")
async def cb_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🏆 <b>Главное меню FTCL³ BET</b>", reply_markup=main_menu_kb())

@router.callback_query(F.data == "menu_profile")
async def cb_profile(call: CallbackQuery):
    user = get_user(call.from_user.id, call.from_user.username)
    log_action(call.from_user.id, "Открыл профиль")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) FROM bets WHERE user_id = ?", (call.from_user.id,))
    total, wins = cursor.fetchone()
    wins = wins or 0
    conn.close()

    display_name = get_user_display_name(call.from_user.username, call.from_user.first_name, call.from_user.id)
    text = (
        f"👤 <b>Профиль:</b> {display_name}\n"
        f"🆔 ID: <code>{call.from_user.id}</code>\n\n"
        f"💵 <b>Баланс:</b> <code>{user[2]:.2f}</code> монет\n"
        f"🎯 <b>Всего ставок:</b> {total}\n"
        f"✅ <b>Побед:</b> {wins}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")]])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "menu_bonus")
async def cb_bonus(call: CallbackQuery):
    user = get_user(call.from_user.id, call.from_user.username)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user[4] == today:
        await call.answer("❌ Вы уже забирали бонус сегодня!", show_alert=True)
        return

    update_balance(call.from_user.id, 500)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (today, call.from_user.id))
    conn.commit()
    conn.close()

    log_action(call.from_user.id, "Получил ежедневный бонус +500")
    await call.answer("🎁 Вы получили +500 монет!", show_alert=True)
    await cb_profile(call)

@router.callback_query(F.data == "menu_leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    log_action(call.from_user.id, "Открыл Топ Каперов")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.username, u.user_id, COALESCE(SUM(b.payout - b.amount), 0) as net_profit
        FROM users u
        LEFT JOIN bets b ON u.user_id = b.user_id AND b.status IN ('WIN', 'LOSE')
        GROUP BY u.user_id
        ORDER BY net_profit DESC, u.balance DESC
        LIMIT 10
    """)
    top = cursor.fetchall()
    conn.close()

    text = "📊 <b>ТОП-10 КАПЕРОВ (Чистый профит):</b>\n\n"
    if not top:
        text += "Пока нет рассчитанных ставок."
    else:
        for i, row in enumerate(top, 1):
            name = get_user_display_name(row[0], fallback_id=row[1])
            text += f"{i}. {name} — <code>{row[2]:+.2f}</code> монет\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")]])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "menu_promo")
async def cb_promo(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.enter_promo_code)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")]])
    await call.message.edit_text("🎟 <b>Введите промокод в чат:</b>", reply_markup=kb)

@router.message(UserStates.enter_promo_code)
async def process_promo_input(message: Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    await state.clear()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT reward, max_uses, current_uses FROM promo_codes WHERE code = ?", (code,))
    promo = cursor.fetchone()

    if not promo:
        await message.answer("❌ Промокод не существует или недействителен.", reply_markup=main_menu_kb())
        conn.close()
        return

    reward, max_uses, current_uses = promo

    if current_uses >= max_uses:
        await message.answer("❌ Лимит активаций этого промокода исчерпан.", reply_markup=main_menu_kb())
        conn.close()
        return

    cursor.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND code = ?", (user_id, code))
    if cursor.fetchone():
        await message.answer("❌ Вы уже активировали данный промокод!", reply_markup=main_menu_kb())
        conn.close()
        return

    update_balance(user_id, reward)
    cursor.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code = ?", (code,))
    cursor.execute("INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (user_id, code))
    conn.commit()
    conn.close()

    log_action(user_id, f"Активировал промокод {code} (+{reward})")
    await message.answer(f"🎉 Промокод активирован! Вы получили <b>+{reward:,.0f}</b> монет.", reply_markup=main_menu_kb())

# --- ВЫБОР РЕЖИМА СТАВКИ ---
@router.callback_query(F.data == "menu_line_type")
async def cb_line_type(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_line_open():
        await call.answer("❌ Линия ставок временно закрыта администратором!", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Одинар", callback_data="menu_line_single")],
        [InlineKeyboardButton(text="🔥 Экспресс", callback_data="menu_line_express")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu_main")]
    ])
    await call.message.edit_text("⚽ <b>Выберите формат ставки:</b>", reply_markup=kb)

# --- ОДИНАР ---
@router.callback_query(F.data == "menu_line_single")
async def cb_line_single(call: CallbackQuery):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, home_team, away_team FROM matches WHERE status = 'OPEN'")
    matches = cursor.fetchall()
    conn.close()

    if not matches:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_line_type")]])
        await call.message.edit_text("⚽ Открытых матчей в линии сейчас нет.", reply_markup=kb)
        return

    buttons = []
    for m in matches:
        buttons.append([InlineKeyboardButton(text=f"{m[1]} vs {m[2]}", callback_data=f"match_{m[0]}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_line_type")])

    await call.message.edit_text("🎯 <b>Одинар — Выберите матч:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("match_"))
async def cb_match(call: CallbackQuery):
    match_id = int(call.data.split("_")[1])
    recalculate_dynamic_odds(match_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT home_team, away_team, kef_p1, kef_x, kef_p2, kef_tb, kef_tm, kef_oz_yes, kef_oz_no, kef_exact_score FROM matches WHERE id = ?", (match_id,))
    m = cursor.fetchone()
    conn.close()

    home, away = html.escape(m[0]), html.escape(m[1])
    text = (
        f"⚽ <b>{home} — {away}</b>\n\n"
        f"<b>Текущие динамические коэффициенты:</b>\n"
        f"П1: <code>{m[2]}</code> | Х: <code>{m[3]}</code> | П2: <code>{m[4]}</code>\n"
        f"ТБ 2.5: <code>{m[5]}</code> | ТМ 2.5: <code>{m[6]}</code>\n"
        f"ОЗ Да: <code>{m[7]}</code> | ОЗ Нет: <code>{m[8]}</code>\n"
        f"Точный счёт: <code>~{m[9]}</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"П1 ({m[2]})", callback_data=f"bet_{match_id}_P1"),
            InlineKeyboardButton(text=f"Х ({m[3]})", callback_data=f"bet_{match_id}_X"),
            InlineKeyboardButton(text=f"П2 ({m[4]})", callback_data=f"bet_{match_id}_P2"),
        ],
        [
            InlineKeyboardButton(text=f"ТБ 2.5 ({m[5]})", callback_data=f"bet_{match_id}_TB"),
            InlineKeyboardButton(text=f"ТМ 2.5 ({m[6]})", callback_data=f"bet_{match_id}_TM"),
        ],
        [
            InlineKeyboardButton(text=f"ОЗ Да ({m[7]})", callback_data=f"bet_{match_id}_OZ_YES"),
            InlineKeyboardButton(text=f"ОЗ Нет ({m[8]})", callback_data=f"bet_{match_id}_OZ_NO"),
        ],
        [
            InlineKeyboardButton(text=f"🎯 Точный Счёт ({m[9]})", callback_data=f"bet_{match_id}_SCORE")
        ],
        [InlineKeyboardButton(text="⬅️ Назад в Линию", callback_data="menu_line_single")]
    ])

    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data.startswith("bet_"))
async def cb_bet_init(call: CallbackQuery, state: FSMContext):
    if not is_line_open():
        await call.answer("❌ Линия ставок закрыта!", show_alert=True)
        return

    parts = call.data.split("_")
    match_id = int(parts[1])
    outcome = "_".join(parts[2:])

    recalculate_dynamic_odds(match_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT home_team, away_team, kef_p1, kef_x, kef_p2, kef_tb, kef_tm, kef_oz_yes, kef_oz_no, kef_exact_score FROM matches WHERE id = ?", (match_id,))
    m = cursor.fetchone()
    conn.close()

    kef_map = {
        "P1": m[2], "X": m[3], "P2": m[4],
        "TB": m[5], "TM": m[6],
        "OZ_YES": m[7], "OZ_NO": m[8],
        "SCORE": m[9]
    }
    kef = kef_map[outcome]

    user = get_user(call.from_user.id, call.from_user.username)
    home, away = html.escape(m[0]), html.escape(m[1])

    if outcome == "SCORE":
        await state.update_data(match_id=match_id, outcome_type="SCORE", kef=kef, home=home, away=away)
        await state.set_state(UserStates.enter_exact_score)
        await call.message.edit_text(
            f"🎯 <b>Ставка на Точный Счёт</b> ({home} — {away})\n"
            f"📈 Базовый кэф: <code>{kef}</code>\n"
            f"💵 <b>Ваш баланс:</b> <code>{user[2]:,.2f}</code> монет\n\n"
            f"Введите предполагаемый счет сообщением в чат в формате <code>Х:Х</code> (например, <code>2:1</code>, <code>1:1</code>):",
            reply_markup=cancel_bet_kb()
        )
        return

    await state.update_data(match_id=match_id, outcome=outcome, kef=kef, home=home, away=away)
    await state.set_state(UserStates.enter_bet_amount)

    await call.message.edit_text(
        f"🎯 <b>Ставка:</b> {home} — {away} (<code>{outcome}</code>)\n"
        f"📈 Коэффициент: <code>{kef}</code>\n"
        f"💵 <b>Ваш текущий баланс:</b> <code>{user[2]:,.2f}</code> монет\n\n"
        f"Введите сумму ставки сообщением в чат:",
        reply_markup=cancel_bet_kb()
    )

@router.message(UserStates.enter_exact_score)
async def process_exact_score_input(message: Message, state: FSMContext):
    text = message.text.strip()
    if ":" not in text:
        await message.answer("❌ Неверный формат счета! Введите счет через двоеточие, например: <code>2:1</code>", reply_markup=cancel_bet_kb())
        return

    parts = text.split(":")
    if not (parts[0].isdigit() and parts[1].isdigit()):
        await message.answer("❌ Числа в счете должны быть целыми!", reply_markup=cancel_bet_kb())
        return

    exact_score = f"{parts[0]}:{parts[1]}"
    data = await state.get_data()

    await state.update_data(outcome=f"SCORE_{exact_score}")
    await state.set_state(UserStates.enter_bet_amount)

    user = get_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"🎯 <b>Ставка на Точный Счёт:</b> {data['home']} — {data['away']} (<code>{exact_score}</code>)\n"
        f"📈 Коэффициент: <code>{data['kef']}</code>\n"
        f"💵 <b>Ваш текущий баланс:</b> <code>{user[2]:,.2f}</code> монет\n\n"
        f"Введите сумму ставки сообщением в чат:",
        reply_markup=cancel_bet_kb()
    )

@router.message(UserStates.enter_bet_amount)
async def process_bet_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError()
    except ValueError:
        await message.answer("❌ Введите корректную сумму ставки числом!", reply_markup=cancel_bet_kb())
        return

    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.username)

    if user[2] < amount:
        await message.answer(
            f"❌ Недостаточно монет на балансе!\n"
            f"💵 Ваш баланс: <code>{user[2]:,.2f}</code> монет\n"
            f"Введите другую сумму:",
            reply_markup=cancel_bet_kb()
        )
        return

    data = await state.get_data()
    match_id = data["match_id"]

    update_balance(user_id, -amount)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bets (user_id, match_id, outcome, kef, amount) VALUES (?, ?, ?, ?, ?)",
        (user_id, match_id, data["outcome"], data["kef"], amount)
    )
    bet_id = cursor.lastrowid
    conn.commit()
    conn.close()

    recalculate_dynamic_odds(match_id)

    log_action(user_id, f"Сделал ставку {amount} на {data['home']}-{data['away']} ({data['outcome']})")
    await state.clear()

    home, away = data['home'], data['away']
    new_user = get_user(user_id)
    await message.answer(
        f"✅ <b>Ставка принята!</b>\n\n"
        f"Матч: {home} — {away}\n"
        f"Исход: <code>{data['outcome']}</code> | Кэф: <code>{data['kef']}</code>\n"
        f"Сумма: <code>{amount:,.2f}</code> монет\n"
        f"💵 Остаток на балансе: <code>{new_user[2]:,.2f}</code> монет",
        reply_markup=main_menu_kb()
    )

    if amount >= 15000:
        try:
            username_str = get_user_display_name(message.from_user.username, message.from_user.first_name, user_id)
            post_text = (
                f"💣 <b>КРУПНАЯ СТАВКА!</b>\n\n"
                f"👤 Пользователь: <b>{username_str}</b>\n"
                f"⚽ Матч: <b>{home} — {away}</b>\n"
                f"🎯 Исход: <b>{data['outcome']}</b> | Кэф: <b>{data['kef']}</b>\n"
                f"💰 Сумма: <b>{amount:,.0f} монет</b>\n"
                f"🚀 Возможный выигрыш: <b>{amount * data['kef']:,.0f} монет</b>\n\n"
                f"🤖 Сделать ставку: {BOT_USERNAME}"
            )
            sent = await bot.send_message(chat_id=CHANNEL_ID, text=post_text)
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("UPDATE bets SET channel_msg_id = ?, original_text = ? WHERE id = ?", (sent.message_id, post_text, bet_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Ошибка отправки в Live-канал: {e}")

# --- ЭКСПРЕСС ---
@router.callback_query(F.data == "menu_line_express")
async def cb_express_start(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_ids = data.get("express_selected", [])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, home_team, away_team FROM matches WHERE status = 'OPEN'")
    matches = cursor.fetchall()
    conn.close()

    if not matches or len(matches) < 2:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_line_type")]])
        await call.message.edit_text("❌ Для создания экспресса необходимо минимум 2 открытых матча!", reply_markup=kb)
        return

    buttons = []
    for m in matches:
        check = "✅ " if m[0] in selected_ids else ""
        buttons.append([InlineKeyboardButton(text=f"{check}{m[1]} vs {m[2]}", callback_data=f"exp_toggle_{m[0]}")])

    if len(selected_ids) >= 2:
        buttons.append([InlineKeyboardButton(text="📌 Выбрать Исходы", callback_data="exp_confirm_matches")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_line_type")])

    await call.message.edit_text(
        "🔥 <b>Конструктор Экспресса:</b>\n\nОтметьте галочками от 2-х матчей и нажмите <b>📌 Выбрать Исходы</b>:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@router.callback_query(F.data.startswith("exp_toggle_"))
async def cb_express_toggle(call: CallbackQuery, state: FSMContext):
    m_id = int(call.data.split("_")[2])
    data = await state.get_data()
    selected = data.get("express_selected", [])

    if m_id in selected:
        selected.remove(m_id)
    else:
        selected.append(m_id)

    await state.update_data(express_selected=selected)
    await cb_express_start(call, state)

@router.callback_query(F.data == "exp_confirm_matches")
async def cb_express_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("express_selected", [])

    if len(selected) < 2:
        await call.answer("Выберите минимум 2 матча!", show_alert=True)
        return

    await state.update_data(express_index=0, express_choices={})
    await ask_express_match_outcome(call.message, state)

async def ask_express_match_outcome(message: Message, state: FSMContext):
    data = await state.get_data()
    selected = data["express_selected"]
    idx = data.get("express_index", 0)

    if idx >= len(selected):
        choices = data.get("express_choices", {})
        total_kef = 1.0
        summary_lines = []
        express_matches_data = []

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for m_id, choice in choices.items():
            recalculate_dynamic_odds(m_id)
            cursor.execute("SELECT home_team, away_team, kef_p1, kef_x, kef_p2, kef_tb, kef_tm, kef_oz_yes, kef_oz_no, kef_exact_score FROM matches WHERE id = ?", (m_id,))
            m = cursor.fetchone()

            k_map = {"P1": m[2], "X": m[3], "P2": m[4], "TB": m[5], "TM": m[6], "OZ_YES": m[7], "OZ_NO": m[8], "SCORE": m[9]}
            outcome_code = choice["outcome"]
            
            kef = choice.get("kef", k_map.get(outcome_code, 1.0))
            total_kef *= kef
            summary_lines.append(f"• {m[0]} vs {m[1]} — <b>{outcome_code}</b> (кэф {kef})")

            express_matches_data.append({
                "match_id": m_id,
                "outcome": outcome_code,
                "kef": kef
            })

        conn.close()

        total_kef = round(total_kef, 2)
        await state.update_data(
            express_total_kef=total_kef, 
            express_summary="\n".join(summary_lines),
            express_matches_json=json.dumps(express_matches_data)
        )
        await state.set_state(UserStates.express_enter_amount)

        user = get_user(message.from_user.id, message.from_user.username)
        text = (
            f"🔥 <b>Ваш Экспресс сформирован!</b>\n\n"
            f"{'\n'.join(summary_lines)}\n\n"
            f"📈 <b>Итоговый коэффициент: {total_kef}</b>\n"
            f"💵 <b>Ваш текущий баланс:</b> <code>{user[2]:,.2f}</code> монет\n\n"
            f"Введите сумму ставки на экспресс сообщением в чат:"
        )
        await message.edit_text(text, reply_markup=cancel_bet_kb())
        return

    m_id = selected[idx]
    recalculate_dynamic_odds(m_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT home_team, away_team, kef_p1, kef_x, kef_p2, kef_tb, kef_tm, kef_oz_yes, kef_oz_no, kef_exact_score FROM matches WHERE id = ?", (m_id,))
    m = cursor.fetchone()
    conn.close()

    home, away = html.escape(m[0]), html.escape(m[1])
    text = (
        f"⚽ <b>Матч {idx+1}/{len(selected)}: {home} — {away}</b>\n"
        f"Выберите исход для этого матча:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"П1 ({m[2]})", callback_data=f"exp_pick:{m_id}:P1:{m[2]}"),
            InlineKeyboardButton(text=f"Х ({m[3]})", callback_data=f"exp_pick:{m_id}:X:{m[3]}"),
            InlineKeyboardButton(text=f"П2 ({m[4]})", callback_data=f"exp_pick:{m_id}:P2:{m[4]}"),
        ],
        [
            InlineKeyboardButton(text=f"ТБ 2.5 ({m[5]})", callback_data=f"exp_pick:{m_id}:TB:{m[5]}"),
            InlineKeyboardButton(text=f"ТМ 2.5 ({m[6]})", callback_data=f"exp_pick:{m_id}:TM:{m[6]}"),
        ],
        [
            InlineKeyboardButton(text=f"ОЗ Да ({m[7]})", callback_data=f"exp_pick:{m_id}:OZ_YES:{m[7]}"),
            InlineKeyboardButton(text=f"ОЗ Нет ({m[8]})", callback_data=f"exp_pick:{m_id}:OZ_NO:{m[8]}"),
        ]
    ])

    await message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data.startswith("exp_pick:"))
async def cb_express_pick_outcome(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    m_id = int(parts[1])
    outcome = parts[2]
    kef = float(parts[3])

    data = await state.get_data()
    choices = data.get("express_choices", {})
    choices[m_id] = {"outcome": outcome, "kef": kef}

    idx = data.get("express_index", 0) + 1
    await state.update_data(express_choices=choices, express_index=idx)

    await ask_express_match_outcome(call.message, state)

@router.message(UserStates.express_enter_amount)
async def process_express_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError()
    except ValueError:
        await message.answer("❌ Введите корректную сумму ставки числом!", reply_markup=cancel_bet_kb())
        return

    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.username)

    if user[2] < amount:
        await message.answer(
            f"❌ Недостаточно монет на балансе!\n"
            f"💵 Ваш баланс: <code>{user[2]:,.2f}</code> монет\n"
            f"Введите другую сумму:",
            reply_markup=cancel_bet_kb()
        )
        return

    data = await state.get_data()
    total_kef = data["express_total_kef"]
    summary = data["express_summary"]
    matches_json = data["express_matches_json"]

    update_balance(user_id, -amount)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bets (user_id, match_id, outcome, kef, amount, is_express, express_details, express_matches) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, 0, "EXPRESS", total_kef, amount, 1, summary, matches_json)
    )
    bet_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_action(user_id, f"Сделал экспресс {amount} (кэф {total_kef})")
    await state.clear()

    new_user = get_user(user_id)
    await message.answer(
        f"✅ <b>Экспресс принят!</b>\n\n"
        f"{summary}\n\n"
        f"📈 Итоговый кэф: <code>{total_kef}</code>\n"
        f"💰 Сумма: <code>{amount:,.2f}</code> монет\n"
        f"💵 Остаток на балансе: <code>{new_user[2]:,.2f}</code> монет",
        reply_markup=main_menu_kb()
    )

    if amount >= 15000:
        try:
            username_str = get_user_display_name(message.from_user.username, message.from_user.first_name, user_id)
            post_text = (
                f"🔥 <b>КРУПНЫЙ ЭКСПРЕСС!</b>\n\n"
                f"👤 Пользователь: <b>{username_str}</b>\n\n"
                f"{summary}\n\n"
                f"🚀 Итоговый кэф: <b>{total_kef}</b>\n"
                f"💰 Сумма: <b>{amount:,.0f} монет</b>\n"
                f"🏆 Возможный выигрыш: <b>{amount * total_kef:,.0f} монет</b>\n\n"
                f"🤖 Сделать ставку: {BOT_USERNAME}"
            )
            sent = await bot.send_message(chat_id=CHANNEL_ID, text=post_text)
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("UPDATE bets SET channel_msg_id = ?, original_text = ? WHERE id = ?", (sent.message_id, post_text, bet_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Ошибка отправки в Live-канал: {e}")

@router.callback_query(F.data == "menu_my_bets")
async def cb_my_bets(call: CallbackQuery):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.home_team, m.away_team, b.outcome, b.kef, b.amount, b.status, b.payout, b.is_express, b.express_details
        FROM bets b
        LEFT JOIN matches m ON b.match_id = m.id
        WHERE b.user_id = ?
        ORDER BY b.id DESC LIMIT 10
    """, (call.from_user.id,))
    bets = cursor.fetchall()
    conn.close()

    if not bets:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")]])
        await call.message.edit_text("📜 У вас пока нет ставок.", reply_markup=kb)
        return

    text = "📜 <b>Ваши последние 10 ставок:</b>\n\n"
    for b in bets:
        icon = "⏳" if b[5] == "PENDING" else ("✅" if b[5] == "WIN" else "❌")
        if b[7] == 1:
            match_title = "🔥 <b>ЭКСПРЕСС</b>"
            details = b[8]
        else:
            match_title = f"{html.escape(b[0])} vs {html.escape(b[1])}" if b[0] else "Одинар"
            details = f"   Выбор: <code>{b[2]}</code>"

        text += f"{icon} {match_title}\n{details}\n   Кэф: <code>{b[3]}</code> | Сумма: <code>{b[4]:.2f}</code>\n"
        if b[5] == "WIN":
            text += f"   Выплата: <code>{b[6]:.2f}</code> монет\n"
        text += "-------------------------\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")]])
    await call.message.edit_text(text, reply_markup=kb)

# ================= ADMIN PANEL =================
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.clear()
    await message.answer("🔧 <b>Панель Администратора</b>", reply_markup=admin_main_kb())

@router.callback_query(F.data == "admin_main")
async def cb_admin_main(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await state.clear()
    await call.message.edit_text("🔧 <b>Панель Администратора</b>", reply_markup=admin_main_kb())

@router.callback_query(F.data == "admin_toggle_line")
async def cb_admin_toggle_line(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    current = is_line_open()
    set_line_status(not current)
    status_str = "ОТКРЫТА" if not current else "ЗАКРЫТА"
    await call.answer(f"Линия ставок теперь {status_str}!", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=admin_main_kb())

# --- УПРАВЛЕНИЕ КОМАНДАМИ (CRUD + СЛИЯНИЕ) ---
@router.callback_query(F.data.startswith("admin_teams_"))
async def cb_admin_teams(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await state.clear()
    page = int(call.data.split("_")[2])
    teams = get_all_teams()

    if not teams:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В Админку", callback_data="admin_main")]])
        await call.message.edit_text("📋 <b>Список команд пуст.</b>", reply_markup=kb)
        return

    items_per_page = 10
    total_pages = (len(teams) + items_per_page - 1) // items_per_page
    page_teams = teams[page * items_per_page : (page + 1) * items_per_page]

    buttons = []
    for idx, team_name in enumerate(page_teams):
        # Передаем индекс в списке страницы для краткости callback_data
        buttons.append([InlineKeyboardButton(text=f"🛡 {team_name}", callback_data=f"adm_t_view:{page}:{idx}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_teams_{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin_teams_{page + 1}"))

    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="⬅️ В Админку", callback_data="admin_main")])

    text = f"📋 <b>Управление командами</b> (Всего: <code>{len(teams)}</code>)\nСтраница: {page + 1}/{total_pages}"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("adm_t_view:"))
async def cb_admin_team_view(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    parts = call.data.split(":")
    page, idx = int(parts[1]), int(parts[2])
    teams = get_all_teams()

    target_idx = page * 10 + idx
    if target_idx >= len(teams):
        await call.answer("Команда не найдена!", show_alert=True)
        return

    team_name = teams[target_idx]
    await state.update_data(current_team=team_name)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT games_played, wins, draws, losses, goals_scored, goals_conceded FROM team_stats WHERE team_name = ?", (team_name,))
    st = cursor.fetchone()
    conn.close()

    stats_str = f"Игр: {st[0]} | В: {st[1]} | Н: {st[2]} | П: {st[3]} | ЗГ: {st[4]} | ПГ: {st[5]}" if st else "Статистика отсутствует."

    text = (
        f"🛡 <b>Команда: {html.escape(team_name)}</b>\n\n"
        f"📊 <b>Статистика:</b>\n{stats_str}\n\n"
        f"Выберите действие:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data="adm_t_rename")],
        [InlineKeyboardButton(text="🔀 Совместить клуб", callback_data=f"adm_t_merge_sel:{page}:{idx}")],
        [InlineKeyboardButton(text="🗑 Удалить команду", callback_data="adm_t_delete")],
        [InlineKeyboardButton(text="⬅️ К списку команд", callback_data=f"admin_teams_{page}")]
    ])

    await call.message.edit_text(text, reply_markup=kb)

# --- ИЗМЕНЕНИЕ НАЗВАНИЯ КОМАНДЫ ---
@router.callback_query(F.data == "adm_t_rename")
async def cb_admin_team_rename(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    data = await state.get_data()
    team_name = data.get("current_team")
    
    await state.set_state(AdminStates.rename_team_input)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_teams_0")]])
    await call.message.edit_text(
        f"✏️ Введите новое название для команды <b>{html.escape(team_name)}</b>:\n"
        f"<i>(Все матчи, статистика и открытые ставки будут обновлены)</i>",
        reply_markup=kb
    )

@router.message(AdminStates.rename_team_input)
async def process_admin_team_rename(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    new_name = message.text.strip()
    data = await state.get_data()
    old_name = data.get("current_team")

    if not new_name or old_name == new_name:
        await message.answer("❌ Новое название должно отличаться от старого!", reply_markup=admin_main_kb())
        await state.clear()
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. Обновляем team_stats
    cursor.execute("UPDATE team_stats SET team_name = ? WHERE team_name = ?", (new_name, old_name))

    # 2. Обновляем matches (home & away)
    cursor.execute("UPDATE matches SET home_team = ? WHERE home_team = ?", (new_name, old_name))
    cursor.execute("UPDATE matches SET away_team = ? WHERE away_team = ?", (new_name, old_name))

    # 3. Обновляем express_details
    update_express_details_for_team(cursor, old_name, new_name)

    # 4. Перерасчет кэфов
    trigger_recalc_for_team(cursor, new_name)

    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        f"✅ Команда <b>{html.escape(old_name)}</b> успешно переименована в <b>{html.escape(new_name)}</b>!\n"
        f"Все результаты и ставки были перенесены.",
        reply_markup=admin_main_kb()
    )

# --- СЛИЯНИЕ (СОВМЕЩЕНИЕ) КОМАНД ---
@router.callback_query(F.data.startswith("adm_t_merge_sel:"))
async def cb_admin_team_merge_select(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    parts = call.data.split(":")
    page, idx = int(parts[1]), int(parts[2])
    
    data = await state.get_data()
    team1 = data.get("current_team")

    teams = [t for t in get_all_teams() if t != team1]
    
    if not teams:
        await call.answer("Нет других команд для совмещения!", show_alert=True)
        return

    items_per_page = 10
    total_pages = (len(teams) + items_per_page - 1) // items_per_page
    page_teams = teams[page * items_per_page : (page + 1) * items_per_page]

    buttons = []
    for i, t_name in enumerate(page_teams):
        buttons.append([InlineKeyboardButton(text=f"🤝 {t_name}", callback_data=f"adm_t_merge_target:{page}:{i}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm_t_merge_sel:{page-1}:{idx}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"adm_t_merge_sel:{page+1}:{idx}"))

    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin_teams_0")])

    await call.message.edit_text(
        f"🤝 Выберите вторую команду для совмещения с <b>{html.escape(team1)}</b>:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@router.callback_query(F.data.startswith("adm_t_merge_target:"))
async def cb_admin_team_merge_target(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    parts = call.data.split(":")
    page, i = int(parts[1]), int(parts[2])

    data = await state.get_data()
    team1 = data.get("current_team")
    teams = [t for t in get_all_teams() if t != team1]

    target_idx = page * 10 + i
    if target_idx >= len(teams):
        await call.answer("Команда не найдена!", show_alert=True)
        return

    team2 = teams[target_idx]
    await state.update_data(merge_team1=team1, merge_team2=team2)
    await state.set_state(AdminStates.merge_teams_new_name)

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_teams_0")]])
    await call.message.edit_text(
        f"🤝 Совмещение команд: <b>{html.escape(team1)}</b> + <b>{html.escape(team2)}</b>\n\n"
        f"Введите новое название для совмещённой команды в чат:",
        reply_markup=kb
    )

@router.message(AdminStates.merge_teams_new_name)
async def process_admin_team_merge_final(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    merged_name = message.text.strip()
    data = await state.get_data()
    t1 = data.get("merge_team1")
    t2 = data.get("merge_team2")

    if not merged_name:
        await message.answer("❌ Название не может быть пустым!")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. Суммируем статистику команд в team_stats
    cursor.execute("SELECT games_played, wins, draws, losses, goals_scored, goals_conceded FROM team_stats WHERE team_name = ?", (t1,))
    st1 = cursor.fetchone() or (0, 0, 0, 0, 0, 0)

    cursor.execute("SELECT games_played, wins, draws, losses, goals_scored, goals_conceded FROM team_stats WHERE team_name = ?", (t2,))
    st2 = cursor.fetchone() or (0, 0, 0, 0, 0, 0)

    sum_gp = st1[0] + st2[0]
    sum_w = st1[1] + st2[1]
    sum_d = st1[2] + st2[2]
    sum_l = st1[3] + st2[3]
    sum_gs = st1[4] + st2[4]
    sum_gc = st1[5] + st2[5]

    cursor.execute("DELETE FROM team_stats WHERE team_name IN (?, ?, ?)", (t1, t2, merged_name))
    cursor.execute("""
        INSERT INTO team_stats (team_name, games_played, wins, draws, losses, goals_scored, goals_conceded)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (merged_name, sum_gp, sum_w, sum_d, sum_l, sum_gs, sum_gc))

    # 2. Обновляем матчи t1 и t2 на merged_name
    cursor.execute("UPDATE matches SET home_team = ? WHERE home_team IN (?, ?)", (merged_name, t1, t2))
    cursor.execute("UPDATE matches SET away_team = ? WHERE away_team IN (?, ?)", (merged_name, t1, t2))

    # 3. Обновляем экспрессы
    update_express_details_for_team(cursor, t1, merged_name)
    update_express_details_for_team(cursor, t2, merged_name)

    # 4. Перерасчет кэфов
    trigger_recalc_for_team(cursor, merged_name)

    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        f"✅ Команды <b>{html.escape(t1)}</b> и <b>{html.escape(t2)}</b> успешно совмещены в <b>{html.escape(merged_name)}</b>!\n"
        f"Вся статистика и результаты соревнований перенесены.",
        reply_markup=admin_main_kb()
    )

# --- УДАЛЕНИЕ КОМАНДЫ ---
@router.callback_query(F.data == "adm_t_delete")
async def cb_admin_team_delete(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    data = await state.get_data()
    team_name = data.get("current_team")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM team_stats WHERE team_name = ?", (team_name,))
    conn.commit()
    conn.close()

    await state.clear()
    await call.answer(f"🗑 Команда {team_name} удалена из базы статистики!", show_alert=True)
    await cb_admin_teams(call, state)

# --- Массовая рассылка ---
@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_broadcast_message)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_main")]])
    await call.message.edit_text(
        "📢 <b>Массовая Рассылка</b>\n\n"
        "Пришлите сообщение для рассылки всем пользователям (поддерживаются форматирование текста, фотографии и файлы):",
        reply_markup=kb
    )

@router.message(AdminStates.waiting_broadcast_message)
async def process_admin_broadcast(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS: return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
    users = cursor.fetchall()
    conn.close()

    await message.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")

    success = 0
    failed = 0

    for u in users:
        u_id = u[0]
        try:
            await bot.copy_message(
                chat_id=u_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success += 1
            await asyncio.sleep(0.04)
        except Exception:
            failed += 1

    await state.clear()
    await message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"Успешно отправлено: <code>{success}</code>\n"
        f"Ошибок: <code>{failed}</code>",
        reply_markup=admin_main_kb()
    )

@router.callback_query(F.data == "admin_create_promo")
async def cb_admin_create_promo(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_promo_name)
    await call.message.edit_text("Введите название нового промокода:")

@router.message(AdminStates.waiting_promo_name)
async def admin_promo_name(message: Message, state: FSMContext):
    await state.update_data(promo_name=message.text.strip())
    await state.set_state(AdminStates.waiting_promo_reward)
    await message.answer("Введите размер награды (число):")

@router.message(AdminStates.waiting_promo_reward)
async def admin_promo_reward(message: Message, state: FSMContext):
    try:
        reward = float(message.text)
        if reward <= 0: raise ValueError()
        await state.update_data(promo_reward=reward)
        await state.set_state(AdminStates.waiting_promo_uses)
        await message.answer("Введите максимальное количество активаций:")
    except ValueError:
        await message.answer("❌ Введите корректное число!")

@router.message(AdminStates.waiting_promo_uses)
async def admin_promo_uses(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите целое число!")
        return

    data = await state.get_data()
    p_name = data["promo_name"]
    p_reward = data["promo_reward"]
    p_uses = int(message.text)
    await state.clear()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO promo_codes (code, reward, max_uses) VALUES (?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET reward=excluded.reward, max_uses=excluded.max_uses, current_uses=0
    """, (p_name, p_reward, p_uses))
    conn.commit()
    conn.close()

    await message.answer(
        f"✅ Промокод <code>{html.escape(p_name)}</code> успешно создан!\n"
        f"💰 Награда: <code>{p_reward:,.0f}</code> монет\n"
        f"👥 Лимит активаций: <code>{p_uses}</code>",
        reply_markup=admin_main_kb()
    )

# --- Управление Матчами и Архив ---
@router.callback_query(F.data == "admin_matches")
async def cb_admin_matches(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, home_team, away_team, status FROM matches WHERE status != 'ARCHIVED' ORDER BY id DESC LIMIT 15")
    matches = cursor.fetchall()
    conn.close()

    buttons = [[InlineKeyboardButton(text="➕ Создать матч", callback_data="admin_add_match")]]
    for m in matches:
        st = "🟢" if m[3] == "OPEN" else "🔴"
        buttons.append([InlineKeyboardButton(text=f"{st} {m[1]} vs {m[2]}", callback_data=f"admin_m_{m[0]}")])
    buttons.append([InlineKeyboardButton(text="⬅️ В Админку", callback_data="admin_main")])

    await call.message.edit_text("⚽ <b>Активные матчи:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == "admin_archive_matches")
async def cb_admin_archive_matches(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, home_team, away_team, status FROM matches WHERE status = 'ARCHIVED' ORDER BY id DESC LIMIT 20")
    matches = cursor.fetchall()
    conn.close()

    if not matches:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В Админку", callback_data="admin_main")]])
        await call.message.edit_text("📦 <b>Архив матчей пуст.</b>", reply_markup=kb)
        return

    buttons = []
    for m in matches:
        buttons.append([InlineKeyboardButton(text=f"📦 {m[1]} vs {m[2]}", callback_data=f"admin_m_{m[0]}")])
    buttons.append([InlineKeyboardButton(text="⬅️ В Админку", callback_data="admin_main")])

    await call.message.edit_text("📦 <b>Архив матчей:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == "admin_add_match")
async def cb_admin_add_match(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminStates.add_match_teams)
    await call.message.edit_text("Введите команды через тире (например: <code>Рапид - Оренбург</code>):")

@router.message(AdminStates.add_match_teams)
async def process_admin_add_match(message: Message, state: FSMContext):
    try:
        home, away = [x.strip() for x in message.text.split("-")]
        p1, x, p2, tb, tm, oz_y, oz_n = calculate_team_odds(home, away)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO matches (home_team, away_team, kef_p1, kef_x, kef_p2, kef_tb, kef_tm, kef_oz_yes, kef_oz_no) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (home, away, p1, x, p2, tb, tm, oz_y, oz_n)
        )
        conn.commit()
        conn.close()

        await state.clear()
        home_esc, away_esc = html.escape(home), html.escape(away)
        await message.answer(
            f"✅ Матч <b>{home_esc} — {away_esc}</b> добавлен!\n"
            f"Автокэфы: П1 <code>{p1}</code> | Х <code>{x}</code> | П2 <code>{p2}</code>\n"
            f"ТБ 2.5 <code>{tb}</code> | ТМ 2.5 <code>{tm}</code> | ОЗ Да <code>{oz_y}</code> | ОЗ Нет <code>{oz_n}</code>",
            reply_markup=admin_main_kb()
        )
    except Exception:
        await message.answer("❌ Ошибка формата! Используйте: <code>Команда1 - Команда2</code>")

@router.callback_query(F.data.startswith("admin_m_"))
async def cb_admin_match_detail(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    match_id = int(call.data.split("_")[2])

    recalculate_dynamic_odds(match_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT home_team, away_team, kef_p1, kef_x, kef_p2, kef_tb, kef_tm, kef_oz_yes, kef_oz_no, kef_exact_score, status FROM matches WHERE id = ?", (match_id,))
    m = cursor.fetchone()
    
    cursor.execute("SELECT outcome, SUM(amount), COUNT(*) FROM bets WHERE match_id = ? GROUP BY outcome", (match_id,))
    pools = cursor.fetchall()
    conn.close()

    pool_str = "\n".join([f"• <code>{p[0]}</code>: {p[1]:,.0f} монет ({p[2]} ставок)" for p in pools]) or "Ставок нет."

    home, away = html.escape(m[0]), html.escape(m[1])
    text = (
        f"⚽ <b>{home} — {away}</b> (Статус: {m[10]})\n\n"
        f"Кэфы: П1 <code>{m[2]}</code> | Х <code>{m[3]}</code> | П2 <code>{m[4]}</code>\n"
        f"ТБ: <code>{m[5]}</code> | ТМ: <code>{m[6]}</code> | ОЗ Да: <code>{m[7]}</code> | ОЗ Нет: <code>{m[8]}</code>\n\n"
        f"📊 <b>Пулы ставок:</b>\n{pool_str}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить кэфы", callback_data=f"am_kefs_{match_id}"), InlineKeyboardButton(text="✏️ Команды", callback_data=f"am_teams_{match_id}")],
        [InlineKeyboardButton(text="🏁 Завершить матч (Счёт)", callback_data=f"am_finish_{match_id}")],
        [InlineKeyboardButton(text="📦 В Архив", callback_data=f"am_archive_{match_id}"), InlineKeyboardButton(text="🗑 Удалить матч", callback_data=f"am_delete_{match_id}")],
        [InlineKeyboardButton(text="⬅️ К матчам", callback_data="admin_matches")]
    ])

    await call.message.edit_text(text, reply_markup=kb)

# --- РЕДАКТИРОВАНИЕ И АРХИВАЦИЯ МАТЧА ---
@router.callback_query(F.data.startswith("am_teams_"))
async def cb_am_edit_teams(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    match_id = int(call.data.split("_")[2])
    await state.update_data(edit_match_id=match_id)
    await state.set_state(AdminStates.edit_teams)
    await call.message.edit_text("Введите новые названия команд через тире (например: <code>Барселона - Реал</code>):")

@router.message(AdminStates.edit_teams)
async def process_edit_teams(message: Message, state: FSMContext):
    try:
        home, away = [x.strip() for x in message.text.split("-")]
        data = await state.get_data()
        m_id = data["edit_match_id"]

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE matches SET home_team = ?, away_team = ? WHERE id = ?", (home, away, m_id))
        conn.commit()

        # Запускаем перерасчет после измененных имен
        trigger_recalc_for_team(cursor, home)
        trigger_recalc_for_team(cursor, away)

        conn.close()

        await state.clear()
        await message.answer("✅ Названия команд успешно изменены!", reply_markup=admin_main_kb())
    except Exception:
        await message.answer("❌ Ошибка формата! Используйте: <code>Команда1 - Команда2</code>")

@router.callback_query(F.data.startswith("am_kefs_"))
async def cb_am_edit_kefs(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    match_id = int(call.data.split("_")[2])
    await state.update_data(edit_match_id=match_id)
    await state.set_state(AdminStates.edit_kefs)
    await call.message.edit_text("Введите 3 кэфа через пробел (П1 Х П2), например: <code>1.85 3.20 2.10</code>:")

@router.message(AdminStates.edit_kefs)
async def process_edit_kefs(message: Message, state: FSMContext):
    try:
        p1, x, p2 = map(float, message.text.split())
        data = await state.get_data()
        m_id = data["edit_match_id"]

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE matches SET kef_p1 = ?, kef_x = ?, kef_p2 = ? WHERE id = ?", (p1, x, p2, m_id))
        conn.commit()
        conn.close()

        await state.clear()
        await message.answer("✅ Коэффициенты успешно обновлены!", reply_markup=admin_main_kb())
    except Exception:
        await message.answer("❌ Ошибка ввода! Введите три числа через пробел.")

@router.callback_query(F.data.startswith("am_archive_"))
async def cb_am_archive(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    match_id = int(call.data.split("_")[2])
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE matches SET status = 'ARCHIVED' WHERE id = ?", (match_id,))
    conn.commit()
    conn.close()

    await call.answer("📦 Матч отправлен в Архив!", show_alert=True)
    await cb_admin_matches(call)

@router.callback_query(F.data.startswith("am_delete_"))
async def cb_am_delete(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    match_id = int(call.data.split("_")[2])
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    cursor.execute("DELETE FROM bets WHERE match_id = ? AND is_express = 0", (match_id,))
    conn.commit()
    conn.close()

    await call.answer("🗑 Матч успешно удален!", show_alert=True)
    await cb_admin_matches(call)

# --- РАСЧЕТ МАТЧА И ЭКСПРЕССОВ ---
@router.callback_query(F.data.startswith("am_finish_"))
async def cb_admin_finish(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    match_id = int(call.data.split("_")[2])
    await state.update_data(finish_match_id=match_id)
    await state.set_state(AdminStates.finish_score)
    await call.message.edit_text("Введите итоговый счет матча через пробел (например: <code>4 2</code>):")

def check_single_bet_win(outcome: str, sh: int, sa: int) -> bool:
    total_goals = sh + sa
    both_scored = (sh > 0 and sa > 0)
    exact_score_str = f"{sh}:{sa}"

    if outcome == "P1" and sh > sa: return True
    if outcome == "X" and sh == sa: return True
    if outcome == "P2" and sa > sh: return True
    if outcome == "TB" and total_goals > 2.5: return True
    if outcome == "TM" and total_goals < 2.5: return True
    if outcome == "OZ_YES" and both_scored: return True
    if outcome == "OZ_NO" and not both_scored: return True
    if outcome.startswith("SCORE_") and outcome.split("_")[1] == exact_score_str: return True
    return False

@router.message(AdminStates.finish_score)
async def process_admin_finish(message: Message, state: FSMContext, bot: Bot):
    try:
        sh, sa = map(int, message.text.split())
        data = await state.get_data()
        match_id = data["finish_match_id"]

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT home_team, away_team FROM matches WHERE id = ?", (match_id,))
        home, away = cursor.fetchone()

        cursor.execute("UPDATE matches SET status = 'FINISHED', score_home = ?, score_away = ? WHERE id = ?", (sh, sa, match_id))

        def update_team(team, scored, conceded, win, draw):
            cursor.execute("INSERT OR IGNORE INTO team_stats (team_name) VALUES (?)", (team,))
            w = 1 if win else 0
            d = 1 if draw else 0
            l = 1 if (not win and not draw) else 0
            cursor.execute("""
                UPDATE team_stats SET games_played = games_played + 1, wins = wins + ?, draws = draws + ?, losses = losses + ?,
                goals_scored = goals_scored + ?, goals_conceded = goals_conceded + ? WHERE team_name = ?
            """, (w, d, l, scored, conceded, team))

        update_team(home, sh, sa, sh > sa, sh == sa)
        update_team(away, sa, sh, sa > sh, sh == sa)

        # 1. Расчет одинаров
        cursor.execute("SELECT id, user_id, outcome, kef, amount, channel_msg_id, original_text FROM bets WHERE match_id = ? AND status = 'PENDING' AND is_express = 0", (match_id,))
        bets = cursor.fetchall()

        for b in bets:
            b_id, u_id, outcome, kef, amount, channel_msg_id, original_text = b
            win = check_single_bet_win(outcome, sh, sa)
            payout = amount * kef if win else 0.0
            st = "WIN" if win else "LOSE"

            cursor.execute("UPDATE bets SET status = ?, payout = ? WHERE id = ?", (st, payout, b_id))
            if win:
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (payout, u_id))

            if channel_msg_id:
                try:
                    status_line = "✅ <b>Ставка сыграла!</b>" if win else "❌ <b>Ставка не сыграла!</b>"
                    base_template = original_text if original_text else f"⚽ <b>Матч: {html.escape(home)} — {html.escape(away)}</b>"
                    updated_text = f"{base_template}\n\n───────────────────\n🏁 <b>Матч завершён со счётом: {sh}:{sa}</b>\n{status_line}"
                    await bot.edit_message_text(chat_id=CHANNEL_ID, message_id=channel_msg_id, text=updated_text)
                except Exception as e:
                    logging.error(f"Ошибка апдейта канала: {e}")

        # 2. Расчет Экспрессов
        cursor.execute("SELECT id, user_id, kef, amount, express_matches, channel_msg_id, original_text FROM bets WHERE status = 'PENDING' AND is_express = 1")
        express_bets = cursor.fetchall()

        for eb in express_bets:
            eb_id, u_id, total_kef, amount, matches_json, channel_msg_id, original_text = eb
            if not matches_json: continue

            m_list = json.loads(matches_json)
            all_finished = True
            express_lost = False

            for item in m_list:
                m_item_id = item["match_id"]
                m_outcome = item["outcome"]

                cursor.execute("SELECT status, score_home, score_away FROM matches WHERE id = ?", (m_item_id,))
                m_data = cursor.fetchone()

                if not m_data or m_data[0] not in ['FINISHED', 'ARCHIVED']:
                    all_finished = False
                else:
                    if not check_single_bet_win(m_outcome, m_data[1], m_data[2]):
                        express_lost = True

            if express_lost:
                cursor.execute("UPDATE bets SET status = 'LOSE', payout = 0.0 WHERE id = ?", (eb_id,))
                if channel_msg_id:
                    try:
                        updated_text = f"{original_text}\n\n───────────────────\n❌ <b>Экспресс проигран!</b>"
                        await bot.edit_message_text(chat_id=CHANNEL_ID, message_id=channel_msg_id, text=updated_text)
                    except Exception as e: logging.error(f"Ошибка апдейта канала (Экспресс): {e}")

            elif all_finished and not express_lost:
                payout = amount * total_kef
                cursor.execute("UPDATE bets SET status = 'WIN', payout = ? WHERE id = ?", (payout, eb_id))
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (payout, u_id))
                if channel_msg_id:
                    try:
                        updated_text = f"{original_text}\n\n───────────────────\n✅ <b>ЭКСПРЕСС ВЫИГРАЛ!</b>\n💰 Выплата: <b>{payout:,.0f} монет</b>"
                        await bot.edit_message_text(chat_id=CHANNEL_ID, message_id=channel_msg_id, text=updated_text)
                    except Exception as e: logging.error(f"Ошибка апдейта канала (Экспресс): {e}")

        conn.commit()
        conn.close()

        await state.clear()
        home_esc, away_esc = html.escape(home), html.escape(away)
        await message.answer(f"✅ Матч <b>{home_esc} {sh}:{sa} {away_esc}</b> завершен! Все одинары и экспрессы рассчитаны.", reply_markup=admin_main_kb())
    except Exception as e:
        await message.answer(f"❌ Ошибка ввода счета! Введите два числа через пробел. ({e})")

# --- Управление Игроками ---
@router.callback_query(F.data.startswith("admin_users_"))
async def cb_admin_users(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    page = int(call.data.split("_")[2])

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN user_id IN (SELECT DISTINCT user_id FROM bets) THEN 1 ELSE 0 END) FROM users")
    total_u, active_u = cursor.fetchone()

    cursor.execute("SELECT user_id, username, balance, is_banned FROM users ORDER BY user_id DESC LIMIT 10 OFFSET ?", (page * 10,))
    users = cursor.fetchall()
    conn.close()

    text = f"👥 <b>Управление игроками:</b>\nВсего пользователей: <code>{total_u}</code> | Активных: <code>{active_u or 0}</code>\nСтраница: {page + 1}"

    buttons = []
    for u in users:
        ban_tag = "⛔" if u[3] == 1 else "👤"
        name = get_user_display_name(u[1], fallback_id=u[0])
        buttons.append([InlineKeyboardButton(text=f"{ban_tag} {name} | {u[2]:.0f} mon", callback_data=f"ad_u_{u[0]}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_users_{page - 1}"))
    if (page + 1) * 10 < total_u:
        nav.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin_users_{page + 1}"))

    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="⬅️ В Админку", callback_data="admin_main")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("ad_u_"))
async def cb_admin_user_card(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    u_id = int(call.data.split("_")[2])

    user = get_user(u_id)
    display_name = get_user_display_name(user[1], fallback_id=user[0])
    text = (
        f"👤 <b>Карточка игрока:</b> {display_name}\n"
        f"🆔 ID: <code>{user[0]}</code>\n"
        f"Баланс: <code>{user[2]:.2f}</code> монет\n"
        f"Забанен: {'Да ⛔' if user[3] == 1 else 'Нет ✅'}"
    )

    ban_btn_text = "🟢 Разбанить" if user[3] == 1 else "⛔ Забанить"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"u_edit_bal_{u_id}"), InlineKeyboardButton(text="➕ Добавить монет", callback_data=f"u_add_bal_{u_id}")],
        [InlineKeyboardButton(text=ban_btn_text, callback_data=f"u_toggle_ban_{u_id}"), InlineKeyboardButton(text="📋 Логи 24ч", callback_data=f"u_logs_{u_id}")],
        [InlineKeyboardButton(text="⚠️ Аннулировать прогресс", callback_data=f"u_reset_{u_id}")],
        [InlineKeyboardButton(text="⬅️ К списку игроков", callback_data="admin_users_0")]
    ])

    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data.startswith("u_edit_bal_"))
async def cb_u_edit_bal(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    u_id = int(call.data.split("_")[3])
    await state.update_data(target_user_id=u_id)
    await state.set_state(AdminStates.user_set_balance)
    await call.message.edit_text(f"Введите НОВЫЙ баланс для игрока <code>{u_id}</code>:")

@router.message(AdminStates.user_set_balance)
async def process_user_set_bal(message: Message, state: FSMContext):
    try:
        new_bal = float(message.text)
        data = await state.get_data()
        u_id = data["target_user_id"]
        set_balance(u_id, new_bal)
        await state.clear()
        await message.answer(f"✅ Установлен новый баланс <code>{new_bal:.2f}</code> для игрока <code>{u_id}</code>", reply_markup=admin_main_kb())
    except Exception:
        await message.answer("❌ Введите корректное число!")

@router.callback_query(F.data.startswith("u_add_bal_"))
async def cb_u_add_bal(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    u_id = int(call.data.split("_")[3])
    await state.update_data(target_user_id=u_id)
    await state.set_state(AdminStates.user_add_balance)
    await call.message.edit_text(f"Введите сколько монет ДОБАВИТЬ игроку <code>{u_id}</code>:")

@router.message(AdminStates.user_add_balance)
async def process_user_add_bal(message: Message, state: FSMContext):
    try:
        add_amount = float(message.text)
        data = await state.get_data()
        u_id = data["target_user_id"]
        update_balance(u_id, add_amount)
        await state.clear()
        await message.answer(f"✅ Изменение <code>{add_amount:+.2f}</code> применилось к балансу игрока <code>{u_id}</code>", reply_markup=admin_main_kb())
    except Exception:
        await message.answer("❌ Введите корректное число!")

@router.callback_query(F.data.startswith("u_toggle_ban_"))
async def cb_toggle_ban(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    u_id = int(call.data.split("_")[3])
    user = get_user(u_id)
    new_status = 0 if user[3] == 1 else 1

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (new_status, u_id))
    conn.commit()
    conn.close()

    await call.answer("Статус бана изменен!", show_alert=True)
    await cb_admin_user_card(call)

@router.callback_query(F.data.startswith("u_logs_"))
async def cb_user_logs(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    u_id = int(call.data.split("_")[2])
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT action, timestamp FROM user_logs WHERE user_id = ? AND timestamp >= datetime('now', '-1 day') ORDER BY id DESC LIMIT 15", (u_id,))
    logs = cursor.fetchall()
    conn.close()

    text = f"📋 <b>Логи игрока <code>{u_id}</code> за 24 часа:</b>\n\n"
    for l in logs:
        text += f"• <code>{l[1]}</code>: {html.escape(l[0])}\n"
    if not logs: text += "Действий не зафиксировано."

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ad_u_{u_id}")]])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data.startswith("u_reset_"))
async def cb_user_reset(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    u_id = int(call.data.split("_")[2])
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = 0.0 WHERE user_id = ?", (u_id,))
    cursor.execute("DELETE FROM bets WHERE user_id = ?", (u_id,))
    conn.commit()
    conn.close()

    await call.answer("Прогресс и баланс игрока сброшены до 0!", show_alert=True)
    await cb_admin_user_card(call)

# --- Ставка Дня ---
@router.callback_query(F.data == "admin_daily_bet")
async def cb_admin_daily_bet(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, home_team, away_team, kef_p1, kef_p2 FROM matches WHERE status = 'OPEN'")
    matches = cursor.fetchall()
    conn.close()

    if not matches:
        await call.answer("❌ Нет открытых матчей для создания Ставки Дня!", show_alert=True)
        return

    chosen = random.sample(matches, min(len(matches), 2))
    total_kef = 1.0
    desc = []
    
    for m in chosen:
        outcome = random.choice(["P1", "P2"])
        kef = m[3] if outcome == "P1" else m[4]
        total_kef *= kef
        desc.append(f"• {html.escape(m[1])} vs {html.escape(m[2])} ({outcome})")

    boosted_kef = round(total_kef * 1.15, 2)
    bet_text = "\n".join(desc)

    await state.update_data(daily_text=bet_text, daily_kef=boosted_kef)

    text = (
        f"🔥 <b>Сгенерирована СТАВКА ДНЯ:</b>\n\n"
        f"{bet_text}\n\n"
        f"📈 Повышенный Кэф: <code>{boosted_kef}</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переизбрать", callback_data="admin_daily_bet")],
        [InlineKeyboardButton(text="✅ Одобрить и рассылать", callback_data="admin_approve_daily")],
        [InlineKeyboardButton(text="⬅️ В Админку", callback_data="admin_main")]
    ])

    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "admin_approve_daily")
async def cb_approve_daily(call: CallbackQuery, state: FSMContext, bot: Bot):
    if call.from_user.id not in ADMIN_IDS: return
    data = await state.get_data()
    bet_text = data.get("daily_text")
    kef = data.get("daily_kef")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
    users = cursor.fetchall()
    conn.close()

    msg = f"🔥 <b>СТАВКА ДНЯ В FTCL³ BET!</b>\n\n{bet_text}\n\n🚀 Повышенный кэф: <b>{kef}</b>\n\nЗаходи в бота и успей сделать ставку!"
    
    cnt = 0
    for u in users:
        try:
            await bot.send_message(chat_id=u[0], text=msg)
            cnt += 1
            await asyncio.sleep(0.05)
        except Exception: pass

    await state.clear()
    await call.message.edit_text(f"✅ Ставка Дня расслана {cnt} пользователям!", reply_markup=admin_main_kb())

# ================= MAIN RUN =================
async def main():
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
