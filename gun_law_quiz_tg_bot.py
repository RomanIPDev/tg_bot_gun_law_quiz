import json
import os
import logging
import time
import random
import asyncio
import signal
from collections import defaultdict
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Настройка логгирования банов
ban_logger = logging.getLogger('ban_logger')
ban_logger.setLevel(logging.INFO)
ban_handler = logging.FileHandler('ban.log', encoding='utf-8')
ban_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
ban_logger.addHandler(ban_handler)

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не задана!")

# ID администратора
ADMIN_ID = 330336095

# Конфигурация защиты от флуда
FLOOD_CONFIG = {
    'MESSAGE_LIMIT': 20,
    'CALLBACK_LIMIT': 20,
    'TIME_WINDOW': 20,
    'BASE_BAN_TIME': 30,
    'REPEAT_BAN_MULTIPLIER': 2,
    'MAX_BAN_TIME': 86400,
    'REPEAT_BAN_WINDOW': 180
}

user_flood_data = defaultdict(lambda: {
    'message_count': 0,
    'callback_count': 0,
    'last_message_time': 0,
    'last_callback_time': 0,
    'banned_until': 0,
    'last_ban_end_time': 0,
    'ban_count': 0,
})

# Загрузка вопросов
QUESTIONS = []
def load_questions():
    global QUESTIONS
    try:
        if not os.path.exists("questions.json"):
            raise FileNotFoundError("Файл questions.json не найден")
        
        with open("questions.json", "r", encoding="utf-8") as f:
            QUESTIONS = json.load(f)
        
        if not isinstance(QUESTIONS, list):
            raise ValueError("questions.json должен содержать список вопросов")
        
        if not QUESTIONS:
            raise ValueError("Файл questions.json не содержит вопросов")
        
        logger.info(f"Успешно загружено {len(QUESTIONS)} вопросов")
        
    except Exception as e:
        logger.error(f"Ошибка загрузки вопросов: {e}")
        raise

load_questions()

async def notify_admin(message):
    try:
        bot = Bot(token=TOKEN)
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=message
        )
        logger.info(f"Уведомление отправлено администратору: {message}")
        await bot.close()
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления администратору: {e}")

def is_flooding(user_id: int, action_type: str) -> bool:
    user_data = user_flood_data[user_id]
    current_time = time.time()
    
    if current_time < user_data['banned_until']:
        return True
    
    if current_time - user_data['last_ban_end_time'] > FLOOD_CONFIG['REPEAT_BAN_WINDOW']:
        user_data['ban_count'] = 0
    
    if current_time - user_data[f'last_{action_type}_time'] > FLOOD_CONFIG['TIME_WINDOW']:
        user_data[f'{action_type}_count'] = 0
    
    user_data[f'{action_type}_count'] += 1
    user_data[f'last_{action_type}_time'] = current_time
    
    if user_data[f'{action_type}_count'] > FLOOD_CONFIG[f'{action_type.upper()}_LIMIT']:
        ban_duration = FLOOD_CONFIG['BASE_BAN_TIME'] * (FLOOD_CONFIG['REPEAT_BAN_MULTIPLIER'] ** user_data['ban_count'])
        
        if ban_duration > FLOOD_CONFIG['MAX_BAN_TIME']:
            ban_duration = FLOOD_CONFIG['MAX_BAN_TIME']
        
        user_data['banned_until'] = current_time + ban_duration
        user_data['last_ban_end_time'] = user_data['banned_until']
        user_data['ban_count'] += 1
        
        logger.warning(
            f"Пользователь {user_id} заблокирован за флуд на {ban_duration} сек. "
            f"Счетчик нарушений: {user_data['ban_count']}"
        )
        
        ban_logger.info(
            f"USER_ID: {user_id} - "
            f"ACTION: {action_type} - "
            f"DURATION: {ban_duration} сек - "
            f"BAN_COUNT: {user_data['ban_count']} - "
            f"IP: N/A"
        )
        return True
    
    return False

async def check_ban(update: Update, context: ContextTypes.DEFAULT_TYPE, action_type: str) -> bool:
    user_id = update.effective_user.id
    if is_flooding(user_id, action_type):
        ban_end = user_flood_data[user_id]['banned_until']
        bansec = max(1, int(ban_end - time.time()))
        
        if update.callback_query:
            await update.callback_query.answer(
                f"⚠️ Слишком много запросов! Подождите {bansec} секунд.",
                show_alert=True
            )
        else:
            msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ Слишком много запросов! Подождите {bansec} секунд."
            )
            await asyncio.sleep(5)
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=msg.message_id
                )
            except Exception:
                pass
        return True
    return False

def get_answer_status(user_data, q_index, option_index):
    if user_data["answers"][q_index] is None:
        return None
    
    question = QUESTIONS[q_index]
    if option_index == question["correct"]:
        return 'correct'
    elif option_index == user_data["answers"][q_index]:
        return 'wrong'
    return None

def get_emoji_by_progress(correct, total):
    if total == 0:
        return "❓"

    percent = (correct / total) * 100
    thresholds = [
        (0, "🤔"), (5, "🤨"), (10, "🥺"), (15, "😢"), (20, "😞"),
        (25, "😕"), (30, "🙁"), (35, "😐"), (40, "🙂"), (45, "😌"),
        (50, "😊"), (55, "😃"), (60, "😄"), (65, "😁"), (70, "😆"),
        (75, "🤩"), (80, "🥳"), (85, "🤪"), (90, "😍"), (95, "🥰")
    ]
    return next((emoji for thresh, emoji in thresholds if percent <= thresh), "🤯")

def get_user_stats(answers):
    try:
        correct = sum(1 for i, a in enumerate(answers) if a == QUESTIONS[i]["correct"])
        answered = sum(1 for a in answers if a is not None)
        total = len(QUESTIONS)
        last_emoji = get_emoji_by_progress(correct, total)
        accuracy = correct / total * 100 if total > 0 else 0
        return correct, answered, total, last_emoji, accuracy
    except Exception as e:
        logger.error(f"Ошибка подсчета статистики: {e}")
        return 0, 0, 0, "❓", 0

def format_question_text(user_data, q_index):
    real_index = user_data["question_order"][q_index]
    question = QUESTIONS[real_index]
    
    correct, answered, total, last_emoji, accuracy = get_user_stats(user_data["answers"])
    remaining = total - answered
    
    if user_data["random_mode"]:
        progress = f"{q_index + 1}/{len(user_data['question_order'])}"
        mode_icon = " 🔀"
    else:
        progress = f"{real_index + 1}/{total}"
        mode_icon = " ▶️"
    
    progress_emoji = get_emoji_by_progress(correct, total)
    
    current_answer_emoji = ""
    if user_data["answers"][real_index] is not None:
        if user_data["answers"][real_index] == question["correct"]:
            current_answer_emoji = " 👍"
        else:
            current_answer_emoji = " 👎"
    
    emojis = f"{progress_emoji}{current_answer_emoji}"
    stats = f"✅ {correct} ❌ {answered - correct} 📝 {remaining} {emojis:>25}"

    text = (
        f"Вопрос {progress}{mode_icon}\n\n"
        f"{question['question']}\n\n"
    )
    
    for i, option in enumerate(question["options"]):
        status = ""
        answer_status = get_answer_status(user_data, real_index, i)
        if answer_status == 'correct':
            status = " ✅"
        elif answer_status == 'wrong':
            status = " ❌"
        text += f"{i+1}. {option}{status}\n"
    
    text += f"\n📊: {stats}"
    
    if user_data["answers"][real_index] is not None:
        explanation = question.get("explanation", "Пояснение отсутствует.")
        text += f"\n\nℹ️ {explanation}"
    
    return text

def get_question_markup(user_data, q_index):
    try:
        buttons = []
        real_index = user_data["question_order"][q_index]
        question = QUESTIONS[real_index]
        
        if user_data["answers"][real_index] is None:
            options_row = []
            for i in range(len(question["options"])):
                button_text = str(i+1)
                options_row.append(InlineKeyboardButton(
                    button_text,
                    callback_data=f"answer:{q_index}:{i}"
                ))
            buttons.append(options_row)
        
        nav_row1 = [
            InlineKeyboardButton("← Предыдущий", callback_data=f"nav:prev"),
            InlineKeyboardButton("📝 Перейти", callback_data="input_number"),
            InlineKeyboardButton("Следующий →", callback_data=f"nav:next")
        ]
        buttons.append(nav_row1)

        if user_data.get("retry_mode", False):
            retry_answers = [user_data["answers"][i] for i in user_data["wrong_questions"]]
            if all(a is not None for a in retry_answers):
                buttons.append([InlineKeyboardButton("🏁 Завершить повторение", callback_data="finish_retry")])
        else:
            if all(a is not None for a in user_data["answers"]):
                buttons.append([InlineKeyboardButton("🏁 Завершить тест", callback_data="finish")])

        return InlineKeyboardMarkup(buttons)

    except Exception as e:
        logger.error(f"Ошибка генерации клавиатуры: {e}")
        return InlineKeyboardMarkup([])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context, 'message'):
        return
    
    try:
        if not QUESTIONS:
            error_msg = "⚠️ Вопросы не загружены! Бот не может работать."
            if update.message:
                await update.message.reply_text(error_msg)
            elif update.callback_query:
                await update.callback_query.message.reply_text(error_msg)
            await notify_admin("CRITICAL: Вопросы не загружены!")
            return
        
        context.user_data.clear()
        context.user_data["current"] = 0
        context.user_data["answers"] = [None] * len(QUESTIONS)
        context.user_data["waiting_for_input"] = False
        context.user_data["random_mode"] = False
        context.user_data["question_order"] = list(range(len(QUESTIONS)))
        context.user_data["navigation_history"] = [0]
        context.user_data["retry_mode"] = False
        context.user_data["original_wrongs"] = []  # Инициализируем список исходных ошибок

        text = format_question_text(context.user_data, 0)
        reply_markup = get_question_markup(context.user_data, 0)

        if update.message:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                text,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        if update.message:
            await update.message.reply_text(
                "⚠️ Произошла ошибка при запуске теста. Попробуйте позже."
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "⚠️ Произошла ошибка при запуске теста. Попробуйте позже."
            )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context, 'message'):
        return
    
    if update.message:
        await update.message.reply_text(
            "🔄 Начинаем новый тест! Ваш предыдущий прогресс был сброшен."
        )
    await start(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context, 'message'):
        return
    
    commands_list = [
        "/start - Начать тест",
        "/quiz - Перезапустить тест",
        "/normal_mode - Обычный режим вопросов",
        "/random_mode - Случайный порядок вопросов",
        "/help - Помощь и инструкции"
    ]
    
    text = (
        "ℹ️ Команды бота:\n\n" +
        "\n".join(commands_list) +
        "\n\nКак пользоваться:\n"
        "1. Начните тест командой /start\n"
        "2. Отвечайте на вопросы, выбирая варианты ответов\n"
        "3. Используйте кнопки навигации для перемещения между вопросами\n"
        "4. Для перехода к конкретному вопросу нажмите '📝 Перейти' и введите номер\n"
        "5. Используйте команды для переключения режимов\n"
        "6. После ответа на все вопросы завершите тест\n\n"
        "В тесте содержится 106 вопросов, из которых:\n"
        "38 вопросов — к правовой подготовке (законодательство, правила хранения, оборота, ответственности и применения оружия).\n"
        "68 вопросов относятся к огневой подготовке (устройство оружия, баллистика, техника стрельбы, безопасность и действия при стрельбе).\n\n"
        "Ключевые детали процедуры сдачи экзамена:\n"
        "1. Периодичность: Экзамен сдается каждые 5 лет одновременно с продлением разрешения на травматическое оружие.\n"
        "2. Содержание экзамена:\n"
        "Теоретическая часть: Компьютерное тестирование из 10 вопросов (допускается 1 ошибка). Время выполнения — 30 минут .\n"
        "Практическая часть: Стрельба из короткоствольного и длинноствольного оружия (по 3 выстрела каждого типа). Выполняются три упражнения, включая базовые действия без стрельбы.\n"
    )
    
    if update.message:
        await update.message.reply_text(text)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text)

async def reload_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context, 'message'):
        return
    
    try:
        load_questions()
        if update.message:
            await update.message.reply_text(
                "🔄 Вопросы успешно перезагружены!\n"
                f"Загружено {len(QUESTIONS)} вопросов."
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "🔄 Вопросы успешно перезагружены!\n"
                f"Загружено {len(QUESTIONS)} вопросов."
            )
    except Exception as e:
        logger.error(f"Ошибка перезагрузки вопросов: {e}")
        if update.message:
            await update.message.reply_text(
                f"⚠️ Ошибка перезагрузки вопросов: {e}"
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                f"⚠️ Ошибка перезагрузки вопросов: {e}"
            )

async def normal_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context, 'message'):
        return
    
    try:
        user_data = context.user_data
        
        if "random_mode" not in user_data:
            user_data["random_mode"] = True
        
        if not user_data["random_mode"]:
            return
            
        user_data["random_mode"] = False
        
        if "answers" in user_data:
            current_real_index = user_data["question_order"][user_data["current"]]
            user_data["question_order"] = list(range(len(QUESTIONS)))
            user_data["current"] = current_real_index
            
            text = format_question_text(user_data, user_data["current"])
            reply_markup = get_question_markup(user_data, user_data["current"])
            
            if update.message:
                await update.message.reply_text(
                    text,
                    reply_markup=reply_markup
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    text,
                    reply_markup=reply_markup
                )
    except Exception as e:
        logger.error(f"Ошибка переключения режима: {e}")

async def random_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context, 'message'):
        return
    
    try:
        user_data = context.user_data
        
        if "random_mode" not in user_data:
            user_data["random_mode"] = False
        
        if user_data["random_mode"]:
            return
            
        user_data["random_mode"] = True
        
        if "answers" in user_data:
            current_real_index = user_data["question_order"][user_data["current"]]
            
            new_order = list(range(len(QUESTIONS)))
            random.shuffle(new_order)
            user_data["question_order"] = new_order
            
            new_index = new_order.index(current_real_index)
            user_data["current"] = new_index
            
            text = format_question_text(user_data, new_index)
            reply_markup = get_question_markup(user_data, new_index)
            
            if update.message:
                await update.message.reply_text(
                    text,
                    reply_markup=reply_markup
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    text,
                    reply_markup=reply_markup
                )
    except Exception as e:
        logger.error(f"Ошибка переключения режима: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if await check_ban(update, context, 'callback'):
        return

    await query.answer()

    try:
        user_data = context.user_data
        
        if "answers" not in user_data:
            await query.edit_message_text(
                "⚠️ Сессия устарела. Нажмите /start для начала новой теста."
            )
            return

        data = query.data
        if ":" in data:
            parts = data.split(":")
            action = parts[0]
        else:
            action = data

        if action == "command":
            command_name = parts[1]
            
            command_handlers = {
                "start": start,
                "quiz": quiz,
                "normal_mode": normal_mode,
                "random_mode": random_mode,
                "help": help_command
            }
            
            if command_name in command_handlers:
                await query.message.delete()
                await command_handlers[command_name](query, context)
            return

        if action == "answer":
            q_index = int(parts[1])
            answer_index = int(parts[2])
            real_index = user_data["question_order"][q_index]
            question = QUESTIONS[real_index]

            if user_data["answers"][real_index] is not None:
                await query.answer("Вы уже ответили на этот вопрос.")
                return

            user_data["answers"][real_index] = answer_index
            
            text = format_question_text(user_data, q_index)
            reply_markup = get_question_markup(user_data, q_index)

            await query.edit_message_text(
                text,
                reply_markup=reply_markup
            )
            
            if user_data.get("retry_mode", False):
                retry_answers = [user_data["answers"][i] for i in user_data["wrong_questions"]]
                if all(a is not None for a in retry_answers):
                    await finish_retry_screen(query, context, user_data)

        elif action == "nav":
            direction = parts[1]
            user_data = context.user_data
            
            if user_data["random_mode"]:
                history = user_data["navigation_history"]
                current_index = history[-1]
                
                if direction == "next":
                    unanswered_indices = [i for i in range(len(QUESTIONS)) 
                                    if user_data["answers"][i] is None]
                    
                    if not unanswered_indices:
                        await query.answer("Все вопросы отвечены!")
                        return
                    
                    new_question_index = random.choice(unanswered_indices)
                    new_index_in_order = user_data["question_order"].index(new_question_index)
                    user_data["current"] = new_index_in_order
                    history.append(new_index_in_order)
                else:
                    if len(history) > 1:
                        history.pop()
                        prev_index = history[-1]
                        user_data["current"] = prev_index
                    else:
                        await query.answer("Это первый вопрос")
                        return
            else:
                if direction == "next":
                    new_index = user_data["current"] + 1
                    if new_index >= len(user_data["question_order"]):
                        await query.answer("Это последний вопрос")
                        return
                    user_data["current"] = new_index
                else:
                    new_index = user_data["current"] - 1
                    if new_index < 0:
                        await query.answer("Это первый вопрос")
                        return
                    user_data["current"] = new_index
            
            text = format_question_text(user_data, user_data["current"])
            reply_markup = get_question_markup(user_data, user_data["current"])
            
            await query.edit_message_text(
                text,
                reply_markup=reply_markup
            )
            
        elif action == "input_number":
            user_data["waiting_for_input"] = True
            user_data["edit_message_id"] = query.message.message_id
            user_data["original_text"] = query.message.text
            user_data["original_markup"] = query.message.reply_markup
            
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                "ℹ️ Введите номер вопроса для перехода:",
                reply_markup=query.message.reply_markup
            )
            await query.answer("Введите номер вопроса в чат")
            
        elif action == "finish":
            c, a, t, _, accuracy = get_user_stats(user_data["answers"])

            wrong_answers = []
            for i, answer in enumerate(user_data["answers"]):
                if answer is not None and answer != QUESTIONS[i]["correct"]:
                    wrong_answers.append(i + 1)
            
            summary = (
                f"🏁 Тестирование завершено!\n\n"
                f"📊 Результаты:\n"
                f"✅ Правильных: {c}\n"
                f"❌ Неправильных: {a - c}\n"
                f"🎯 Точность: {accuracy:.1f}%\n\n"
            )
            
            if wrong_answers:
                wrong_list = ", ".join(map(str, wrong_answers))
                summary += (
                    f"📌 Вопросы с ошибками: {wrong_list}\n"
                    f"Рекомендуем повторить эти вопросы для закрепления знаний.\n\n"
                )
            
            keyboard = []
            
            if wrong_answers:
                keyboard.append([InlineKeyboardButton("🔄 Повторно пройти вопросы с ошибками", callback_data="restart_wrongs")])
                
            keyboard.append([InlineKeyboardButton("🔁 Пройти весь тест заново", callback_data="restart_quiz")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                summary,
                reply_markup=reply_markup
            )

        elif action == "restart_quiz":
            c, a, t, _, accuracy = get_user_stats(user_data["answers"])
            
            old_stats = {
                "correct": c,
                "total": t,
                "accuracy": accuracy
            }
            
            random_mode = user_data.get("random_mode", False)
            user_data["current"] = 0
            user_data["answers"] = [None] * len(QUESTIONS)
            user_data["navigation_history"] = [0]
            user_data["retry_mode"] = False
            
            if random_mode:
                new_order = list(range(len(QUESTIONS)))
                random.shuffle(new_order)
                user_data["question_order"] = new_order
            else:
                user_data["question_order"] = list(range(len(QUESTIONS)))
            
            text = format_question_text(user_data, 0)
            reply_markup = get_question_markup(user_data, 0)
            
            history_note = (
                f"\n\n📌 Предыдущая попытка: "
                f"{old_stats['correct']}/{old_stats['total']} "
                f"({old_stats['accuracy']:.1f}%)"
            )
            
            await query.edit_message_text(
                text + history_note,
                reply_markup=reply_markup
            )
            
        elif action == "restart_wrongs":
            if "original_wrongs" in user_data and user_data["original_wrongs"]:
                wrong_questions = user_data["original_wrongs"].copy()
            else:
                wrong_questions = []
                for i, answer in enumerate(user_data["answers"]):
                    if answer is not None and answer != QUESTIONS[i]["correct"]:
                        wrong_questions.append(i)
                user_data["original_wrongs"] = wrong_questions.copy()
            
            if not wrong_questions:
                await query.answer("🎉 У вас больше нет вопросов с ошибками!", show_alert=True)
                return
                
            c, a, t, _, accuracy = get_user_stats(user_data["answers"])
            old_stats = {
                "correct": c,
                "total": t,
                "accuracy": accuracy
            }
            
            user_data["current"] = 0
            user_data["wrong_questions"] = wrong_questions.copy()
            user_data["question_order"] = wrong_questions.copy()
            user_data["navigation_history"] = [0]
            user_data["retry_mode"] = True

            for idx in wrong_questions:
                user_data["answers"][idx] = None
            
            if user_data.get("random_mode", False):
                random.shuffle(user_data["question_order"])
            
            text = format_question_text(user_data, 0)
            reply_markup = get_question_markup(user_data, 0)
            
            # Форматируем номера вопросов
            question_numbers = [str(i + 1) for i in wrong_questions]
            numbers_str = ", ".join(question_numbers)
            
            history_note = (
                f"\n\n📌 Предыдущая попытка: "
                f"{old_stats['correct']}/{old_stats['total']} "
                f"({old_stats['accuracy']:.1f}%)"
                f"\n🔁 Повторно пройти вопросы с ошибками: {numbers_str}"
            )
            
            await query.edit_message_text(
                text + history_note,
                reply_markup=reply_markup
            )
            
        elif action == "finish_retry":
            await finish_retry_screen(query, context, user_data)
            
        elif action == "return_to_main":
            user_data["question_order"] = list(range(len(QUESTIONS)))
            user_data["current"] = 0
            user_data["retry_mode"] = False
            
            text = format_question_text(user_data, 0)
            reply_markup = get_question_markup(user_data, 0)
            
            await query.edit_message_text(
                text,
                reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Ошибка обработки callback: {e}")
        try:
            await query.edit_message_text(
                "⚠️ Произошла ошибка при обработке запроса. Попробуйте снова или начните новый тест командой /start"
            )
        except Exception as inner_e:
            logger.error(f"Не удалось отредактировать сообщение: {inner_e}")

async def finish_retry_screen(query, context, user_data):
    """Показывает экран завершения повторения ошибок"""
    correct_retry = 0
    for idx in user_data["wrong_questions"]:
        if user_data["answers"][idx] == QUESTIONS[idx]["correct"]:
            correct_retry += 1
    
    total_retry = len(user_data["wrong_questions"])
    accuracy = correct_retry / total_retry * 100 if total_retry > 0 else 0
    
    # Определяем, все ли ошибки исправлены
    all_correct = correct_retry == total_retry
    
    text = (
        f"🏁 Повторение вопросов с ошибками завершено!\n\n"
        f"📊 Результаты повторения:\n"
        f"✅ Правильных: {correct_retry}\n"
        f"❌ Неправильных: {total_retry - correct_retry}\n"
        f"🎯 Точность: {accuracy:.1f}%\n\n"
    )
    
    # Добавляем соответствующее сообщение в зависимости от результата
    if all_correct:
        text += "🎉 Поздравляем! Все ошибки исправлены!"
    else:
        text += "⚠️ Обратите внимание: остались неправильные ответы."
    
    keyboard = [
        [InlineKeyboardButton("🔙 К основному тесту", callback_data="return_to_main")],
        [InlineKeyboardButton("🔄 Повторно пройти вопросы с ошибками", callback_data="restart_wrongs")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and await check_ban(update, context, 'message'):
        return
    
    if update.message:
        user_data = context.user_data
        
        if user_data.get("waiting_for_input") and "edit_message_id" in user_data:
            try:
                user_data["waiting_for_input"] = False
                
                question_num = int(update.message.text.strip())
                
                if 1 <= question_num <= len(QUESTIONS):
                    new_index = None
                    for idx in range(len(user_data["question_order"])):
                        real_idx = user_data["question_order"][idx]
                        if real_idx == question_num - 1:
                            new_index = idx
                            break
                    
                    if new_index is None:
                        raise ValueError("Вопрос не найден в текущем порядке")
                    
                    user_data["current"] = new_index
                    
                    if user_data["random_mode"]:
                        user_data["navigation_history"].append(new_index)
                    
                    text = format_question_text(user_data, new_index)
                    reply_markup = get_question_markup(user_data, new_index)
                    
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=user_data["edit_message_id"],
                        text=text,
                        reply_markup=reply_markup
                    )
                    
                    await update.message.delete()
                else:
                    error_text = user_data["original_text"] + "\n\n" \
                                f"⚠️ Неверный номер вопроса. Введите число от 1 до {len(QUESTIONS)}"
                    
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=user_data["edit_message_id"],
                        text=error_text,
                        reply_markup=user_data["original_markup"]
                    )
                    
                    user_data["waiting_for_input"] = True
            except ValueError:
                error_text = user_data["original_text"] + "\n\n⚠️ Пожалуйста, введите число"
                
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=user_data["edit_message_id"],
                    text=error_text,
                    reply_markup=user_data["original_markup"]
                )
                
                user_data["waiting_for_input"] = True
            return
        
        try:
            sent_message = await update.message.reply_text(
                "🤖 Я бот для тестирования знаний по закону об оружии!\n"
                "Вы ввели неверную команду.\n"
                "Повторные нарушения приведут к бану!\n"
                "Используйте команду /help для просмотра доступных команд\n"
                "Или начните тест командой /start"
            )
            
            await asyncio.sleep(5)
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=sent_message.message_id
            )
            
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
            except Exception as delete_error:
                logger.debug(f"Не удалось удалить сообщение пользователя: {delete_error}")
                
        except Exception as e:
            logger.error(f"Ошибка обработки текста: {e}")

async def set_commands(application):
    commands = [
        BotCommand("start", "Начать тест"),
        BotCommand("quiz", "Перезапустить тест"),
        BotCommand("normal_mode", "Обычный режим"),
        BotCommand("random_mode", "Случайный режим"),
        BotCommand("help", "Помощь")
    ]
    
    try:
        await application.bot.set_my_commands(commands)
        
        bot = Bot(token=TOKEN)
        await bot.set_my_commands(commands)
        await bot.close()
        
        logger.info("Команды бота успешно установлены")
    except Exception as e:
        logger.error(f"Ошибка установки команд: {e}")

async def post_init(application):
    try:
        await set_commands(application)
        logger.info("Бот успешно запущен")
        await notify_admin("✅ Бот успешно запущен!")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        await notify_admin(f"⚠️ Ошибка при запуске бота: {e}")

async def post_shutdown(application):
    try:
        await notify_admin("⛔ Бот остановлен")
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка при остановке бота: {e}")

async def shutdown(signum, app):
    logger.info(f"Получен сигнал {signum}, останавливаю бота...")
    await notify_admin(f"⛔ Бот остановлен по сигналу {signum}")
    await app.stop()

def handle_signal(signum, frame):
    loop = asyncio.get_running_loop()
    loop.create_task(shutdown(signum, app))

if __name__ == '__main__':
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .post_init(post_init) \
        .post_shutdown(post_shutdown) \
        .build()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("normal_mode", normal_mode))
    app.add_handler(CommandHandler("random_mode", random_mode))
    app.add_handler(CommandHandler("reload_questions", reload_questions))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    try:
        logger.info("Бот запускается...")
        app.run_polling()
    except Exception as e:
        logger.critical(f"Фатальная ошибка при запуске бота: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(notify_admin(f"🚨 Бот аварийно остановлен: {e}"))
        loop.close()