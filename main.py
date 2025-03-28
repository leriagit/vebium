import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, CallbackContext
from telegram.ext import filters
import asyncio
import sqlite3

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            name TEXT,
            is_admin INTEGER
        )
    ''')
    conn.commit()
    conn.close()

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
REGISTER, NAME, MAIN_MENU, UPLOAD_ASSIGNMENT, UPLOAD_THEORY, SEND_REMINDER, SEND_VIDEO = range(7)

# Структура для хранения данных учеников
students = {}
admins = ['vcshss']  # Ник администратора

# Функция старта
async def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    students[user.id] = {"nickname": "", "name": ""}

    if user.username in admins:
        students[user.id]["is_admin"] = True
        await update.message.reply_text("Привет, админ! Введите ваш ник:")
    else:
        students[user.id]["is_admin"] = False
        await update.message.reply_text("Добро пожаловать! Введите ваш ник:")

    return REGISTER


# Регистрация ника
async def register_nickname(update: Update, context: CallbackContext):
    user = update.message.from_user
    students[user.id]["nickname"] = update.message.text
    await update.message.reply_text(f"Ваш ник: {update.message.text}\nТеперь введите ваше имя:")
    return NAME


# Регистрация имени и показ меню
async def register_name(update: Update, context: CallbackContext):
    user = update.message.from_user
    students[user.id]["name"] = update.message.text
    await update.message.reply_text("Вы успешно зарегистрированы!")

    if students[user.id]["is_admin"]:
        await main_menu_admin(update)
    else:
        await main_menu_student(update)

    return MAIN_MENU

def add_user(user_id, username, name, is_admin=False):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (id, username, name, is_admin) VALUES (?, ?, ?, ?)",
                       (user_id, username, name, int(is_admin)))
        conn.commit()
    except sqlite3.IntegrityError:
        print("Пользователь уже есть в базе.")
    finally:
        conn.close()

def is_user_registered(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user is not None

def get_students():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE is_admin=0")
    students = [row[0] for row in cursor.fetchall()]
    conn.close()
    return students

def is_admin(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None and result[0] == 1

# Меню для администратора (ReplyKeyboardMarkup)
async def main_menu_admin(update: Update):
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📅 Напоминание о созвоне"), KeyboardButton("📹 Отправить видео созвона")],
    ], resize_keyboard=True)

    await update.message.reply_text("Выберите действие:", reply_markup=keyboard)

# Обработчик выбора админа
async def handle_admin_choice(update: Update, context: CallbackContext):
    text = update.message.text

    if text == "📅 Напоминание о созвоне":
        await update.message.reply_text("Введите текст напоминания:")
        return SEND_REMINDER  # Устанавливаем состояние
    elif text == "📹 Отправить видео созвона":
        return await send_video(update, context)

    return MAIN_MENU



# Обработчик текста напоминания
async def handle_reminder(update: Update, context: CallbackContext):
    reminder_text = update.message.text

    # Рассылаем напоминание всем ученикам
    for student_id, student_data in students.items():
        if not student_data["is_admin"]:  # Только ученикам
            await context.bot.send_message(student_id, text=f"📢 Напоминание: {reminder_text}")

    await update.message.reply_text("✅ Напоминание отправлено всем ученикам.")
    return MAIN_MENU

# Меню для ученика (ReplyKeyboardMarkup)
async def main_menu_student(update: Update):
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📝 Разобрать задание"), KeyboardButton("📚 Разобрать теорию")],
    ], resize_keyboard=True)

    await update.message.reply_text("Выберите действие:", reply_markup=keyboard)


# Обработчик выбора ученика
async def handle_student_choice(update: Update, context: CallbackContext):
    text = update.message.text

    if text == "📝 Разобрать задание":
        await update.message.reply_text("Пришлите фото задания и описание проблемы.")
        return UPLOAD_ASSIGNMENT
    elif text == "📚 Разобрать теорию":
        await update.message.reply_text("Опишите, что непонятно по теории.")
        return UPLOAD_THEORY


# Обработчик задания
async def upload_assignment(update: Update, context: CallbackContext):
    user = update.message.from_user
    if update.message.photo:
        photo = update.message.photo[-1].file_id
        context.user_data['photo'] = photo
        context.user_data['description'] = update.message.caption or "Нет описания"
        await update.message.reply_text("Задание отправлено куратору.")

        for student_id in students:
            if students[student_id]["is_admin"]:
                await context.bot.send_photo(
                    student_id,
                    photo=photo,
                    caption=f"Задание от {students[user.id]['name']} ({students[user.id]['nickname']}):\n{context.user_data['description']}"
                )
    else:
        await update.message.reply_text("Пришлите фотографию задания.")

    return MAIN_MENU


# Обработчик теории
async def upload_theory(update: Update, context: CallbackContext):
    user = update.message.from_user
    context.user_data['theory_question'] = update.message.text
    await update.message.reply_text("Ваш вопрос по теории принят.")

    for student_id in students:
        if students[student_id]["is_admin"]:
            await context.bot.send_message(
                student_id,
                f"Вопрос от {students[user.id]['name']} ({students[user.id]['nickname']}):\n{context.user_data['theory_question']}"
            )

    return MAIN_MENU


# Напоминание о созвоне
async def send_reminder(update: Update, context: CallbackContext):
    await update.message.reply_text("Введите текст напоминания:")
    return SEND_REMINDER


# Обработчик текста напоминания
async def handle_reminder(update: Update, context: CallbackContext):
    reminder_text = update.message.text
    for student_id in students:
        if not students[student_id]["is_admin"]:
            await context.bot.send_message(student_id, text=reminder_text)

    await update.message.reply_text("Напоминание отправлено.")
    return MAIN_MENU


# Отправка видео созвона
async def send_video(update: Update, context: CallbackContext):
    await update.message.reply_text("Отправьте видео созвона.")
    return SEND_VIDEO


# Обработчик видео
async def handle_video(update: Update, context: CallbackContext):
    video = update.message.video
    context.user_data['video_file'] = video.file_id
    await update.message.reply_text("Введите название видеозаписи.")
    return SEND_VIDEO


# Обработчик названия видео
async def handle_video_name(update: Update, context: CallbackContext):
    video_name = update.message.text
    for student_id in students:
        if not students[student_id]["is_admin"]:
            await context.bot.send_video(student_id, video=context.user_data['video_file'], caption=f"Запись созвона: {video_name}")

    await update.message.reply_text("Видео отправлено.")
    return MAIN_MENU


# Завершение
async def done(update: Update, context: CallbackContext):
    return MAIN_MENU


async def main():
    application = Application.builder().token("7722855093:AAGCMwpeNhtcuMp9ra_b1PsRGeTjmPl6wRA").build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REGISTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nickname)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_student_choice)],
            UPLOAD_ASSIGNMENT: [MessageHandler(filters.PHOTO & filters.CAPTION, upload_assignment)],
            UPLOAD_THEORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_theory)],
            SEND_REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reminder)],  # Должен быть тут!
            SEND_VIDEO: [
                MessageHandler(filters.VIDEO, handle_video),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_name)
            ],
        },
        fallbacks=[CommandHandler('done', done)],
    )

    application.add_handler(conv_handler)
    await application.run_polling()


if __name__ == '__main__':
    import nest_asyncio

    nest_asyncio.apply()
    asyncio.run(main())