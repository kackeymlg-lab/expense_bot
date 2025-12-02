import telebot
import os
import logging
from datetime import datetime
import sqlite3
from dotenv import load_dotenv

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
            budget REAL DEFAULT 0,
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
    
    conn.commit()
    conn.close()
    logger.info("✅ БД инициализирована")

def save_user(user_id, username, first_name):
    """Сохранить пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, first_name))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения пользователя: {e}")

def add_expense(user_id, amount, category, description):
    """Добавить расход"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO expenses (user_id, amount, category, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, category, description))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления расхода: {e}")
        return False

def get_today_expenses(user_id):
    """Получить расходы за день"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT amount, category, description, timestamp
            FROM expenses
            WHERE user_id = ? AND DATE(timestamp) = DATE('now')
            ORDER BY timestamp DESC
        ''', (user_id,))
        expenses = cursor.fetchall()
        conn.close()
        return expenses
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов: {e}")
        return []

def get_month_expenses(user_id):
    """Получить расходы за месяц"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT SUM(amount) FROM expenses
            WHERE user_id = ? AND strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result[0] else 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения месячных расходов: {e}")
        return 0

def get_stats(user_id):
    """Получить статистику"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Всего расходов
        cursor.execute('SELECT SUM(amount) FROM expenses WHERE user_id = ?', (user_id,))
        total = cursor.fetchone()[0]
        
        # За месяц
        month_total = get_month_expenses(user_id)
        
        # По категориям
        cursor.execute('''
            SELECT category, SUM(amount) as sum_amount
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

# ===== КОМАНДЫ БОТА =====

@bot.message_handler(commands=['start'])
def start(message):
    """Команда /start"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('💰 Добавить расход', '📊 Статистика')
    markup.add('📋 Сегодня', '❓ Помощь')
    
    msg = f"👋 Привет, {user.first_name}!\n\nЯ помогу отслеживать твои расходы 💰"
    bot.send_message(message.chat.id, msg, reply_markup=markup)
    logger.info(f"✅ Пользователь {user.id} начал чат")

@bot.message_handler(commands=['help'])
def help_command(message):
    """Команда /help"""
    msg = """
📚 **Доступные команды:**

💰 **/spend [сумма] [категория] [описание]** — добавить расход
   Пример: `/spend 500 Кофе Латте в кафе`

📊 **/stats** — статистика расходов
📋 **/today** — расходы за день
🔄 **/start** — начать заново
❓ **/help** — эта помощь

**Категории:** Еда, Транспорт, Развлечения, Подписки, Другое
    """
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')

@bot.message_handler(commands=['spend'])
def spend_command(message):
    """Команда /spend"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    try:
        parts = message.text.split(maxsplit=3)
        if len(parts) < 3:
            bot.send_message(message.chat.id, 
                "❌ Использование: /spend [сумма] [категория] [описание]\n"
                "Пример: /spend 500 Кофе Латте в кафе")
            return
        
        amount = float(parts[1])
        category = parts[2]
        description = parts[3] if len(parts) > 3 else "Без описания"
        
        if add_expense(user.id, amount, category, description):
            msg = f"✅ Расход добавлен!\n\n💰 Сумма: {amount}₽\n🏷️ Категория: {category}\n📝 Описание: {description}"
            bot.send_message(message.chat.id, msg)
            logger.info(f"✅ Расход {amount}₽ добавлен пользователем {user.id}")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при добавлении расхода")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Сумма должна быть числом!\nПример: /spend 500 Кофе Латте")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['today'])
def today_command(message):
    """Команда /today"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    expenses = get_today_expenses(user.id)
    
    if not expenses:
        msg = "📋 Расходов сегодня нет"
    else:
        total = sum(exp[0] for exp in expenses)
        msg = f"📋 **Расходы за сегодня** ({len(expenses)})\n\n"
        for amount, category, desc, timestamp in expenses:
            time = datetime.fromisoformat(timestamp).strftime('%H:%M')
            msg += f"⏰ {time} | 💰 {amount}₽ | {category} - {desc}\n"
        msg += f"\n**Итого: {total}₽**"
    
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def stats_command(message):
    """Команда /stats"""
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    
    total, month_total, categories = get_stats(user.id)
    
    msg = f"""
📊 **СТАТИСТИКА РАСХОДОВ**

💰 Всего расходов: **{total}₽** (или {total/1000:.1f}K)
📅 За этот месяц: **{month_total}₽**

🏆 **По категориям:**
"""
    
    if categories:
        for category, amount in categories:
            msg += f"\n  • {category}: {amount}₽"
    else:
        msg += "\n  (Нет данных)"
    
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Обработка текстовых сообщений"""
    user = message.from_user
    text = message.text
    save_user(user.id, user.username, user.first_name)
    
    if text == '💰 Добавить расход':
        msg = "💰 Отправь расход в формате:\n/spend [сумма] [категория] [описание]\n\nПример:\n/spend 500 Кофе Латте в кафе"
        bot.send_message(message.chat.id, msg)
    elif text == '📊 Статистика':
        stats_command(message)
    elif text == '📋 Сегодня':
        today_command(message)
    elif text == '❓ Помощь':
        help_command(message)
    else:
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
