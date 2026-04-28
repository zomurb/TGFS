import sqlite3
import os

DB_PATH = "tgfs.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица файлов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        size INTEGER NOT NULL,
        total_chunks INTEGER NOT NULL,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица частей файлов (сообщения в Telegram)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER,
        message_id INTEGER NOT NULL,
        part_index INTEGER NOT NULL,
        FOREIGN KEY (file_id) REFERENCES files (id)
    )
    ''')
    
    conn.commit()
    conn.close()

def add_file(name, size, total_chunks):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO files (name, size, total_chunks) VALUES (?, ?, ?)", (name, size, total_chunks))
    file_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return file_id

def add_chunk(file_id, message_id, part_index):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chunks (file_id, message_id, part_index) VALUES (?, ?, ?)", (file_id, message_id, part_index))
    conn.commit()
    conn.close()

def get_all_files():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, size, upload_date FROM files")
    files = cursor.fetchall()
    conn.close()
    return files

def get_file_chunks(file_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, part_index FROM chunks WHERE file_id = ? ORDER BY part_index", (file_id,))
    chunks = cursor.fetchall()
    conn.close()
    return chunks
