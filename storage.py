import os
import math
import asyncio
from telethon import TelegramClient, errors
from database import add_file, add_chunk
from encryption import derive_key, encrypt_data, decrypt_data, get_file_hash, get_hash

CHUNK_SIZE = 48 * 1024 * 1024  # 48 MB
MAX_PARALLEL = 5
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class TGStorage:
    def __init__(self, api_id, api_hash, session_name='tgfs_session'):
        if session_name == "tgfs_session":
            session_name = os.path.join(BASE_DIR, session_name)
        self.client = TelegramClient(session_name, api_id, api_hash)

    async def connect(self):
        await self.client.start()

    async def upload_chunk(self, file_id, file_name, chunk_data, part_index, total_chunks, progress_callback=None):
        retries = 5
        for attempt in range(retries):
            try:
                msg = await self.client.send_file(
                    'me',
                    chunk_data,
                    caption=f"{file_name} | part {part_index+1}/{total_chunks}",
                    force_document=True
                )
                add_chunk(file_id, msg.id, part_index)
                if progress_callback:
                    await progress_callback(part_index, len(chunk_data))
                return msg.id
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                if attempt == retries - 1:
                    raise e
                await asyncio.sleep(2 ** attempt)

    async def upload_file(self, file_path, password=None, progress_callback=None):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_hash = get_file_hash(file_path)
        
        is_encrypted = 0
        salt = None
        key = None
        if password:
            is_encrypted = 1
            salt = os.urandom(16)
            key = derive_key(password, salt)

        total_chunks = math.ceil(file_size / CHUNK_SIZE)
        file_id = add_file(file_name, file_size, total_chunks, file_hash, is_encrypted, salt)

        queue = asyncio.Queue(maxsize=MAX_PARALLEL)

        async def worker():
            while True:
                item = await queue.get()
                if item is None:
                    queue.task_done()
                    break
                p_index, data = item
                try:
                    await self.upload_chunk(file_id, file_name, data, p_index, total_chunks, progress_callback)
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(MAX_PARALLEL)]

        with open(file_path, 'rb') as f:
            for i in range(total_chunks):
                chunk_data = f.read(CHUNK_SIZE)
                if is_encrypted:
                    chunk_data = encrypt_data(chunk_data, key)
                await queue.put((i, chunk_data))

        for _ in range(MAX_PARALLEL):
            await queue.put(None)

        await asyncio.gather(*workers)
        return file_id

    async def download_chunk(self, msg_id, part_index, key=None, progress_callback=None):
        retries = 5
        for attempt in range(retries):
            try:
                msg = await self.client.get_messages('me', ids=msg_id)
                chunk_data = await self.client.download_media(msg, file=bytes)
                if key:
                    chunk_data = decrypt_data(chunk_data, key)
                if progress_callback:
                    await progress_callback(part_index, len(chunk_data))
                return chunk_data
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                if attempt == retries - 1:
                    raise e
                await asyncio.sleep(2 ** attempt)

    async def download_file(self, file_id, dest_path, chunks, password=None, progress_callback=None):
        from database import get_file_info
        file_info = get_file_info(file_id)
        is_encrypted = file_info[5]
        salt = file_info[6]
        expected_hash = file_info[4]

        key = None
        if is_encrypted:
            if not password:
                raise ValueError("Password required for encrypted file")
            key = derive_key(password, salt)

        queue = asyncio.Queue(maxsize=MAX_PARALLEL)
        results = {}

        async def worker():
            while True:
                item = await queue.get()
                if item is None:
                    queue.task_done()
                    break
                m_id, p_index = item
                try:
                    data = await self.download_chunk(m_id, p_index, key, progress_callback)
                    results[p_index] = data
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(MAX_PARALLEL)]

        for msg_id, part_index in chunks:
            await queue.put((msg_id, part_index))

        for _ in range(MAX_PARALLEL):
            await queue.put(None)

        await asyncio.gather(*workers)
        
        # Write to disk in order to save memory
        with open(dest_path, 'wb') as f:
            for i in range(len(chunks)):
                if i in results:
                    f.write(results[i])
                    del results[i]  # Free memory as we write
                else:
                    # This shouldn't happen because we await workers, 
                    # but if parallelism was more complex this would be a placeholder
                    raise ValueError(f"Chunk {i} missing from results")
        
        downloaded_hash = get_file_hash(dest_path)
        if downloaded_hash != expected_hash:
            raise ValueError("Integrity check failed! Hashes do not match.")

    async def delete_file(self, file_id, chunks):
        msg_ids = [c[0] for c in chunks]
        # Delete from Telegram
        await self.client.delete_messages('me', msg_ids)
        # Delete from DB is handled in main.py call to database.py
