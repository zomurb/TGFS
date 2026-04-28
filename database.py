import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tgfs.db")

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
        hash TEXT,
        is_encrypted INTEGER DEFAULT 0,
        salt BLOB,
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

    # Таблица настроек (для мастер-пароля)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

def add_file(name, size, total_chunks, file_hash=None, is_encrypted=0, salt=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO files (name, size, total_chunks, hash, is_encrypted, salt) VALUES (?, ?, ?, ?, ?, ?)",
        (name, size, total_chunks, file_hash, is_encrypted, salt)
    )
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
    cursor.execute("SELECT id, name, size, upload_date, is_encrypted FROM files")
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

def delete_file_from_db(file_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

def get_file_info(file_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    file_info = cursor.fetchone()
    conn.close()
    return file_info

def search_files(query):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, size, upload_date, is_encrypted FROM files WHERE name LIKE ?", (f'%{query}%',))
    files = cursor.fetchall()
    conn.close()
    return files

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None
