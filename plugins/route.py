from aiohttp import web
import re
import math
import logging
import secrets
import mimetypes
import pytz  # Added missing import
from datetime import datetime, timedelta  # Added missing imports
from pyrogram import enums  # Added missing import for ParseMode

from database.users_chats_db import db
from aiohttp.http_exceptions import BadStatusLine
from Jisshu.bot import multi_clients, work_loads
from Jisshu.server.exceptions import FIleNotFound, InvalidHash
from Jisshu.util.custom_dl import ByteStreamer
from Jisshu.util.render_template import render_page
from info import *

routes = web.RouteTableDef()


@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("Telegram ~ ProBotXUpdate")


@routes.get("/addpremium/{user_id}/{time}")
async def webhook_add_premium(request):
    user_id_str = request.match_info.get('user_id')
    time_str = request.match_info.get('time')

    try:
        user_id = int(user_id_str)
        
        # FIX: Fetch the bot instance before checking if it exists
        bot = request.app.get('bot')
        if not bot:
            return web.Response(text="Bot instance not found in app", status=500)
        
        seconds = get_seconds(time_str)
        if seconds <= 0:
            return web.Response(text="Invalid time format", status=400)

        IST = pytz.timezone("Asia/Kolkata")
        now = datetime.now(IST)
        
        data = await db.get_user(user_id)
        
        if data and data.get("expiry_time"):
            current_expiry = data.get("expiry_time")
            
            # MongoDB timezone fix
            if current_expiry.tzinfo is None:
                current_expiry = pytz.utc.localize(current_expiry).astimezone(IST)
                
            base_time = max(current_expiry, now)
            expiry_time = base_time + timedelta(seconds=seconds)
        else:
            expiry_time = now + timedelta(seconds=seconds)
        
        await db.update_user({"id": user_id, "expiry_time": expiry_time})
        expiry_str = expiry_time.strftime("%d-%m-%Y %I:%M:%S %p")
        
        try:
            user = await bot.get_users(user_id)
            msg = (
                f"🎉 <b>ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ!</b> {user.mention},\n"
                f"<i>ʏᴏᴜ'ᴠᴇ ɢᴏᴛ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ!</i> 💎\n\n"
                f"⏳ <b>ᴅᴜʀᴀᴛɪᴏɴ:</b> <code>{time_str}</code>\n"
                f"📅 <b>ᴇxᴘɪʀʏ:</b> <code>{expiry_str}</code>\n\n"
                f"<i>✨ ᴇɴᴊᴏʏ ʏᴏᴜʀ ᴜʟᴛɪᴍᴀᴛᴇ ᴘʀᴇᴍɪᴜᴍ ʙᴇɴᴇꜰɪᴛꜱ!</i>"
            )
            await bot.send_message(user_id, text=msg, parse_mode=enums.ParseMode.HTML)
            
            # Assuming LOG_CHANNEL and PREMIUM_LOGS are imported from 'info'
            if LOG_CHANNEL:
                log_msg = f"✅ <b>𝐈𝐦𝐝𝐛𝐅𝐢𝐥𝐞𝐬 𝐁𝐨𝐭 ⚝\n\nᴡᴇʙʜᴏᴏᴋ ꜱᴜᴄᴄᴇꜱꜱ:</b> ᴘʀᴇᴍɪᴜᴍ ᴀᴅᴅᴇᴅ ᴛᴏ <code>{user_id}</code> ꜰᴏʀ <code>{time_str}</code>"
                await bot.send_message(PREMIUM_LOGS, text=log_msg, parse_mode=enums.ParseMode.HTML)
                
        except Exception as n_err:
            logging.error(f"Notification error: {n_err}")

        return web.Response(text=f"Successfully added premium to {user_id} until {expiry_str}", status=200)

    except Exception as e:
        return web.Response(text=f"Error: {str(e)}", status=500)


# --- ⏱️ HELPER FUNCTIONS ---

def get_seconds(time_str):
    time_units = {
        'year': 31536000, 'month': 2592000, 'week': 604800,
        'day': 86400, 'hour': 3600, 'min': 60
    }
    for unit, sec in time_units.items():
        if unit in time_str:
            try:
                # Group 1 captures the number, we multiply it by the seconds
                num = int(re.search(r'(\d+)', time_str).group(1))
                return num * sec
            except (AttributeError, ValueError): 
                # Replaced bare except with specific exceptions
                continue
    return -1
    
    
@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return web.Response(
            text=await render_page(id, secure_hash), content_type="text/html"
        )
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))


@routes.get(r"/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return await media_streamer(request, id, secure_hash)
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))


class_cache = {}


async def media_streamer(request: web.Request, id: int, secure_hash: str):
    range_header = request.headers.get("Range", 0)

    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]

    if MULTI_CLIENT:
        logging.info(f"Client {index} is now serving {request.remote}")

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
        logging.debug(f"Using cached ByteStreamer object for client {index}")
    else:
        logging.debug(f"Creating new ByteStreamer object for client {index}")
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect
    logging.debug("before calling get_file_properties")
    file_id = await tg_connect.get_file_properties(id)
    logging.debug("after calling get_file_properties")

    if file_id.unique_id[:6] != secure_hash:
        logging.debug(f"Invalid hash for message with ID {id}")
        raise InvalidHash

    file_size = file_id.file_size

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        until_bytes = (request.http_range.stop or file_size) - 1

    if (until_bytes > file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = 1024 * 1024
    until_bytes = min(until_bytes, file_size - 1)

    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1

    req_length = until_bytes - from_bytes + 1
    part_count = math.ceil(until_bytes / chunk_size) - math.floor(offset / chunk_size)
    body = tg_connect.yield_file(
        file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )

    mime_type = file_id.mime_type
    file_name = file_id.file_name
    disposition = "attachment"

    if mime_type:
        if not file_name:
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_id.file_name)
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": f"{mime_type}",
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        },
    )
