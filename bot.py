import asyncio
import logging
import os
import tempfile
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import BotCommand

from core.database import (
    get_all_files, get_file_info, search_files, 
    set_setting, get_setting, delete_file_from_db, get_file_chunks
)
from core.encryption import derive_key, get_hash
from config import BOT_TOKEN, API_ID, API_HASH
from storage import TGStorage

# Загружаем ID владельца из окружения
OWNER_ID = int(os.getenv("OWNER_ID", 0))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class MasterPasswordStates(StatesGroup):
    entering_password = State()
    setting_password = State()
    confirming_password = State()

# Middleware-подобная проверка владельца
def is_owner(user_id: int):
    return user_id == OWNER_ID

def verify_master_password(password: str):
    stored_hash = get_setting("master_password_hash")
    if not stored_hash: return False
    salt = bytes.fromhex(get_setting("master_password_salt"))
    key = derive_key(password, salt)
    return get_hash(key) == stored_hash


async def setup_bot_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск и меню"),
        BotCommand(command="help", description="Справка"),
        BotCommand(command="list", description="Показать файлы"),
        BotCommand(command="search", description="Поиск файлов"),
        BotCommand(command="set_password", description="Установить мастер-пароль"),
    ])


async def upload_from_telegram(file_id: str, file_name: str):
    master_key = get_setting("master_password_hash")
    if not master_key:
        raise ValueError("Master password is not set")

    storage = TGStorage(API_ID, API_HASH)
    await storage.connect()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp:
            temp_path = tmp.name
        await bot.download(file_id, destination=temp_path)
        return await storage.upload_file(temp_path, password=master_key)
    finally:
        await storage.client.disconnect()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@dp.message(F.from_user.id != OWNER_ID)
async def restricted_access(message: types.Message):
    await message.answer("⛔ Доступ запрещен. Вы не являетесь владельцем этой системы.")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Список файлов"), KeyboardButton(text="🚀 Помощь")],
        [KeyboardButton(text="⚙️ Настройки")]
    ], resize_keyboard=True)
    
    await message.answer(
        "🔐 **TGFS Hybrid System**\n\nСистема готова. Используйте меню ниже для навигации.",
        reply_markup=kb, parse_mode="Markdown"
    )

@dp.message(F.text == "🚀 Помощь")
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "📖 **Инструкция TGFS**\n\n"
        "**Команды бота:**\n"
        "• `/list` — Показать все файлы\n"
        "• `/search <имя>` — Поиск\n"
        "• `/set_password` — Установка мастер-пароля\n\n"
        "**Работа через CLI (терминал):**\n"
        "Для загрузки больших файлов (до 2ГБ+) используйте CLI:\n"
        "```bash\n"
        "# Загрузка файла\n"
        "python main.py upload \"movie.mp4\"\n\n"
        "# Скачивание файла (по ID)\n"
        "python main.py download 1\n"
        "```\n"
        "💡 *Бот и CLI используют одну базу и один пароль!*"
    )
    await message.answer(help_text, parse_mode="Markdown")


@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("🔎 Использование: `/search <имя_файла>`", parse_mode="Markdown")
        return
    query = parts[1].strip()
    files = search_files(query)
    if not files:
        await message.answer(f"∅ По запросу '{query}' ничего не найдено.")
        return

    builder = InlineKeyboardBuilder()
    for f in files:
        status = "🔒" if f[4] else "🔓"
        builder.button(text=f"{status} {f[1]}", callback_data=f"info_{f[0]}")
    builder.adjust(1)
    await message.answer(f"🔎 Результаты поиска: {query}", reply_markup=builder.as_markup())

@dp.message(Command("set_password"))
async def cmd_set_password(message: types.Message, state: FSMContext):
    stored_hash = get_setting("master_password_hash")
    if stored_hash:
        await message.answer("🔑 Введите текущий мастер-пароль для смены:")
        await state.set_state(MasterPasswordStates.entering_password)
    else:
        await message.answer("🆕 Введите новый мастер-пароль:")
        await state.set_state(MasterPasswordStates.setting_password)

@dp.message(MasterPasswordStates.entering_password)
@dp.message(MasterPasswordStates.setting_password)
@dp.message(MasterPasswordStates.confirming_password)
async def process_passwords(message: types.Message, state: FSMContext):
    # Удаляем сообщение с паролем для безопасности
    try:
        await message.delete()
    except:
        pass

    current_state = await state.get_state()
    
    if current_state == MasterPasswordStates.entering_password:
        if verify_master_password(message.text):
            await message.answer("✅ Верно. Теперь введите новый пароль:")
            await state.set_state(MasterPasswordStates.setting_password)
        else:
            await message.answer("❌ Неверный пароль. Попробуйте еще раз.")
            
    elif current_state == MasterPasswordStates.setting_password:
        await state.update_data(new_password=message.text)
        await message.answer("🔁 Подтвердите пароль:")
        await state.set_state(MasterPasswordStates.confirming_password)
        
    elif current_state == MasterPasswordStates.confirming_password:
        data = await state.get_data()
        if message.text == data['new_password']:
            salt = os.urandom(16)
            key = derive_key(message.text, salt)
            set_setting("master_password_salt", salt.hex())
            set_setting("master_password_hash", get_hash(key))
            await message.answer("🎉 Мастер-пароль успешно обновлен!")
            await state.clear()
        else:
            await message.answer("❌ Пароли не совпали. Начните заново: /set_password")
            await state.clear()

@dp.message(F.text == "📂 Список файлов")
@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    files = get_all_files()
    if not files:
        await message.answer("∅ Облако пока пусто.")
        return

    builder = InlineKeyboardBuilder()
    for f in files:
        status = "🔒" if f[4] else "🔓"
        builder.button(text=f"{status} {f[1]}", callback_data=f"info_{f[0]}")
    builder.adjust(1)
    await message.answer("🗂 Ваши файлы:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("info_"))
async def process_info(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    f = get_file_info(file_id)
    if not f: return

    text = (
        f"📄 *Имя:* `{f[1]}`\n"
        f"📏 *Размер:* {f[2]/(1024*1024):.2f} MB\n"
        f"🔐 *Зашифрован:* {'Да' if f[5] else 'Нет'}\n"
        f"📅 *Дата:* {f[7]}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Как скачать?", callback_data=f"link_{file_id}")
    builder.button(text="🗑 Удалить", callback_data=f"delete_{file_id}")
    builder.adjust(1)

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("link_"))
async def process_link(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    await callback.message.answer(
        f"🚀 **Для скачивания используйте CLI:**\n"
        f"```bash\npython main.py download {file_id}\n```",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_"))
async def process_delete(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    storage = TGStorage(API_ID, API_HASH)
    await storage.connect()
    chunks = get_file_chunks(file_id)
    await storage.delete_file(file_id, chunks)
    delete_file_from_db(file_id)
    await storage.client.disconnect()
    await callback.message.edit_text("🗑 Файл полностью удален из системы.")
    await callback.answer("Удалено")

# Прием файлов через бота
@dp.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    if not doc:
        await message.answer("❌ Не удалось прочитать документ.")
        return

    file_name = doc.file_name or f"document_{doc.file_id}.bin"
    status_msg = await message.answer(f"⏳ Загружаю `{file_name}` в TGFS...", parse_mode="Markdown")
    try:
        new_file_id = await upload_from_telegram(doc.file_id, file_name)
        await status_msg.edit_text(
            f"✅ Файл добавлен в TGFS.\nID: `{new_file_id}`\nИмя: `{file_name}`",
            parse_mode="Markdown"
        )
    except Exception:
        await status_msg.edit_text("❌ Ошибка при загрузке файла. Попробуйте позже.")


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    if not message.photo:
        await message.answer("❌ Фото не найдено в сообщении.")
        return
    photo = message.photo[-1]  # highest resolution
    file_name = f"photo_{photo.file_unique_id}.jpg"
    status_msg = await message.answer("⏳ Загружаю фото в TGFS...")
    try:
        new_file_id = await upload_from_telegram(photo.file_id, file_name)
        await status_msg.edit_text(f"✅ Фото добавлено в TGFS. ID: `{new_file_id}`", parse_mode="Markdown")
    except Exception:
        await status_msg.edit_text("❌ Ошибка при загрузке фото. Попробуйте позже.")


@dp.message(F.video)
async def handle_video(message: types.Message):
    video = message.video
    if not video:
        await message.answer("❌ Видео не найдено в сообщении.")
        return
    file_name = video.file_name or f"video_{video.file_unique_id}.mp4"
    status_msg = await message.answer(f"⏳ Загружаю `{file_name}` в TGFS...", parse_mode="Markdown")
    try:
        new_file_id = await upload_from_telegram(video.file_id, file_name)
        await status_msg.edit_text(f"✅ Видео добавлено в TGFS. ID: `{new_file_id}`", parse_mode="Markdown")
    except Exception:
        await status_msg.edit_text("❌ Ошибка при загрузке видео. Попробуйте позже.")


@dp.message(F.audio)
async def handle_audio(message: types.Message):
    audio = message.audio
    if not audio:
        await message.answer("❌ Аудио не найдено в сообщении.")
        return
    file_name = audio.file_name or f"audio_{audio.file_unique_id}.mp3"
    status_msg = await message.answer(f"⏳ Загружаю `{file_name}` в TGFS...", parse_mode="Markdown")
    try:
        new_file_id = await upload_from_telegram(audio.file_id, file_name)
        await status_msg.edit_text(f"✅ Аудио добавлено в TGFS. ID: `{new_file_id}`", parse_mode="Markdown")
    except Exception:
        await status_msg.edit_text("❌ Ошибка при загрузке аудио. Попробуйте позже.")


@dp.message(F.voice)
async def handle_voice(message: types.Message):
    voice = message.voice
    if not voice:
        await message.answer("❌ Голосовое сообщение не найдено.")
        return
    file_name = f"voice_{voice.file_unique_id}.ogg"
    status_msg = await message.answer("⏳ Загружаю голосовое в TGFS...")
    try:
        new_file_id = await upload_from_telegram(voice.file_id, file_name)
        await status_msg.edit_text(f"✅ Голосовое добавлено в TGFS. ID: `{new_file_id}`", parse_mode="Markdown")
    except Exception:
        await status_msg.edit_text("❌ Ошибка при загрузке голосового. Попробуйте позже.")

async def main():
    await setup_bot_commands()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
