import typer
import asyncio
import os
import sys
import math
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.prompt import Prompt

from core.database import (
    init_db, get_all_files, get_file_chunks,
    delete_file_from_db, get_file_info, search_files,
    set_setting, get_setting
)
from storage import TGStorage
from config import API_ID, API_HASH
from core.encryption import derive_key, get_hash

console = Console()
app = typer.Typer()

async def get_storage():
    storage = TGStorage(API_ID, API_HASH)
    await storage.connect()
    return storage

def check_password():
    stored_hash = get_setting("master_password_hash")
    if not stored_hash:
        console.print("[yellow]Мастер-пароль не установлен. Пожалуйста, установите его.[/yellow]")
        password = Prompt.ask("Новый мастер-пароль", password=True)
        confirm = Prompt.ask("Подтвердите пароль", password=True)
        if password != confirm:
            console.print("[red]Пароли не совпадают![/red]")
            sys.exit(1)
        salt = os.urandom(16)
        # We store salt for the master password too
        set_setting("master_password_salt", salt.hex())
        key = derive_key(password, salt)
        set_setting("master_password_hash", get_hash(key))
        console.print("[green]Мастер-пароль успешно установлен![/green]")
        return password

    password = Prompt.ask("Введите мастер-пароль", password=True)
    salt = bytes.fromhex(get_setting("master_password_salt"))
    key = derive_key(password, salt)
    if get_hash(key) != stored_hash:
        console.print("[red]Неверный пароль![/red]")
        sys.exit(1)
    return password

@app.command()
def init_fs():
    """Инициализировать базу данных."""
    init_db()
    console.print(Panel("[bold green]База данных TGFS готова к работе![/bold green]"))

@app.command()
def ls():
    """Показать файлы в облаке."""
    files = get_all_files()
    if not files:
        console.print("[yellow]Облако пусто.[/yellow]")
        return
    
    table = Table(title="Файлы в TGFS")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Имя файла", style="magenta")
    table.add_column("Размер (MB)", justify="right", style="green")
    table.add_column("Дата загрузки", style="blue")
    table.add_column("Зашифрован", justify="center")

    for f in files:
        size_mb = f[2] / (1024 * 1024)
        encrypted = "🔒" if f[4] else "🔓"
        table.add_row(str(f[0]), f[1], f"{size_mb:.2f}", str(f[3]), encrypted)

    console.print(table)

@app.command()
def upload(path: str, encrypt: bool = typer.Option(True, help="Зашифровать файл")):
    """Загрузить файл."""
    if not os.path.exists(path):
        console.print(f"[red]Ошибка: Файл {path} не найден.[/red]")
        return
    
    password = None
    if encrypt:
        password = check_password()

    async def run_upload():
        storage = await get_storage()

        file_size = os.path.getsize(path)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            overall_task = progress.add_task("[cyan]Загрузка...", total=file_size)
            chunk_tasks = {}
            total_chunks = math.ceil(file_size / (48 * 1024 * 1024))

            async def update_progress(idx, size):
                if idx not in chunk_tasks:
                    chunk_tasks[idx] = progress.add_task(f"  [gray]Часть {idx+1}", total=size)

                progress.update(chunk_tasks[idx], completed=size)
                progress.update(overall_task, advance=size)
                if progress.tasks[chunk_tasks[idx]].finished:
                    progress.remove_task(chunk_tasks[idx])

            await storage.upload_file(path, password, update_progress)

        console.print(f"[bold green]Файл {os.path.basename(path)} успешно загружен![/bold green]")

    try:
        asyncio.run(run_upload())
    except Exception as e:
        console.print_exception()

@app.command()
def download(file_id: int, output: str = "."):
    """Скачать файл по ID."""
    file_info = get_file_info(file_id)
    if not file_info:
        console.print(f"[red]Ошибка: Файл с ID {file_id} не найден.[/red]")
        return

    name = file_info[1]
    is_encrypted = file_info[5]
    file_size = file_info[2]

    password = None
    if is_encrypted:
        password = check_password()

    dest = os.path.join(output, name) if os.path.isdir(output) else output

    async def run_download():
        chunks = get_file_chunks(file_id)
        storage = await get_storage()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            overall_task = progress.add_task("[cyan]Скачивание...", total=file_size)
            chunk_tasks = {}

            async def update_progress(idx, size):
                if idx not in chunk_tasks:
                    chunk_tasks[idx] = progress.add_task(f"  [gray]Часть {idx+1}", total=size)

                progress.update(chunk_tasks[idx], completed=size)
                progress.update(overall_task, advance=size)
                if progress.tasks[chunk_tasks[idx]].finished:
                    progress.remove_task(chunk_tasks[idx])

            await storage.download_file(file_id, dest, chunks, password, update_progress)

        console.print(f"[bold green]Файл сохранен в: {dest}[/bold green]")

    try:
        asyncio.run(run_download())
    except Exception as e:
        console.print_exception()

@app.command()
def rm(file_id: int):
    """Удалить файл из облака и базы."""
    file_info = get_file_info(file_id)
    if not file_info:
        console.print(f"[red]Ошибка: Файл с ID {file_id} не найден.[/red]")
        return

    confirm = typer.confirm(f"Вы уверены, что хотите удалить {file_info[1]}?")
    if not confirm:
        return

    async def run_delete():
        chunks = get_file_chunks(file_id)
        storage = await get_storage()
        await storage.delete_file(file_id, chunks)
        delete_file_from_db(file_id)
        console.print(f"[green]Файл {file_info[1]} удален.[/green]")

    try:
        asyncio.run(run_delete())
    except Exception as e:
        console.print_exception()

@app.command()
def info(file_id: int):
    """Показать детальную информацию о файле."""
    f = get_file_info(file_id)
    if not f:
        console.print(f"[red]Ошибка: Файл с ID {file_id} не найден.[/red]")
        return

    panel_content = (
        f"[bold]ID:[/bold] {f[0]}\n"
        f"[bold]Имя:[/bold] {f[1]}\n"
        f"[bold]Размер:[/bold] {f[2]} байт ({f[2]/(1024*1024):.2f} MB)\n"
        f"[bold]Частей:[/bold] {f[3]}\n"
        f"[bold]Hash:[/bold] {f[4]}\n"
        f"[bold]Зашифрован:[/bold] {'Да' if f[5] else 'Нет'}\n"
        f"[bold]Дата загрузки:[/bold] {f[7]}"
    )
    console.print(Panel(panel_content, title=f"Информация о файле: {f[1]}"))

@app.command()
def search(query: str):
    """Поиск файлов по имени."""
    files = search_files(query)
    if not files:
        console.print(f"[yellow]Файлы по запросу '{query}' не найдены.[/yellow]")
        return

    table = Table(title=f"Результаты поиска: {query}")
    table.add_column("ID", style="cyan")
    table.add_column("Имя файла", style="magenta")
    table.add_column("Размер (MB)", justify="right", style="green")
    table.add_column("Зашифрован", justify="center")

    for f in files:
        size_mb = f[2] / (1024 * 1024)
        encrypted = "🔒" if f[4] else "🔓"
        table.add_row(str(f[0]), f[1], f"{size_mb:.2f}", encrypted)

    console.print(table)

if __name__ == "__main__":
    try:
        app()
    except Exception:
        console.print_exception()
