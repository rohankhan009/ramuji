"""
Aadhaar Download Bot - Clean Version
Only Aadhaar download via Umang + MyAadhaar
"""
from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import pikepdf
import asyncio
import httpx
import base64
from aadhaar_automation import get_or_create_session, cleanup_session

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'aadhaar_bot')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# FastAPI
app = FastAPI(title="Aadhaar Download Bot")
api_router = APIRouter(prefix="/api")

# Bot state
telegram_bot_running = False
telegram_polling_task = None

# User states for Aadhaar flow
user_state: Dict[int, Dict[str, Any]] = {}

# Default Umang credentials
DEFAULT_UMANG_MOBILE = os.environ.get('UMANG_MOBILE', '9503939471')
DEFAULT_UMANG_MPIN = os.environ.get('UMANG_MPIN', '989162')

# Models
class BotSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bot_token: str = ""
    chat_id: str = ""

class BotSettingsUpdate(BaseModel):
    bot_token: str
    chat_id: str


# ============== PASSWORD CRACKER ==============

def generate_passwords(name: str) -> List[str]:
    """Generate NAME(4 caps) + YEAR combinations"""
    name_part = name[:4].upper()
    return [f"{name_part}{year}" for year in range(1900, 2027)]

def crack_pdf_password(file_path: str, name: str) -> Optional[str]:
    """Crack PDF password synchronously"""
    for password in generate_passwords(name):
        try:
            with pikepdf.open(file_path, password=password) as pdf:
                return password
        except pikepdf.PasswordError:
            continue
    return None


# ============== TELEGRAM HELPERS ==============

async def send_msg(bot_token: str, chat_id: int, text: str):
    """Send message"""
    try:
        async with httpx.AsyncClient() as c:
            await c.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            )
    except Exception as e:
        logging.error(f"Send error: {e}")

async def send_photo(bot_token: str, chat_id: int, photo_b64: str, caption: str = ""):
    """Send photo"""
    try:
        async with httpx.AsyncClient() as c:
            await c.post(
                f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                files={"photo": ("img.png", base64.b64decode(photo_b64), "image/png")},
                data={"chat_id": chat_id, "caption": caption}
            )
    except Exception as e:
        logging.error(f"Photo error: {e}")

async def send_doc(bot_token: str, chat_id: int, file_path: str, caption: str = ""):
    """Send document"""
    try:
        with open(file_path, "rb") as f:
            async with httpx.AsyncClient() as c:
                await c.post(
                    f"https://api.telegram.org/bot{bot_token}/sendDocument",
                    files={"document": ("aadhaar.pdf", f.read(), "application/pdf")},
                    data={"chat_id": chat_id, "caption": caption}
                )
    except Exception as e:
        logging.error(f"Doc error: {e}")


# ============== BOT POLLING ==============

async def bot_polling():
    """Main polling loop"""
    global telegram_bot_running
    
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if not settings or not settings.get("bot_token"):
        telegram_bot_running = False
        return
    
    bot_token = settings["bot_token"]
    last_id = 0
    
    # Validate
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            if not r.json().get("ok"):
                telegram_bot_running = False
                return
            logging.info(f"Bot: @{r.json()['result'].get('username')}")
    except:
        telegram_bot_running = False
        return
    
    while telegram_bot_running:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(
                    f"https://api.telegram.org/bot{bot_token}/getUpdates",
                    params={"offset": last_id + 1, "timeout": 20}
                )
                data = r.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        last_id = update["update_id"]
                        await handle_update(update, bot_token)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Poll error: {e}")
            await asyncio.sleep(5)


async def handle_update(update: dict, bot_token: str):
    """Handle telegram update"""
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "").strip()
    
    if not chat_id:
        return
    
    # If user in flow, handle flow
    if chat_id in user_state:
        await handle_flow(chat_id, text, bot_token)
        return
    
    # /start
    if text == "/start":
        await send_msg(bot_token, chat_id,
            "🆔 <b>Aadhaar Download Bot</b>\n\n"
            "/aadhaar - Download Aadhaar PDF\n"
            "/cancel - Cancel"
        )
        return
    
    # /aadhaar
    if text == "/aadhaar":
        user_state[chat_id] = {"step": "awaiting_number", "bot_token": bot_token}
        await send_msg(bot_token, chat_id,
            "📱 Enter <b>Mobile Number</b> (registered with Aadhaar):"
        )
        return
    
    # /cancel
    if text == "/cancel":
        if chat_id in user_state:
            await cleanup_session(chat_id)
            del user_state[chat_id]
        await send_msg(bot_token, chat_id, "❌ Cancelled")
        return
    
    await send_msg(bot_token, chat_id, "Send /aadhaar to start")


async def handle_flow(chat_id: int, text: str, bot_token: str):
    """Handle Aadhaar download flow"""
    state = user_state.get(chat_id, {})
    step = state.get("step", "")
    
    try:
        # Step 1: Mobile number input
        if step == "awaiting_number":
            number = text.replace(" ", "")
            if not number.isdigit() or len(number) != 10:
                await send_msg(bot_token, chat_id, "❌ Enter valid 10-digit mobile number:")
                return
            
            user_state[chat_id]["number"] = number
            user_state[chat_id]["step"] = "logging_in"
            
            await send_msg(bot_token, chat_id, "⏳ Logging into Umang...")
            
            session = await get_or_create_session(chat_id)
            result = await session.umang_login(DEFAULT_UMANG_MOBILE, DEFAULT_UMANG_MPIN)
            
            if result.get("success"):
                user_state[chat_id]["step"] = "awaiting_name"
                await send_msg(bot_token, chat_id,
                    "✅ Logged in!\n\n👤 Enter <b>NAME</b> (as per Aadhaar):"
                )
            else:
                if result.get("screenshot"):
                    await send_photo(bot_token, chat_id, result["screenshot"], "Login page")
                await send_msg(bot_token, chat_id, f"❌ Login failed: {result.get('message')}\n\n/aadhaar to retry")
                await cleanup_session(chat_id)
                del user_state[chat_id]
        
        # Step 2: Name input
        elif step == "awaiting_name":
            name = text.strip()
            if len(name) < 2:
                await send_msg(bot_token, chat_id, "❌ Enter valid name:")
                return
            
            user_state[chat_id]["name"] = name
            user_state[chat_id]["step"] = "navigating"
            
            await send_msg(bot_token, chat_id, "⏳ Going to EID retrieval page...")
            
            session = await get_or_create_session(chat_id)
            await session.umang_goto_eid_retrieval()
            
            # Fill form
            number = user_state[chat_id]["number"]
            result = await session.umang_fill_eid_form(name, number)
            
            if result.get("captcha_image"):
                user_state[chat_id]["step"] = "awaiting_umang_captcha"
                await send_photo(bot_token, chat_id, result["captcha_image"], "🔡 Enter CAPTCHA:")
            elif result.get("screenshot"):
                user_state[chat_id]["step"] = "awaiting_umang_captcha"
                await send_photo(bot_token, chat_id, result["screenshot"], "🔡 Type the CAPTCHA you see:")
            else:
                await send_msg(bot_token, chat_id, f"⚠️ {result.get('message')}\n\n🔡 Enter CAPTCHA:")
                user_state[chat_id]["step"] = "awaiting_umang_captcha"
        
        # Step 3: Umang CAPTCHA
        elif step == "awaiting_umang_captcha":
            captcha = text.strip()
            user_state[chat_id]["step"] = "submitting_captcha"
            
            await send_msg(bot_token, chat_id, "⏳ Submitting...")
            
            session = await get_or_create_session(chat_id)
            result = await session.umang_submit_captcha(captcha)
            
            if result.get("success") and result.get("eid"):
                eid = result["eid"]
                user_state[chat_id]["eid"] = eid
                
                await send_msg(bot_token, chat_id, f"✅ EID: <b>{eid}</b>\n\n⏳ Going to MyAadhaar...")
                
                # Go to MyAadhaar
                ma_result = await session.myaadhaar_goto_download()
                
                if ma_result.get("success"):
                    user_state[chat_id]["step"] = "awaiting_date_time"
                    await send_msg(bot_token, chat_id,
                        "📅 Enter enrollment <b>Date & Time</b>:\n\n"
                        "Format: <code>DD/MM/YYYY HH:MM</code>\n"
                        "Example: <code>15/03/2023 10:30</code>"
                    )
                else:
                    if ma_result.get("screenshot"):
                        await send_photo(bot_token, chat_id, ma_result["screenshot"], "MyAadhaar")
                    await send_msg(bot_token, chat_id, f"❌ {ma_result.get('message')}")
            else:
                if result.get("screenshot"):
                    await send_photo(bot_token, chat_id, result["screenshot"], "Result")
                await send_msg(bot_token, chat_id, f"❌ {result.get('message', 'EID not found')}\n\n/aadhaar to retry")
                await cleanup_session(chat_id)
                del user_state[chat_id]
        
        # Step 4: Date/Time input
        elif step == "awaiting_date_time":
            parts = text.strip().split()
            if len(parts) < 2:
                await send_msg(bot_token, chat_id, "❌ Format: DD/MM/YYYY HH:MM")
                return
            
            date_str, time_str = parts[0], parts[1]
            user_state[chat_id]["date"] = date_str
            user_state[chat_id]["time"] = time_str
            
            await send_msg(bot_token, chat_id, "⏳ Filling MyAadhaar form...")
            
            session = await get_or_create_session(chat_id)
            eid = user_state[chat_id]["eid"]
            
            result = await session.myaadhaar_fill_eid(eid, date_str, time_str)
            
            if result.get("captcha_image"):
                user_state[chat_id]["step"] = "awaiting_myaadhaar_captcha"
                await send_photo(bot_token, chat_id, result["captcha_image"], "🔡 Enter CAPTCHA:")
            elif result.get("screenshot"):
                user_state[chat_id]["step"] = "awaiting_myaadhaar_captcha"
                await send_photo(bot_token, chat_id, result["screenshot"], "🔡 Type CAPTCHA:")
            else:
                user_state[chat_id]["step"] = "awaiting_myaadhaar_captcha"
                await send_msg(bot_token, chat_id, "🔡 Enter CAPTCHA:")
        
        # Step 5: MyAadhaar CAPTCHA
        elif step == "awaiting_myaadhaar_captcha":
            captcha = text.strip()
            
            await send_msg(bot_token, chat_id, "⏳ Sending OTP...")
            
            session = await get_or_create_session(chat_id)
            result = await session.myaadhaar_submit_captcha_send_otp(captcha)
            
            if result.get("screenshot"):
                await send_photo(bot_token, chat_id, result["screenshot"], "OTP page")
            
            user_state[chat_id]["step"] = "awaiting_otp"
            await send_msg(bot_token, chat_id, "📱 OTP sent!\n\n🔢 Enter 6-digit OTP:")
        
        # Step 6: OTP verification
        elif step == "awaiting_otp":
            otp = text.strip()
            
            await send_msg(bot_token, chat_id, "⏳ Verifying & downloading...")
            
            session = await get_or_create_session(chat_id)
            result = await session.myaadhaar_verify_otp_download(otp)
            
            if result.get("success") and result.get("file_path"):
                file_path = result["file_path"]
                name = user_state[chat_id].get("name", "")
                
                await send_msg(bot_token, chat_id, "⏳ Cracking password...")
                
                password = crack_pdf_password(file_path, name)
                
                if password:
                    await send_doc(bot_token, chat_id, file_path,
                        f"✅ <b>Aadhaar Downloaded!</b>\n\n🔑 Password: <b>{password}</b>"
                    )
                else:
                    await send_doc(bot_token, chat_id, file_path,
                        "✅ Aadhaar Downloaded!\n\n❌ Password not cracked"
                    )
                
                await cleanup_session(chat_id)
                del user_state[chat_id]
            else:
                if result.get("screenshot"):
                    await send_photo(bot_token, chat_id, result["screenshot"], "Result")
                await send_msg(bot_token, chat_id, f"❌ {result.get('message')}\n\n/aadhaar to retry")
                await cleanup_session(chat_id)
                del user_state[chat_id]
        
        else:
            await send_msg(bot_token, chat_id, "❌ Error. /aadhaar to restart")
            await cleanup_session(chat_id)
            if chat_id in user_state:
                del user_state[chat_id]
    
    except Exception as e:
        logging.error(f"Flow error: {e}")
        await send_msg(bot_token, chat_id, f"❌ Error: {str(e)}\n\n/aadhaar to retry")
        await cleanup_session(chat_id)
        if chat_id in user_state:
            del user_state[chat_id]


# ============== API ==============

@api_router.get("/")
async def root():
    return {"message": "Aadhaar Bot API"}

@api_router.get("/settings")
async def get_settings():
    s = await db.bot_settings.find_one({}, {"_id": 0})
    return s or {"bot_token": "", "chat_id": ""}

@api_router.post("/settings")
async def update_settings(s: BotSettingsUpdate):
    global telegram_bot_running, telegram_polling_task
    
    telegram_bot_running = False
    if telegram_polling_task:
        telegram_polling_task.cancel()
        telegram_polling_task = None
    
    if s.bot_token:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://api.telegram.org/bot{s.bot_token}/getMe")
                if not r.json().get("ok"):
                    raise HTTPException(400, "Invalid token")
        except httpx.RequestError as e:
            raise HTTPException(400, str(e))
    
    await db.bot_settings.update_one({}, {"$set": {"bot_token": s.bot_token, "chat_id": s.chat_id}}, upsert=True)
    
    if s.bot_token:
        telegram_bot_running = True
        telegram_polling_task = asyncio.create_task(bot_polling())
    
    return {"ok": True}

@api_router.get("/status")
async def status():
    s = await db.bot_settings.find_one({}, {"_id": 0})
    return {"running": telegram_bot_running, "token_set": bool(s and s.get("bot_token"))}


# ============== APP ==============

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@app.on_event("startup")
async def startup():
    global telegram_bot_running, telegram_polling_task
    s = await db.bot_settings.find_one({}, {"_id": 0})
    if s and s.get("bot_token"):
        telegram_bot_running = True
        telegram_polling_task = asyncio.create_task(bot_polling())

@app.on_event("shutdown")
async def shutdown():
    global telegram_bot_running
    telegram_bot_running = False
    client.close()
