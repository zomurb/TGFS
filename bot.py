import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Dict
from aiogram import Bot, Dispatcher, types, F, Router, BaseMiddleware
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import BOT_TOKEN, OWNER_ID, TG_API_ID, TG_API_HASH
from core.database import (
    get_all_files, get_file_info, search_files,
    get_setting, set_setting, delete_file_from_db, get_file_chunks
)
from core.encryption import derive_key, get_hash
from core.storage import TGStorage

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# States for FSM
class AuthStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_new_password = State()
    waiting_for_current_password_change = State()

# In-memory session storage (simple for one owner)
authenticated_users = set()

# Shared storage instance for the bot
# Use a different session name to avoid conflicts with CLI
storage = TGStorage(TG_API_ID, TG_API_HASH, session_name='tgfs_bot_session')

# Middlewares

class OwnerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.id != OWNER_ID:
            if isinstance(event, Message):
                await event.answer("⛔ Access denied.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Access denied.", show_alert=True)
            return
        return await handler(event, data)

class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Skip auth check for some commands and states
        user = data.get("event_from_user")
        state: FSMContext = data.get("state")
        current_state = await state.get_state()

        # Check if it's a message and starts with /start or /help or /setpassword
        is_auth_action = False
        if isinstance(event, Message):
            if event.text:
                if event.text.startswith(("/start", "/help", "/setpassword")):
                    is_auth_action = True

        if current_state in [AuthStates.waiting_for_new_password, AuthStates.waiting_for_current_password_change]:
            is_auth_action = True

        if user.id not in authenticated_users and not is_auth_action:
            if isinstance(event, Message):
                # If not a command, it might be the login attempt
                if event.text and not event.text.startswith("/"):
                    return await handler(event, data)
                await event.answer("🔐 Please login by entering the Master Password.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🔐 Login required", show_alert=True)
            return

        return await handler(event, data)

# Commands

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    stored_hash = get_setting("master_password_hash")
    if not stored_hash:
        await message.answer("👋 Welcome! Master password is not set. Use /setpassword to set it.")
    else:
        if message.from_user.id in authenticated_users:
            await message.answer("✅ Authenticated. Use /list to see files or /help for commands.")
        else:
            await message.answer("🔒 Please enter the Master Password to access TGFS.")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "📖 *TGFS Bot Help*\n\n"
        "/list - Show all files\n"
        "/search <query> - Search files by name\n"
        "/setpassword - Change master password\n"
        "/start - Check auth status\n\n"
        "To access files, you must first enter the Master Password."
    )
    await message.answer(help_text, parse_mode="Markdown")

@router.message(Command("setpassword"))
async def cmd_setpassword(message: types.Message, state: FSMContext):
    stored_hash = get_setting("master_password_hash")
    if stored_hash:
        await message.answer("🔐 Please enter your *current* Master Password:")
        await state.set_state(AuthStates.waiting_for_current_password_change)
    else:
        await message.answer("🆕 Please set a *new* Master Password:")
        await state.set_state(AuthStates.waiting_for_new_password)

@router.message(AuthStates.waiting_for_current_password_change)
async def process_current_password_change(message: types.Message, state: FSMContext):
    password = message.text
    await message.delete() # Security: delete password message

    stored_hash = get_setting("master_password_hash")
    salt = bytes.fromhex(get_setting("master_password_salt"))
    key = derive_key(password, salt)

    if get_hash(key) == stored_hash:
        await message.answer("✅ Correct. Now enter the *new* Master Password:")
        await state.set_state(AuthStates.waiting_for_new_password)
    else:
        await message.answer("❌ Incorrect password. Action cancelled.")
        await state.clear()

@router.message(AuthStates.waiting_for_new_password)
async def process_new_password(message: types.Message, state: FSMContext):
    password = message.text
    await message.delete() # Security: delete password message

    salt = os.urandom(16)
    set_setting("master_password_salt", salt.hex())
    key = derive_key(password, salt)
    set_setting("master_password_hash", get_hash(key))

    authenticated_users.add(message.from_user.id)
    await message.answer("✅ Master Password has been set and you are now logged in!")
    await state.clear()

@router.message(F.text)
async def handle_login_or_text(message: types.Message, state: FSMContext):
    if message.text.startswith("/"):
        return

    if message.from_user.id not in authenticated_users:
        stored_hash = get_setting("master_password_hash")
        if not stored_hash:
            await message.answer("⚠️ Master password not set. Use /setpassword")
            return

        password = message.text
        await message.delete() # Security: delete password message

        salt = bytes.fromhex(get_setting("master_password_salt"))
        key = derive_key(password, salt)

        if get_hash(key) == stored_hash:
            authenticated_users.add(message.from_user.id)
            await message.answer("🔓 Access granted! You can now use TGFS.")
        else:
            await message.answer("❌ Incorrect password.")
        return

    await message.answer("❓ Use /help to see available commands.")

@router.message(Command("list"))
async def cmd_list(message: types.Message):
    files = get_all_files()
    if not files:
        await message.answer("📁 Cloud is empty.")
        return

    response = "📁 *Files in TGFS:*\n\n"
    builder = InlineKeyboardBuilder()
    for f in files:
        file_id, name, size, date, encrypted = f
        size_mb = size / (1024 * 1024)
        lock = "🔒" if encrypted else "🔓"
        response += f"{lock} `{name}` ({size_mb:.2f} MB)\n"
        builder.button(text=f"ℹ️ {name}", callback_data=f"info_{file_id}")

    builder.adjust(1)
    await message.answer(response, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.message(Command("search"))
async def cmd_search(message: types.Message, command: CommandObject):
    query = command.args
    if not query:
        await message.answer("❓ Please provide a search query: `/search <name>`", parse_mode="Markdown")
        return

    files = search_files(query)
    if not files:
        await message.answer(f"🔍 No files found for '{query}'.")
        return

    builder = InlineKeyboardBuilder()
    for f in files:
        file_id, name, size, date, encrypted = f
        builder.button(text=f"ℹ️ {name}", callback_data=f"info_{file_id}")

    builder.adjust(1)
    await message.answer(f"🔍 *Search results for '{query}':*", parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("info_"))
async def cb_info(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    f = get_file_info(file_id)
    if not f:
        await callback.answer("❌ File not found")
        return

    info_text = (
        f"📄 *File Info*\n"
        f"🆔 ID: `{f[0]}`\n"
        f"📛 Name: `{f[1]}`\n"
        f"📏 Size: `{f[2]}` bytes ({f[2]/(1024*1024):.2f} MB)\n"
        f"🧩 Chunks: `{f[3]}`\n"
        f"🔐 Encrypted: `{'Yes' if f[5] else 'No'}`\n"
        f"📅 Date: `{f[7]}`"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Get Link", callback_data=f"link_{file_id}")
    builder.button(text="🗑️ Delete", callback_data=f"delete_{file_id}")
    builder.button(text="⬅️ Back to list", callback_data="list_files")
    builder.adjust(2, 1)

    await callback.message.edit_text(info_text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "list_files")
async def cb_list(callback: types.CallbackQuery):
    files = get_all_files()
    if not files:
        await callback.message.edit_text("📁 Cloud is empty.")
        return

    response = "📁 *Files in TGFS:*\n\n"
    builder = InlineKeyboardBuilder()
    for f in files:
        file_id, name, size, date, encrypted = f
        size_mb = size / (1024 * 1024)
        lock = "🔒" if encrypted else "🔓"
        response += f"{lock} `{name}` ({size_mb:.2f} MB)\n"
        builder.button(text=f"ℹ️ {name}", callback_data=f"info_{file_id}")

    builder.adjust(1)
    await callback.message.edit_text(response, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("link_"))
async def cb_link(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    chunks = get_file_chunks(file_id)
    if not chunks:
        await callback.answer("❌ Chunks not found", show_alert=True)
        return

    msg_id = chunks[0][0]
    link = f"https://t.me/c/{OWNER_ID}/{msg_id}"

    await callback.message.answer(f"🔗 Link to first chunk (Message ID: {msg_id}):\n{link}\n\n_Note: This link works if you have access to the chat._", parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("delete_"))
async def cb_delete(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    f = get_file_info(file_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm Delete", callback_data=f"confirm_del_{file_id}")
    builder.button(text="❌ Cancel", callback_data=f"info_{file_id}")
    builder.adjust(1)

    await callback.message.edit_text(f"⚠️ Are you sure you want to delete `{f[1]}`?", parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("confirm_del_"))
async def cb_confirm_delete(callback: types.CallbackQuery):
    file_id = int(callback.data.split("_")[1])
    f = get_file_info(file_id)

    if not storage.client.is_connected():
        await storage.connect()

    chunks = get_file_chunks(file_id)
    await storage.delete_file(file_id, chunks)
    delete_file_from_db(file_id)

    await callback.message.edit_text(f"✅ File `{f[1]}` has been deleted from cloud and database.", parse_mode="Markdown")
    await callback.answer()

async def main():
    # Setup storage
    await storage.connect()

    # Register middlewares
    router.message.middleware(OwnerMiddleware())
    router.callback_query.middleware(OwnerMiddleware())
    router.message.middleware(AuthMiddleware())
    router.callback_query.middleware(AuthMiddleware())

    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
