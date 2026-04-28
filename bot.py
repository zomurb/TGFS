import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from core.database import (
    get_all_files, get_file_info, search_files,
    set_setting, get_setting, delete_file_from_db, get_file_chunks
)
from core.encryption import derive_key, get_hash
from config import BOT_TOKEN, API_ID, API_HASH
from storage import TGStorage

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class MasterPasswordStates(StatesGroup):
    entering_password = State()
    setting_password = State()
    confirming_password = State()

def verify_master_password(password: str):
    stored_hash = get_setting("master_password_hash")
    if not stored_hash:
        return False
    salt = bytes.fromhex(get_setting("master_password_salt"))
    key = derive_key(password, salt)
    return get_hash(key) == stored_hash

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    stored_hash = get_setting("master_password_hash")
    if not stored_hash:
        await message.answer("Добро пожаловать в TGFS! Мастер-пароль не установлен. Используйте /set_password для установки.")
    else:
        await message.answer("Добро пожаловать в TGFS! Используйте /list для просмотра файлов или /search <запрос> для поиска.")

@dp.message(Command("set_password"))
async def cmd_set_password(message: types.Message, state: FSMContext):
    stored_hash = get_setting("master_password_hash")
    if stored_hash:
        await message.answer("Мастер-пароль уже установлен. Для смены сначала введите текущий пароль:")
        await state.set_state(MasterPasswordStates.entering_password)
    else:
        await message.answer("Введите новый мастер-пароль:")
        await state.set_state(MasterPasswordStates.setting_password)

@dp.message(MasterPasswordStates.entering_password)
async def process_current_password(message: types.Message, state: FSMContext):
    if verify_master_password(message.text):
        await message.answer("Верно. Теперь введите новый мастер-пароль:")
        await state.set_state(MasterPasswordStates.setting_password)
    else:
        await message.answer("Неверный пароль. Попробуйте снова или /cancel.")

@dp.message(MasterPasswordStates.setting_password)
async def process_new_password(message: types.Message, state: FSMContext):
    await state.update_data(new_password=message.text)
    await message.answer("Подтвердите новый мастер-пароль:")
    await state.set_state(MasterPasswordStates.confirming_password)

@dp.message(MasterPasswordStates.confirming_password)
async def process_confirm_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == data['new_password']:
        salt = os.urandom(16)
        key = derive_key(message.text, salt)
        set_setting("master_password_salt", salt.hex())
        set_setting("master_password_hash", get_hash(key))
        await message.answer("Мастер-пароль успешно установлен!")
        await state.clear()
    else:
        await message.answer("Пароли не совпадают. Попробуйте /set_password снова.")
        await state.clear()

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    files = get_all_files()
    if not files:
        await message.answer("Облако пусто.")
        return

    builder = InlineKeyboardBuilder()
    for f in files:
        builder.button(text=f"{'🔒' if f[4] else '🔓'} {f[1]}", callback_data=f"info_{f[0]}")
    builder.adjust(1)
    await message.answer("Список файлов:", reply_markup=builder.as_markup())

@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    query = message.text.replace("/search", "").strip()
    if not query:
        await message.answer("Использование: /search <запрос>")
        return

    files = search_files(query)
    if not files:
        await message.answer(f"Файлы по запросу '{query}' не найдены.")
        return

    builder = InlineKeyboardBuilder()
    for f in files:
        builder.button(text=f"{'🔒' if f[4] else '🔓'} {f[1]}", callback_data=f"info_{f[0]}")
    builder.adjust(1)
    await message.answer(f"Результаты поиска '{query}':", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("info_"))
async def process_info(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    f = get_file_info(file_id)
    if not f:
        await callback.answer("Файл не найден.")
        return

    text = (
        f"📄 *Имя:* {f[1]}\n"
        f"📏 *Размер:* {f[2]/(1024*1024):.2f} MB\n"
        f"🧩 *Частей:* {f[3]}\n"
        f"🔐 *Зашифрован:* {'Да' if f[5] else 'Нет'}\n"
        f"📅 *Дата:* {f[7]}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"delete_{file_id}")
    builder.button(text="🔗 Получить ссылку (CLI)", callback_data=f"link_{file_id}")
    builder.adjust(2)

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("delete_"))
async def process_delete(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    f = get_file_info(file_id)

    storage = TGStorage(API_ID, API_HASH)
    await storage.connect()
    chunks = get_file_chunks(file_id)
    await storage.delete_file(file_id, chunks)
    delete_file_from_db(file_id)
    await storage.client.disconnect()

    await callback.message.edit_text(f"Файл {f[1]} удален.")
    await callback.answer("Удалено.")

@dp.callback_query(F.data.startswith("link_"))
async def process_link(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    await callback.answer(f"Для скачивания используйте CLI: python main.py download {file_id}", show_alert=True)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
