import uvloop
import asyncio
import uuid
import sys
from time import time as tm
from asyncio import create_subprocess_exec, gather
from pyrogram.types import User
from pyrogram import Client, enums, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, WebpageCurlFailed, WebpageMediaEmpty
from asyncio import Queue
from config import *
from utils import *
from tmdb import get_by_name
from shorterner import shorten_url
from database import add_user, del_user, full_userbase, present_user

uvloop.install()

# Define an async queue to handle messages sequentially
message_queue = Queue()

user_data = {}
user_sessions = {}

# PROGRAM BOT INITIALIZATION 

bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=1000,
    parse_mode=enums.ParseMode.HTML
).start()

bot_loop = bot.loop
bot_username = bot.me.username

@bot.on_message(filters.private & filters.command("start"))
async def start_command(client, message):
    try:
        user_id = message.from_user.id

        if not await present_user(user_id):
            try:
                await add_user(user_id)
            except:
                pass

        user_link = await get_user_link(message.from_user)

        if len(message.command) > 1:
            command_arg = message.command[1]
            
            # Handle token flow
            if command_arg == "token":
                msg = await bot.get_messages(LOG_CHANNEL_ID, TUT_ID)
                sent_msg = await msg.copy(chat_id=message.chat.id)
                await message.delete()
                await asyncio.sleep(300)
                await sent_msg.delete()
                return

            # Handle token verification
            if command_arg.startswith("token_"):
                input_token = command_arg[6:]
                token_msg = await verify_token(user_id, input_token)
                reply = await message.reply_text(token_msg)
                await bot.send_message(LOG_CHANNEL_ID, f"User🕵️‍♂️{user_link} with 🆔 {user_id} @{bot_username} {token_msg}", parse_mode=enums.ParseMode.HTML)
                await auto_delete_message(message, reply)
                return

            # Handle file flow
            file_id = int(command_arg)
            if not await check_access(message, user_id):
                return

            file_message = await bot.get_messages(DB_CHANNEL_ID, file_id)
            media = file_message.video or file_message.audio or file_message.document
            if media:
                caption = await remove_extension(file_message.caption.html or "")
                copy_message = await file_message.copy(chat_id=message.chat.id, caption=f"<b>{caption}</b>", parse_mode=enums.ParseMode.HTML)
                user_data[user_id]['file_count'] = user_data[user_id].get('file_count', 0) + 1
                await auto_delete_message(message, copy_message)
                await asyncio.sleep(3)
            else:
                await auto_delete_message(message, await message.reply_text("File not found or inaccessible."))
            return

        # Default flow (no arguments)
        await greet_user(message)
        
    except ValueError:
        reply = await message.reply_text("Invalid File ID.")
        await auto_delete_message(message, reply)
    except FloodWait as f:
        await asyncio.sleep(f.value)
        await start_command(client, message)  # Retry after the flood wait
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await auto_delete_message(message, await message.reply_text(f"An error occurred: {e}"))


@bot.on_message(filters.chat(DB_CHANNEL_ID) & (filters.document | filters.video |filters.audio))
async def handle_new_message(client, message):
    # Add the message to the queue for sequential processing
    await message_queue.put(message)
    
@bot.on_message(filters.private & filters.command("index") & filters.user(OWNER_ID))
async def handle_file(client, message):
    try:
        user_id = message.from_user.id
        user_sessions[user_id] = True

        # Helper function to get user input
        async def get_user_input(prompt):
            bot_message = await message.reply_text(prompt)
            user_message = await bot.listen(chat_id=message.chat.id, filters=filters.user(OWNER_ID))
            if user_sessions.get(user_id) == False:
                raise Exception("Process cancelled")
            asyncio.create_task(auto_delete_message(bot_message, user_message))
            return await extract_tg_link(user_message.text.strip())

        async def auto_delete_message(bot_message, user_message):
            await asyncio.sleep(10)
            await bot_message.delete()
            await user_message.delete()

        # Get the start and end message IDs
        start_msg_id = int(await get_user_input("Send first msg link"))
        end_msg_id = int(await get_user_input("Send end msg link"))

        batch_size = 199

        for start in range(int(start_msg_id), int(end_msg_id) + 1, batch_size):            
            if user_sessions.get(user_id) == False:
                raise Exception("Process cancelled")
            end = min(start + batch_size - 1, int(end_msg_id))
            file_messages = await bot.get_messages(DB_CHANNEL_ID, range(start, end + 1))

            for file_message in file_messages:
                await message_queue.put(file_message)

    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")
    finally:
        user_sessions.pop(user_id, None)

@bot.on_message(filters.private & filters.command("cancel") & filters.user(OWNER_ID))
async def cancel_process(client, message):
    user_id = message.from_user.id
    user_sessions[user_id] = False
    await message.reply_text("Process has been cancelled.")

@bot.on_message(filters.private & filters.command('broadcast') & filters.user(OWNER_ID))
async def send_text(client, message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0
        
        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        for chat_id in query:
            try:
                await asyncio.sleep(3)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1
        
        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
        
        return await pls_wait.edit(status)

    else:
        msg = await message.reply("<code>Use this command as a replay to any telegram message with out any spaces.</code>")
        await asyncio.sleep(8)
        await msg.delete()

@bot.on_message(filters.command('users') & filters.private & filters.user(OWNER_ID))
async def get_users(client, message):
    msg = await client.send_message(chat_id=message.chat.id, text="Please Wait..")
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")

@bot.on_message(filters.command("log") & filters.user(OWNER_ID))
async def log_command(client, message):
    user_id = message.from_user.id

    try:
        reply = await bot.send_document(user_id, document=LOG_FILE_NAME, caption="Bot Log File")
        await auto_delete_message(message, reply)
    except Exception as e:
        await bot.send_message(user_id, f"Failed to send log file. Error: {str(e)}")

async def process_queue():
    while True:
        message = await message_queue.get()  
        if message is None:  
            break
        await process_message(bot, message) 
        message_queue.task_done()

async def process_message(client, message):

    await asyncio.sleep(3)

    media = message.document or message.video or message.audio

    if media:
        caption = message.caption if message.caption else media.file_name
        file_name = await remove_extension(caption)   
        file_size = humanbytes(media.file_size)
        thumbnail = media.thumbs[0].file_id if media.thumbs else None
        if message.video:
            duration = TimeFormatter(media.duration * 1000)
        else:
            duration = ""
        if message.audio:
            audio_path = await bot.download_media(message.audio.file_id)
            audio_thumb = await get_audio_thumbnail(audio_path)

        file_id = message.id
        v_info = f"<blockquote expandable><b>{file_name}</b></blockquote>\n<blockquote><b>{file_size}</b></blockquote>\n<blockquote><b>{duration}</b></blockquote>"
        if message.audio:
            a_info = f"<blockquote ><b>{media.title}</b></blockquote>\n<blockquote><b>{media.performer}</b></blockquote>"

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Send in DM", url=f"https://telegram.dog/{bot_username}?start={file_id}")]])

        try:
            if thumbnail:
                await bot.send_photo(
                    UPDATE_CHANNEL_ID,
                    photo=thumbnail,
                    caption=v_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard
                    )
            elif not message.audio:
                await bot.send_message(
                    UPDATE_CHANNEL_ID,
                    text=v_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard 
                    )
                
            if message.audio:
                await bot.send_photo(
                    UPDATE_CHANNEL_ID,
                    photo=audio_thumb,
                    caption=a_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard
                    )
                os.remove(audio_path) 

        except (WebpageMediaEmpty, WebpageCurlFailed):
            logger.info(f"{thumbnail}")
            await bot.send_message(
                UPDATE_CHANNEL_ID,
                text=v_info,
                parse_mode=enums.ParseMode.HTML,
                reply_markup=keyboard
                )
            
        except FloodWait as f:
            await asyncio.sleep(f.value)
            await process_message(client, message)

        except Exception as e:
            await bot.send_message(OWNER_ID, text=f"Error in Proccessing MSG:{file_name} {e}")

@bot.on_message(filters.command('restart') & filters.private & filters.user(OWNER_ID))
async def restart(client, message):
    os.system("python3 update.py")  
    os.execl(sys.executable, sys.executable, "bot.py")

async def verify_token(user_id, input_token):
    current_time = tm()

    # Check if the user_id exists in user_data
    if user_id not in user_data:
        return 'Token Mismatched ❌' 
    
    stored_token = user_data[user_id]['token']
    if input_token == stored_token:
        token = str(uuid.uuid4())
        user_data[user_id] = {"token": token, "time": current_time, "status": "verified", "file_count": 0}
        return f'Token Verified ✅ (Validity: {get_readable_time(TOKEN_TIMEOUT)})'
    else:
        return f'Token Mismatched ❌'
    
async def check_access(message, user_id):
    if user_id in user_data:
        time = user_data[user_id]['time']
        status = user_data[user_id]['status']
        file_count = user_data[user_id].get('file_count', 0)
        expiry = time + TOKEN_TIMEOUT
        current_time = tm()
        if current_time < expiry and status == "verified":
            if file_count < DAILY_LIMIT:
                return True
            else:
                reply = await message.reply_text(f"You have reached the limit. Please wait until the token expires")
                await auto_delete_message(message, reply)
                return False
        else:
            button = await update_token(user_id)
            send_message = await message.reply_text( 
                                                    text=f"👋 Welcome! Please renew your token now using the link below to access your files instantly. 🚀", 
                                                    reply_markup=button
                                                    )
            await auto_delete_message(message, send_message)
            return False
    else:
        button = await genrate_token(user_id)
        send_message = await message.reply_text( 
                                                text=f"👋 Welcome! Please renew your token now using the link below to access your files instantly. 🚀", 
                                                reply_markup=button
                                                )     
           
        await auto_delete_message(message, send_message)
        return False
    
async def update_token(user_id):
    try:
        time = user_data[user_id]['time']
        expiry = time + TOKEN_TIMEOUT
        if time < expiry:
            token = user_data[user_id]['token']
        else:
            token = str(uuid.uuid4())
        current_time = tm()
        user_data[user_id] = {"token": token, "time": current_time, "status": "unverified", "file_count": 0}
        urlshortx = await shorten_url(f'https://telegram.dog/{bot_username}?start=token_{token}')
        token_url = f'https://telegram.me/{bot_username}?start=token'
        button1 = InlineKeyboardButton("🎟️ Get Token", url=urlshortx)
        button2 = InlineKeyboardButton("How to get verified ✅", url=token_url)
        button = InlineKeyboardMarkup([[button1], [button2]]) 
        return button
    except Exception as e:
        logger.error(f"error in update_token: {e}")

async def genrate_token(user_id):
    try:
        token = str(uuid.uuid4())
        current_time = tm()
        user_data[user_id] = {"token": token, "time": current_time, "status": "unverified", "file_count": 0}
        urlshortx = await shorten_url(f'https://telegram.me/{bot_username}?start=token_{token}')
        token_url = f'https://telegram.dog/{bot_username}?start=token'
        button1 = InlineKeyboardButton("🎟️ Get Token", url=urlshortx)
        button2 = InlineKeyboardButton("How to get verified ✅", url=token_url)
        button = InlineKeyboardMarkup([[button1], [button2]]) 
        return button
    except Exception as e:
        logger.error(f"error in genrate_token: {e}")

async def greet_user(message):
    user_link = await get_user_link(message.from_user)

    greeting_text = (
        f"Hello {user_link}, 👋\n\n"
        "Welcome to FileShare Bot! 🌟\n\n"
        "Here, you can easily access files.\n"
        "<b>○ Creator : <b>TG⚡️FLIX</b>"
        "\n<b>○ Language : Python</b>"
    )

    rply = await message.reply_text(
        text=greeting_text
        )
    
    await auto_delete_message(message, rply)

async def get_user_link(user: User) -> str:
    try:
        user_id = user.id if hasattr(user, 'id') else None
        first_name = user.first_name if hasattr(user, 'first_name') else "Unknown"
    except Exception as e:
        logger.info(f"{e}")
        user_id = None
        first_name = "Unknown"
    
    if user_id:
        return f'<a href=tg://user?id={user_id}>{first_name}</a>'
    else:
        return first_name

async def main():
    await asyncio.create_task(process_queue())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot.send_message(LOG_CHANNEL_ID,"Bot Started ✅")
    
    try:
        bot.loop.run_until_complete(main())
        bot.loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down gracefully...")
    finally:
        logger.info("Bot has stopped.")
