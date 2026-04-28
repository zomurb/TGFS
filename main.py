import typer
import asyncio
import os
from database import init_db, get_all_files, get_file_chunks
from storage import TGStorage
from config import API_ID, API_HASH
from colorama import Fore, Style, init

init()
app = typer.Typer()

async def get_storage():
    storage = TGStorage(API_ID, API_HASH)
    await storage.connect()
    return storage

@app.command()
def init_fs():
    """Инициализировать базу данных."""
    init_db()
    print(f"{Fore.GREEN}База данных TGFS готова к работе!{Style.RESET_ALL}")

@app.command()
def ls():
    """Показать файлы в облаке."""
    files = get_all_files()
    if not files:
        print("Облако пусто.")
        return
    
    print(f"{Fore.CYAN}{'ID':<4} {'Имя файла':<30} {'Размер':<10} {'Дата загрузки':<20}{Style.RESET_ALL}")
    print("-" * 70)
    for f in files:
        size_mb = f[2] / (1024 * 1024)
        print(f"{f[0]:<4} {f[1]:<30} {size_mb:>7.2f} MB   {f[3]:<20}")

@app.command()
def upload(path: str):
    """Загрузить файл."""
    if not os.path.exists(path):
        print(f"{Fore.RED}Ошибка: Файл {path} не найден.{Style.RESET_ALL}")
        return
    
    async def run_upload():
        storage = await get_storage()
        await storage.upload_file(path)
        print(f"{Fore.GREEN}Файл успешно загружен!{Style.RESET_ALL}")

    asyncio.run(run_upload())

@app.command()
def download(file_id: int, output: str = "."):
    """Скачать файл по ID."""
    chunks = get_file_chunks(file_id)
    if not chunks:
        print(f"{Fore.RED}Ошибка: Файл с ID {file_id} не найден в базе.{Style.RESET_ALL}")
        return

    # Получаем имя файла из базы
    from database import sqlite3, DB_PATH
    conn = sqlite3.connect(DB_PATH)
    name = conn.execute("SELECT name FROM files WHERE id = ?", (file_id,)).fetchone()[0]
    conn.close()

    dest = os.path.join(output, name) if os.path.isdir(output) else output

    async def run_download():
        storage = await get_storage()
        await storage.download_file(file_id, dest, chunks)
        print(f"{Fore.GREEN}Файл сохранен в: {dest}{Style.RESET_ALL}")

    asyncio.run(run_download())

if __name__ == "__main__":
    app()
