import telebot
import os
import logging
from datetime import datetime, timedelta
import sqlite3
from dotenv import load_dotenv
from collections import defaultdict
import pytz

# Загружаем переменные окружения
load_dotenv()

# Инициализация логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("❌ TELEGRAM_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# Стандартные категории
DEFAULT_CATEGORIES = ['Еда', 'Транспорт', 'Развлечения', 'Подписки', 'Здоровье', 'Жильё', 'Образование', 'Другое']

# Поддерживаемые тайм-зоны
TIMEZONES = {
    'UTC+0': 'UTC',
    'UTC+1': 'Europe/London',
    'UTC+2': 'Europe/Helsinki',
    'UTC+3': 'Europe/Moscow',
    'UTC+4': 'Asia/Baku',
    'UTC+5': 'Asia/Tashkent',
    'UTC+6': 'Asia/Almaty',
    'UTC+7': 'Asia/Bangkok',
    'UTC+8': 'Asia/Shanghai',
    'UTC+9': 'Asia/Tokyo',
    'UTC+10': 'Australia/Sydney',
    'UTC+11': 'Pacific/Guadalcanal',
    'UTC+12': 'Pacific/Fiji',
}

# ===== БД =====
DB_PATH = 'data/expenses.db'

def init_db():
    """Инициализация БД"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            timezone TEXT DEFAULT 'UTC+3',
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            category TEXT,
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT UNIQUE,
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ БД инициализирована")

def save_user(user_id, username, first_name, timezone='UTC+3'):
    """Сохранить пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, timezone)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, timezone))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения пользователя: {e}")

def get_user_timezone(user_id):
    """Получить тайм-зону пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT timezone FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 'UTC+3'
    except Exception as e:
        logger.error(f"❌ Ошибка получения тайм-зоны: {e}")
        return 'UTC+3'

def update_user_timezone(user_id, timezone):
    """Обновить тайм-зону пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET timezone = ? WHERE user_id = ?', (timezone, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления тайм-зоны: {e}")
        return False

def get_user_local_time(user_id):
    """Получить текущее время пользователя"""
    tz_str = get_user_timezone(user_id)
    tz_name = TIMEZONES.get(tz_str, 'UTC')
    tz = pytz.timezone(tz_name)
    return datetime.now(tz)

def initialize_user_categories(user_id):
    """Инициализировать категории для нового пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for category in DEFAULT_CATEGORIES:
            cursor.execute('''
                INSERT OR IGNORE INTO user_categories (user_id, category, usage_count)
                VALUES (?, ?, 0)
            ''', (user_id, category))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации категорий: {e}")

def get_user_categories_sorted(user_id):
    """Получить отсортированные категории пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT category, usage_count
            FROM user_categories
            WHERE user_id = ?
            ORDER BY usage_count DESC, category ASC
        ''', (user_id,))
        
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()
        return categories
    except Exception as e:
        logger.error(f"❌ Ошибка получения категорий: {e}")
        return DEFAULT_CATEGORIES

def get_top_categories(user_id, limit=5):
    """Получить топ категорий по использованию"""
    categories = get_user_categories_sorted(user_id)
    return categories[:limit]

def get_common_categories(user_id):
    """Получить оставшиеся категории (не в топ-5)"""
    categories = get_user_categories_sorted(user_id)
    return categories[5:] if len(categories) > 5 else []

def add_category(user_id, category):
    """Добавить новую категорию"""
    try:
        category = category.lower().capitalize()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO user_categories (user_id, category, usage_count)
            VALUES (?, ?, 0)
        ''', (user_id, category))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления категории: {e}")
        return False

def increment_category_usage(user_id, category):
    """Увеличить счётчик использования категории"""
    try:
        category = category.lower().capitalize()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE user_categories
            SET usage_count = usage_count + 1
            WHERE user_id = ? AND category = ?
        ''', (user_id, category))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка обновления счётчика: {e}")

def add_expense(user_id, amount, category, description):
    """Добавить расход"""
    try:
        category = category.lower().capitalize()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO expenses (user_id, amount, category, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, category, description))
        
        conn.commit()
        expense_id = cursor.lastrowid
        conn.close()
        
        increment_category_usage(user_id, category)
        return expense_id
    except Exception as e:
        logger.error(f"❌ Ошибка добавления расхода: {e}")
        return None

def edit_expense(expense_id, amount=None, category=None, description=None):
    """Редактировать расход"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if amount is not None:
            cursor.execute('UPDATE expenses SET amount = ? WHERE id = ?', (amount, expense_id))
        if category is not None:
            category = category.lower().capitalize()
            cursor.execute('UPDATE expenses SET category = ? WHERE id = ?', (category, expense_id))
        if description is not None:
            cursor.execute('UPDATE expenses SET description = ? WHERE id = ?', (description, expense_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования расхода: {e}")
        return False

def delete_expense(expense_id):
    """Удалить расход"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления расхода: {e}")
        return False

def get_expense(expense_id, user_id):
    """Получить расход по ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, amount, category, description, timestamp
            FROM expenses
            WHERE id = ? AND user_id = ?
        ''', (expense_id, user_id))
        
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка получения расхода: {e}")
        return None

def get_all_expenses(user_id, limit=20):
    """Получить расходы пользователя (новые сверху, максимум limit)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, amount, category, description, timestamp
            FROM expenses
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        
        expenses = cursor.fetchall()
        conn.close()
        return expenses
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов: {e}")
        return []

def get_today_expenses(user_id):
    """Получить расходы за день (по времени пользователя)"""
    try:
        tz_str = get_user_timezone(user_id)
        tz_name = TIMEZONES.get(tz_str, 'UTC')
        tz = pytz.timezone(tz_name)
        
        now = datetime.now(tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, amount, category, description, timestamp
            FROM expenses
            WHERE user_id = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp DESC
        ''', (user_id, today_start.isoformat(), today_end.isoformat()))
        
        expenses = cursor.fetchall()
        conn.close()
        return expenses
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов за день: {e}")
        return []

def get_today_expenses_by_category(user_id, category):
    """Получить расходы за день по категории"""
    try:
        category = category.lower().capitalize()
        tz_str = get_user_timezone(user_id)
        tz_name = TIMEZONES.get(tz_str, 'UTC')
        tz = pytz.timezone(tz_name)
        
        now = datetime.now(tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, amount, category, description, timestamp
            FROM expenses
            WHERE user_id = ? AND category = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp DESC
        ''', (user_id, category, today_start.isoformat(), today_end.isoformat()))
        
        expenses = cursor.fetchall()
        conn.close()
        return expenses
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов: {e}")
        return []

def get_month_expenses(user_id):
    """Получить расходы за месяц"""
    try:
        tz_str = get_user_timezone(user_id)
        tz_name = TIMEZONES.get(tz_str, 'UTC')
        tz = pytz.timezone(tz_name)
        
        now = datetime.now(tz)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT SUM(amount) FROM expenses
            WHERE user_id = ? AND timestamp BETWEEN ? AND ?
        ''', (user_id, month_start.isoformat(), month_end.isoformat()))
        
        result = cursor.fetchone()
        conn.close()
        return result[0] if result[0] else 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения месячных расходов: {e}")
        return 0

def get_stats(user_id):
    """Получить общую статистику"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT SUM(amount) FROM expenses WHERE user_id = ?', (user_id,))
        total = cursor.fetchone()[0] or 0
        
        month_total = get_month_expenses(user_id)
        
        cursor.execute('''
            SELECT category, SUM(amount) as sum_amount, COUNT(*) as count
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY sum_amount DESC
        ''', (user_id,))
        
        categories = cursor.fetchall()
        conn.close()
        return total, month_total, categories
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return 0, 0, []

def get_stats_by_category(user_id, category):
    """Получить статистику по категории"""
    try:
        category = category.lower().capitalize()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT SUM(amount), COUNT(*), AVG(amount)
            FROM expenses
            WHERE user_id = ? AND category = ?
        ''', (user_id, category))
        
        result = cursor.fetchone()
        conn.close()
        
        return {
            'total': result[0] or 0,
            'count': result[1] or 0,
            'avg': result[2] or 0
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return {'total': 0, 'count': 0, 'avg': 0}

# ===== ХРАНЕНИЕ СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЯ =====
user_state = {}

def set_state(user_id, state):
    """Установить состояние пользователя"""
    user_state[user_id] = state

def get_state(user_id):
    """Получить состояние пользователя"""
    return user_state.get(user_id, None)

def clear_state(user_id):
    """Очистить состояние пользователя"""
    if user_id in user_state:
        del user_state[user_id]

# ===== КНОПКИ =====

def get_category_buttons(user_id):
    """Получить кнопки с категориями"""
    top = get_top_categories(user_id, 5)
    common = get_common_categories(user_id)
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    # Топ 5 категорий
    row1 = [telebot.types.KeyboardButton(f"🏷️ {cat}") for cat in top[:2]]
    row2 = [telebot.types.KeyboardButton(f"🏷️ {cat}") for cat in top[2:4]]
    row3 = [telebot.types.KeyboardButton(f"🏷️ {cat}") for cat in top[4:5]]
    
    if row1:
        markup.add(*row1)
    if row2:
        markup.add(*row2)
    if row3:
        markup.add(*row3)
    
    # Остальные категории
    if common:
        row4 = [telebot.types.KeyboardButton(f"🏷️ {cat}") for cat in common[:2]]
        row5 = [telebot.types.KeyboardButton(f"🏷️ {cat}") for cat in common[2:4]]
        if row4:
            markup.add(*row4)
        if row5:
            markup.add(*row5)
    
    markup.add(telebot.types.KeyboardButton("➕ Новая категория"))
    markup.add(telebot.types.KeyboardButton("⬅️ Назад"))
    
    return markup

def get_timezone_buttons():
    """Получить кнопки с тайм-зонами"""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    zones = list(TIMEZONES.keys())
    for i in range(0, len(zones), 3):
        row = [telebot.types.KeyboardButton(zones[j]) for j in range(i, min(i+3, len(zones)))]
        markup.add(*row)
    
    return markup

# ===== КОМАНДЫ БОТА =====

@bot.message_handler(commands=['start'])
def start(message):
    """Команда /start"""
    user = message.from_user
    
    msg = f"👋 Привет, {user.first_name}!\n\n🌍 Сначала выбери свой часовой пояс:"
    markup = get_timezone_buttons()
    bot.send_message(message.chat.id, msg, reply_markup=markup)
    set_state(user.id, 'choosing_timezone')
    logger.info(f"✅ Пользователь {user.id} начал выбор тайм-зоны")

@bot.message_handler(commands=['help'])
def help_command(message):
    """Команда /help"""
    msg = """
📚 **Доступные команды:**

💰 **/spend** — добавить расход через интерфейс кнопок
📊 **/stats** [категория] — статистика расходов
📋 **/today** [категория] — расходы за сегодня
📝 **/list** — все расходы с ID для редактирования
✏️ **/edit [ID]** — редактировать расход
🗑️ **/delete [ID]** — удалить расход
🏷️ **/categories** — список твоих категорий
🌍 **/timezone** — изменить часовой пояс
🔄 **/start** — начать заново
❓ **/help** — эта помощь
    """
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')

@bot.message_handler(commands=['spend'])
def spend_command(message):
    """Команда /spend"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    set_state(user.id, 'choosing_category')
    
    msg = "💰 Выбери категорию:"
    markup = get_category_buttons(user.id)
    bot.send_message(message.chat.id, msg, reply_markup=markup)

@bot.message_handler(commands=['list'])
def list_command(message):
    """Команда /list"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    expenses = get_all_expenses(user.id, 20)
    
    if not expenses:
        msg = "📋 Расходов нет"
        bot.send_message(message.chat.id, msg)
    else:
        msg = f"📋 Последние расходы ({len(expenses)}):\n\n"
        for exp_id, amount, category, desc, timestamp in expenses:
            time = datetime.fromisoformat(timestamp).strftime('%d.%m %H:%M')
            msg += f"#{exp_id}: {amount}₽ | {category} | {desc} | {time}\n"
        
        bot.send_message(message.chat.id, msg)
        
        # Предлагаем редактирование
        edit_msg = "Нажми на ID для редактирования или используй /edit [ID] или /delete [ID]"
        bot.send_message(message.chat.id, edit_msg)

@bot.message_handler(commands=['today'])
def today_command(message):
    """Команда /today"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    parts = message.text.split(maxsplit=1)
    
    if len(parts) > 1:
        category = parts[1]
        expenses = get_today_expenses_by_category(user.id, category)
        title = f"за сегодня по категории '{category}'"
    else:
        expenses = get_today_expenses(user.id)
        title = "за сегодня"
    
    if not expenses:
        msg = f"📋 Расходов {title} нет"
    else:
        total = sum(exp[1] for exp in expenses)
        msg = f"📋 **Расходы {title}** ({len(expenses)}, Итого: {total}₽)\n\n"
        for exp_id, amount, cat, desc, timestamp in expenses:
            time = datetime.fromisoformat(timestamp).strftime('%H:%M')
            msg += f"#{exp_id}: {amount}₽ | {cat} | {desc} | {time}\n"
    
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def stats_command(message):
    """Команда /stats"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    parts = message.text.split(maxsplit=1)
    
    if len(parts) > 1:
        category = parts[1]
        stats = get_stats_by_category(user.id, category)
        
        msg = f"""
📊 **По категории "{category}":**

💰 Всего: **{stats['total']}₽**
🔢 Расходов: **{stats['count']}**
📊 Средний: **{stats['avg']:.0f}₽**
        """
    else:
        total, month_total, categories = get_stats(user.id)
        
        msg = f"""
📊 **СТАТИСТИКА РАСХОДОВ**

💰 Всего расходов: **{total}₽**
📅 За этот месяц: **{month_total}₽**

🏆 **По категориям:**
"""
        
        if categories:
            for category, amount, count in categories:
                avg = amount / count if count > 0 else 0
                msg += f"\n  • {category}: {amount}₽ ({count} расходов, ср: {avg:.0f}₽)"
        else:
            msg += "\n  (Нет данных)"
    
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')

@bot.message_handler(commands=['categories'])
def categories_command(message):
    """Команда /categories"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    categories = get_user_categories_sorted(user.id)
    
    msg = "🏷️ **Твои категории:**\n\n"
    for i, cat in enumerate(categories, 1):
        msg += f"{i}. {cat}\n"
    
    msg += "\n📝 Используй /spend для добавления расхода"
    
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')

@bot.message_handler(commands=['timezone'])
def timezone_command(message):
    """Команда /timezone"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    msg = "🌍 Выбери свой часовой пояс:"
    markup = get_timezone_buttons()
    bot.send_message(message.chat.id, msg, reply_markup=markup)
    set_state(user.id, 'choosing_timezone')

@bot.message_handler(commands=['edit', 'delete'])
def edit_delete_handler(message):
    """Команды /edit и /delete"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    parts = message.text.split()
    
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Укажи ID расхода!\nПример: /edit 42")
        return
    
    try:
        expense_id = int(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, "❌ ID должен быть числом!")
        return
    
    expense = get_expense(expense_id, user.id)
    
    if not expense:
        bot.send_message(message.chat.id, "❌ Расход не найден!")
        return
    
    command = message.text.split()[0][1:]
    
    if command == 'delete':
        if delete_expense(expense_id):
            bot.send_message(message.chat.id, f"✅ Расход #{expense_id} удалён!")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка удаления!")
    else:
        exp_id, amount, category, description, timestamp = expense
        time = datetime.fromisoformat(timestamp).strftime('%d.%m %H:%M')
        
        msg = f"""
📝 **Расход #{exp_id}:**

💰 Сумма: {amount}₽
🏷️ Категория: {category}
📝 Описание: {description}
⏰ Время: {time}

Что редактировать?
        """
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('💰 Сумма', '🏷️ Категория')
        markup.add('📝 Описание', '⬅️ Отмена')
        
        bot.send_message(message.chat.id, msg, reply_markup=markup)
        set_state(user.id, f'editing_{expense_id}')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Обработка текстовых сообщений"""
    user = message.from_user
    text = message.text
    save_user(user.id, user.username, user.first_name)
    
    state = get_state(user.id)
    
    # Выбор тайм-зоны
    if state == 'choosing_timezone':
        if text in TIMEZONES:
            update_user_timezone(user.id, text)
            save_user(user.id, user.username, user.first_name, text)
            initialize_user_categories(user.id)
            
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add('💰 Добавить расход', '📊 Статистика')
            markup.add('📋 Сегодня', '📝 Все расходы')
            markup.add('❓ Помощь')
            
            msg = f"✅ Тайм-зона установлена на {text}\n\n💰 Теперь я готов помогать тебе отслеживать расходы!"
            bot.send_message(message.chat.id, msg, reply_markup=markup)
            clear_state(user.id)
            logger.info(f"✅ Пользователь {user.id} выбрал тайм-зону {text}")
        else:
            bot.send_message(message.chat.id, "❌ Выбери тайм-зону из предложенных")
        return
    
    # Основное меню
    if text == '💰 Добавить расход':
        spend_command(message)
        return
    elif text == '📊 Статистика':
        msg = "📊 Выбери тип статистики:\n\n[📊 Общая] [🏷️ По категории]"
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('📊 Общая', '🏷️ По категории')
        markup.add('⬅️ Назад')
        bot.send_message(message.chat.id, msg, reply_markup=markup)
        set_state(user.id, 'choosing_stats')
        return
    elif text == '📊 Общая':
        stats_command(message)
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('💰 Добавить расход', '📊 Статистика')
        markup.add('📋 Сегодня', '📝 Все расходы')
        markup.add('❓ Помощь')
        bot.send_message(message.chat.id, "Выбери действие:", reply_markup=markup)
        clear_state(user.id)
        return
    elif text == '🏷️ По категории':
        categories = get_user_categories_sorted(user.id)
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        for cat in categories:
            markup.add(telebot.types.KeyboardButton(cat))
        markup.add('⬅️ Назад')
        bot.send_message(message.chat.id, "Выбери категорию:", reply_markup=markup)
        set_state(user.id, 'choosing_category_for_stats')
        return
    elif state == 'choosing_category_for_stats':
        if text != '⬅️ Назад':
            stats_command(telebot.util.util.CTypes(text=f'/stats {text}', message_id=message.message_id))
            bot.edit_message_text("📊 Выбери тип статистики:\n\n[📊 Общая] [🏷️ По категории]", 
                                 message.chat.id, message.message_id)
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('💰 Добавить расход', '📊 Статистика')
        markup.add('📋 Сегодня', '📝 Все расходы')
        markup.add('❓ Помощь')
        bot.send_message(message.chat.id, "Выбери действие:", reply_markup=markup)
        clear_state(user.id)
        return
    elif text == '📋 Сегодня':
        today_command(message)
        return
    elif text == '📝 Все расходы':
        list_command(message)
        return
    elif text == '🏷️ Категории':
        categories_command(message)
        return
    elif text == '❓ Помощь':
        help_command(message)
        return
    elif text == '⬅️ Назад' or text == '⬅️ Отмена':
        clear_state(user.id)
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('💰 Добавить расход', '📊 Статистика')
        markup.add('📋 Сегодня', '📝 Все расходы')
        markup.add('❓ Помощь')
        bot.send_message(message.chat.id, "✅ Отмена", reply_markup=markup)
        return
    
    # Выбор категории
    if state == 'choosing_category':
        if text.startswith('🏷️ '):
            category = text.replace('🏷️ ', '')
            set_state(user.id, f'waiting_amount_{category}')
            bot.send_message(message.chat.id, "💰 Введи сумму расхода:")
        elif text == '➕ Новая категория':
            set_state(user.id, 'adding_category')
            bot.send_message(message.chat.id, "📝 Введи название новой категории:")
        else:
            bot.send_message(message.chat.id, "❌ Выбери категорию из предложенных")
        return
    
    # Добавление новой категории
    if state == 'adding_category':
        if add_category(user.id, text):
            set_state(user.id, f'waiting_amount_{text}')
            bot.send_message(message.chat.id, f"✅ Категория '{text}' добавлена!\n\n💰 Введи сумму расхода:")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка добавления категории!")
        return
    
    # Ввод суммы
    if state and state.startswith('waiting_amount_'):
        category = state.replace('waiting_amount_', '')
        try:
            amount = float(text)
            set_state(user.id, f'waiting_description_{category}_{amount}')
            bot.send_message(message.chat.id, "📝 Введи описание (или 'Пропустить'):")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Сумма должна быть числом!")
        return
    
    # Ввод описания
    if state and state.startswith('waiting_description_'):
        parts = state.replace('waiting_description_', '').rsplit('_', 1)
        category = parts[0]
        amount = float(parts[1])
        
        description = "Без описания" if text.lower() == 'пропустить' else text
        
        expense_id = add_expense(user.id, amount, category, description)
        
        if expense_id:
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add('💰 Добавить расход', '📊 Статистика')
            markup.add('📋 Сегодня', '📝 Все расходы')
            markup.add('❓ Помощь')
            
            msg = f"""
✅ **Расход добавлен!**

💰 Сумма: {amount}₽
🏷️ Категория: {category}
📝 Описание: {description}
ID: {expense_id}
            """
            bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode='Markdown')
            clear_state(user.id)
            logger.info(f"✅ Расход {amount}₽ добавлен пользователем {user.id}")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при добавлении расхода!")
        return
    
    # Редактирование расхода
    if state and state.startswith('editing_'):
        expense_id = int(state.replace('editing_', ''))
        
        if text == '💰 Сумма':
            set_state(user.id, f'editing_amount_{expense_id}')
            bot.send_message(message.chat.id, "Введи новую сумму:")
        elif text == '🏷️ Категория':
            set_state(user.id, f'editing_category_{expense_id}')
            bot.send_message(message.chat.id, "Введи новую категорию:")
        elif text == '📝 Описание':
            set_state(user.id, f'editing_description_{expense_id}')
            bot.send_message(message.chat.id, "Введи новое описание:")
        else:
            bot.send_message(message.chat.id, "❌ Выбери что редактировать")
        return
    
    # Редактирование суммы
    if state and state.startswith('editing_amount_'):
        expense_id = int(state.replace('editing_amount_', ''))
        try:
            amount = float(text)
            if edit_expense(expense_id, amount=amount):
                bot.send_message(message.chat.id, f"✅ Сумма обновлена на {amount}₽!")
                clear_state(user.id)
            else:
                bot.send_message(message.chat.id, "❌ Ошибка обновления!")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введи число!")
        return
    
    # Редактирование категории
    if state and state.startswith('editing_category_'):
        expense_id = int(state.replace('editing_category_', ''))
        if edit_expense(expense_id, category=text):
            bot.send_message(message.chat.id, f"✅ Категория обновлена на '{text}'!")
            clear_state(user.id)
        else:
            bot.send_message(message.chat.id, "❌ Ошибка обновления!")
        return
    
    # Редактирование описания
    if state and state.startswith('editing_description_'):
        expense_id = int(state.replace('editing_description_', ''))
        if edit_expense(expense_id, description=text):
            bot.send_message(message.chat.id, f"✅ Описание обновлено на '{text}'!")
            clear_state(user.id)
        else:
            bot.send_message(message.chat.id, "❌ Ошибка обновления!")
        return
    
    bot.send_message(message.chat.id, "❓ Команда не понята. Нажми /help для справки")

# ===== ЗАПУСК БОТА =====

if __name__ == '__main__':
    logger.info("==================================================")
    logger.info("💰 Бот отслеживания расходов запущен!")
    logger.info("==================================================")
    
    init_db()
    
    try:
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
