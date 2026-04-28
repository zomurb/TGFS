from telethon import TelegramClient
import os
import math
from database import add_file, add_chunk

CHUNK_SIZE = 48 * 1024 * 1024  # 48 MB

class TGStorage:
    def __init__(self, api_id, api_hash, session_name='tgfs_session'):
        self.client = TelegramClient(session_name, api_id, api_hash)

    async def connect(self):
        await self.client.start()
        if not await self.client.is_user_authorized():
            # Если не авторизован, Telethon сам спросит код в терминале
            pass

    async def upload_file(self, file_path):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        total_chunks = math.ceil(file_size / CHUNK_SIZE)
        
        # Регистрация в БД
        file_id = add_file(file_name, file_size, total_chunks)
        
        print(f"Загружаю {file_name} ({total_chunks} частей)...")
        
        with open(file_path, 'rb') as f:
            for i in range(total_chunks):
                chunk_data = f.read(CHUNK_SIZE)
                # Отправляем чанк как файл (документ)
                # Чтобы не забивать память, создаем временный буфер
                msg = await self.client.send_file(
                    'me', 
                    chunk_data, 
                    caption=f"{file_name} | part {i+1}/{total_chunks}",
                    force_document=True
                )
                add_chunk(file_id, msg.id, i)
                print(f"Загружено {i+1}/{total_chunks}")
        
        return file_id

    async def download_file(self, file_id, dest_path, chunks):
        print(f"Скачиваю файл {file_id}...")
        with open(dest_path, 'wb') as f:
            for msg_id, part_index in chunks:
                msg = await self.client.get_messages('me', ids=msg_id)
                chunk_data = await self.client.download_media(msg, file=bytes)
                f.write(chunk_data)
                print(f"Скачана часть {part_index+1}")
