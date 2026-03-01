"""
PDF Password Cracker + Aadhaar Download Bot
Complete Telegram Bot with Umang + MyAadhaar automation
"""
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import pikepdf
import asyncio
import httpx
import tempfile
import shutil
import base64
from aadhaar_automation import get_or_create_session, cleanup_session

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'pdf_cracker')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# FastAPI app
app = FastAPI(title="PDF Cracker + Aadhaar Bot")
api_router = APIRouter(prefix="/api")

# Bot state
telegram_bot_running = False
telegram_polling_task = None

# User session states
user_aadhaar_state: Dict[int, Dict[str, Any]] = {}

# Default credentials (change these!)
DEFAULT_UMANG_MOBILE = os.environ.get('UMANG_MOBILE', '9503939471')
DEFAULT_UMANG_MPIN = os.environ.get('UMANG_MPIN', '989162')

# Models
class BotSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bot_token: str = ""
    chat_id: str = ""
    updated_at: str = ""

class BotSettingsUpdate(BaseModel):
    bot_token: str
    chat_id: str

class CrackAttempt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    name_used: str
    status: str
    password_found: Optional[str] = None
    attempts_tried: int = 0
    total_attempts: int = 0
    created_at: str = ""
    completed_at: Optional[str] = None

class BotStatus(BaseModel):
    is_running: bool
    bot_token_set: bool
    chat_id_set: bool
    last_checked: str


# ============== PASSWORD GENERATION ==============

def generate_passwords(name: str) -> List[str]:
    """Generate NAME(4 letters CAPS) + YEAR combinations"""
    name_part = name[:4].upper()
    passwords = []
    for year in range(1900, 2027):
        passwords.append(f"{name_part}{year}")
    return passwords


# ============== PDF CRACKING ==============

async def crack_pdf(file_path: str, name: str, attempt_id: str, chat_id: int = None, bot_token: str = None):
    """Crack PDF password"""
    passwords = generate_passwords(name)
    total = len(passwords)
    
    await db.crack_attempts.update_one(
        {"id": attempt_id},
        {"$set": {"total_attempts": total, "status": "cracking"}}
    )
    
    found_password = None
    attempts_tried = 0
    
    for password in passwords:
        attempts_tried += 1
        try:
            with pikepdf.open(file_path, password=password) as pdf:
                found_password = password
                break
        except pikepdf.PasswordError:
            continue
        except Exception as e:
            logging.error(f"Error: {e}")
            continue
    
    attempt = await db.crack_attempts.find_one({"id": attempt_id}, {"_id": 0})
    
    if found_password:
        await db.crack_attempts.update_one(
            {"id": attempt_id},
            {"$set": {
                "status": "success",
                "password_found": found_password,
                "attempts_tried": attempts_tried,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        if chat_id and bot_token:
            msg = f"✅ PDF CRACKED!\n\n📄 File: {attempt['filename']}\n👤 Name: {attempt['name_used']}\n🔑 Password: {found_password}\n📊 Attempts: {attempts_tried}/{total}"
            await send_telegram_message(bot_token, chat_id, msg)
    else:
        await db.crack_attempts.update_one(
            {"id": attempt_id},
            {"$set": {
                "status": "failed",
                "attempts_tried": attempts_tried,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        if chat_id and bot_token:
            msg = f"❌ CRACK FAILED\n\n📄 File: {attempt['filename']}\n👤 Name: {attempt['name_used']}\n📊 Tried: {attempts_tried}/{total}"
            await send_telegram_message(bot_token, chat_id, msg)
    
    try:
        os.remove(file_path)
    except:
        pass
    
    return found_password


# ============== TELEGRAM HELPERS ==============

async def send_telegram_message(bot_token: str, chat_id: int, text: str):
    """Send text message"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            )
    except Exception as e:
        logging.error(f"Send message error: {e}")

async def send_telegram_photo(bot_token: str, chat_id: int, photo_base64: str, caption: str = ""):
    """Send photo"""
    try:
        photo_bytes = base64.b64decode(photo_base64)
        async with httpx.AsyncClient() as client:
            files = {"photo": ("captcha.png", photo_bytes, "image/png")}
            data = {"chat_id": chat_id, "caption": caption}
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                files=files,
                data=data
            )
    except Exception as e:
        logging.error(f"Send photo error: {e}")

async def send_telegram_document(bot_token: str, chat_id: int, file_path: str, caption: str = ""):
    """Send document"""
    try:
        with open(file_path, "rb") as f:
            file_content = f.read()
        async with httpx.AsyncClient() as client:
            files = {"document": ("aadhaar.pdf", file_content, "application/pdf")}
            data = {"chat_id": chat_id, "caption": caption}
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendDocument",
                files=files,
                data=data
            )
    except Exception as e:
        logging.error(f"Send document error: {e}")


# ============== TELEGRAM BOT POLLING ==============

async def handle_telegram_updates():
    """Main polling loop"""
    global telegram_bot_running
    
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if not settings or not settings.get("bot_token"):
        telegram_bot_running = False
        return
    
    bot_token = settings["bot_token"]
    last_update_id = 0
    error_count = 0
    
    # Validate token
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            data = response.json()
            if not data.get("ok"):
                logging.error(f"Invalid token: {data.get('description')}")
                telegram_bot_running = False
                return
            logging.info(f"Bot connected: @{data['result'].get('username')}")
    except Exception as e:
        logging.error(f"Token validation failed: {e}")
        telegram_bot_running = False
        return
    
    while telegram_bot_running:
        try:
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                response = await http_client.get(
                    f"https://api.telegram.org/bot{bot_token}/getUpdates",
                    params={"offset": last_update_id + 1, "timeout": 20}
                )
                data = response.json()
                
                if not data.get("ok"):
                    error_count += 1
                    if error_count >= 5:
                        telegram_bot_running = False
                        break
                    await asyncio.sleep(5)
                    continue
                
                error_count = 0
                
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    await process_telegram_update(update, bot_token)
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Polling error: {e}")
            error_count += 1
            if error_count >= 5:
                telegram_bot_running = False
                break
            await asyncio.sleep(5)


async def process_telegram_update(update: dict, bot_token: str):
    """Process single update"""
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    document = message.get("document")
    
    if not chat_id:
        return
    
    # Check if in Aadhaar flow
    if chat_id in user_aadhaar_state:
        await handle_aadhaar_flow(chat_id, text, bot_token)
        return
    
    # /start
    if text == "/start":
        await send_telegram_message(bot_token, chat_id,
            "🔓 <b>PDF Cracker + Aadhaar Bot</b>\n\n"
            "📋 <b>Commands:</b>\n"
            "/aadhaar - Download Aadhaar PDF (auto)\n"
            "/crack - Just crack PDF password\n"
            "/status - Recent attempts\n"
            "/cancel - Cancel current operation\n\n"
            "📤 Or send a PDF file directly to crack password!"
        )
        return
    
    # /aadhaar - Start Aadhaar flow
    if text == "/aadhaar":
        user_aadhaar_state[chat_id] = {
            "step": "start",
            "bot_token": bot_token,
            "mobile": DEFAULT_UMANG_MOBILE,
            "mpin": DEFAULT_UMANG_MPIN
        }
        
        await send_telegram_message(bot_token, chat_id,
            "🆔 <b>Aadhaar Download Service</b>\n\n"
            "⏳ Logging into Umang..."
        )
        
        # Auto login
        session = await get_or_create_session(chat_id)
        result = await session.umang_login(DEFAULT_UMANG_MOBILE, DEFAULT_UMANG_MPIN)
        
        if result.get("success"):
            user_aadhaar_state[chat_id]["step"] = "awaiting_name"
            await send_telegram_message(bot_token, chat_id,
                "✅ Login successful!\n\n"
                "👤 Enter the <b>NAME</b> (as per Aadhaar):"
            )
        else:
            if result.get("screenshot"):
                await send_telegram_photo(bot_token, chat_id, result["screenshot"], "Login page")
            await send_telegram_message(bot_token, chat_id,
                f"❌ Login failed: {result.get('message')}\n\nSend /aadhaar to retry."
            )
            await cleanup_session(chat_id)
            if chat_id in user_aadhaar_state:
                del user_aadhaar_state[chat_id]
        return
    
    # /cancel
    if text == "/cancel":
        if chat_id in user_aadhaar_state:
            await cleanup_session(chat_id)
            del user_aadhaar_state[chat_id]
        await db.pending_files.delete_one({"chat_id": chat_id})
        await send_telegram_message(bot_token, chat_id, "❌ Cancelled.")
        return
    
    # /status
    if text == "/status":
        attempts = await db.crack_attempts.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
        if attempts:
            status_text = "📊 <b>Recent Attempts:</b>\n\n"
            for a in attempts:
                emoji = "✅" if a["status"] == "success" else "❌" if a["status"] == "failed" else "⏳"
                pwd = f" | 🔑 {a['password_found']}" if a.get('password_found') else ""
                status_text += f"{emoji} {a['filename'][:25]}...{pwd}\n"
        else:
            status_text = "No attempts yet."
        await send_telegram_message(bot_token, chat_id, status_text)
        return
    
    # PDF file
    if document:
        file_name = document.get("file_name", "file.pdf")
        if not file_name.lower().endswith(".pdf"):
            await send_telegram_message(bot_token, chat_id, "❌ PDF files only!")
            return
        
        await db.pending_files.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "chat_id": chat_id,
                "file_id": document["file_id"],
                "file_name": file_name,
                "created_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        await send_telegram_message(bot_token, chat_id,
            f"📄 Received: <b>{file_name}</b>\n\n"
            "👤 Send the <b>NAME</b> to try (first 4 letters + years 1900-2026)"
        )
        return
    
    # Text input - check for pending file
    if text and not text.startswith("/"):
        pending = await db.pending_files.find_one({"chat_id": chat_id}, {"_id": 0})
        if pending:
            name = text.strip()
            if len(name) < 4:
                await send_telegram_message(bot_token, chat_id, "❌ Name must be 4+ characters!")
                return
            
            await send_telegram_message(bot_token, chat_id,
                f"⏳ Cracking: <b>{pending['file_name']}</b>\n"
                f"👤 Using: <b>{name[:4].upper()}</b> + years 1900-2026"
            )
            
            try:
                async with httpx.AsyncClient() as http_client:
                    file_response = await http_client.get(
                        f"https://api.telegram.org/bot{bot_token}/getFile",
                        params={"file_id": pending["file_id"]}
                    )
                    file_data = file_response.json()
                    file_path = file_data["result"]["file_path"]
                    
                    download_response = await http_client.get(
                        f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
                    )
                    
                    temp_dir = tempfile.mkdtemp()
                    local_path = os.path.join(temp_dir, pending["file_name"])
                    with open(local_path, "wb") as f:
                        f.write(download_response.content)
                    
                    attempt = CrackAttempt(
                        filename=pending["file_name"],
                        name_used=name,
                        status="pending",
                        created_at=datetime.now(timezone.utc).isoformat()
                    )
                    await db.crack_attempts.insert_one(attempt.model_dump())
                    
                    asyncio.create_task(crack_pdf(local_path, name, attempt.id, chat_id, bot_token))
                    await db.pending_files.delete_one({"chat_id": chat_id})
                    
            except Exception as e:
                logging.error(f"Download error: {e}")
                await send_telegram_message(bot_token, chat_id, f"❌ Error: {str(e)}")
        else:
            await send_telegram_message(bot_token, chat_id,
                "📤 Send a PDF first, or use /aadhaar"
            )


# ============== AADHAAR FLOW HANDLER ==============

async def handle_aadhaar_flow(chat_id: int, text: str, bot_token: str):
    """Handle multi-step Aadhaar download flow"""
    state = user_aadhaar_state.get(chat_id, {})
    step = state.get("step", "")
    
    try:
        # Step: Name input
        if step == "awaiting_name":
            name = text.strip()
            user_aadhaar_state[chat_id]["name"] = name
            user_aadhaar_state[chat_id]["step"] = "navigating"
            
            await send_telegram_message(bot_token, chat_id, "⏳ Going to EID retrieval page...")
            
            session = await get_or_create_session(chat_id)
            result = await session.umang_goto_eid_retrieval()
            
            if result.get("screenshot"):
                await send_telegram_photo(bot_token, chat_id, result["screenshot"], "Current page")
            
            # Fill form
            mobile = user_aadhaar_state[chat_id]["mobile"]
            form_result = await session.umang_fill_eid_form(name, mobile)
            
            if form_result.get("captcha_image"):
                user_aadhaar_state[chat_id]["step"] = "awaiting_umang_captcha"
                await send_telegram_photo(bot_token, chat_id, form_result["captcha_image"], "🔡 Enter CAPTCHA:")
            else:
                if form_result.get("screenshot"):
                    await send_telegram_photo(bot_token, chat_id, form_result["screenshot"], "Form page")
                await send_telegram_message(bot_token, chat_id,
                    f"⚠️ {form_result.get('message', 'Check screenshot')}\n\n"
                    "🔡 Type the CAPTCHA you see:"
                )
                user_aadhaar_state[chat_id]["step"] = "awaiting_umang_captcha"
        
        # Step: Umang CAPTCHA
        elif step == "awaiting_umang_captcha":
            captcha = text.strip()
            user_aadhaar_state[chat_id]["step"] = "submitting_umang_captcha"
            
            await send_telegram_message(bot_token, chat_id, "⏳ Submitting CAPTCHA...")
            
            session = await get_or_create_session(chat_id)
            result = await session.umang_submit_captcha(captcha)
            
            if result.get("success") and result.get("eid"):
                eid = result["eid"]
                user_aadhaar_state[chat_id]["eid"] = eid
                user_aadhaar_state[chat_id]["step"] = "going_to_myaadhaar"
                
                await send_telegram_message(bot_token, chat_id,
                    f"✅ EID Found: <b>{eid}</b>\n\n"
                    "⏳ Going to MyAadhaar download page..."
                )
                
                # Go to MyAadhaar
                myaadhaar_result = await session.myaadhaar_goto_download()
                
                if myaadhaar_result.get("success"):
                    user_aadhaar_state[chat_id]["step"] = "awaiting_eid_details"
                    await send_telegram_message(bot_token, chat_id,
                        "📋 Enter enrollment details:\n\n"
                        "Format: <b>DD/MM/YYYY HH:MM</b>\n"
                        "Example: 15/03/2023 10:30"
                    )
                else:
                    if myaadhaar_result.get("screenshot"):
                        await send_telegram_photo(bot_token, chat_id, myaadhaar_result["screenshot"], "MyAadhaar page")
                    await send_telegram_message(bot_token, chat_id,
                        f"❌ Error: {myaadhaar_result.get('message')}"
                    )
            else:
                if result.get("screenshot"):
                    await send_telegram_photo(bot_token, chat_id, result["screenshot"], "Result")
                await send_telegram_message(bot_token, chat_id,
                    f"❌ {result.get('message', 'EID not found')}\n\nSend /aadhaar to retry."
                )
                await cleanup_session(chat_id)
                del user_aadhaar_state[chat_id]
        
        # Step: EID date/time details
        elif step == "awaiting_eid_details":
            # Parse date and time
            parts = text.strip().split()
            if len(parts) >= 2:
                date_str = parts[0]  # DD/MM/YYYY
                time_str = parts[1]  # HH:MM
            else:
                await send_telegram_message(bot_token, chat_id,
                    "❌ Format: DD/MM/YYYY HH:MM\nExample: 15/03/2023 10:30"
                )
                return
            
            user_aadhaar_state[chat_id]["date"] = date_str
            user_aadhaar_state[chat_id]["time"] = time_str
            user_aadhaar_state[chat_id]["step"] = "filling_myaadhaar"
            
            await send_telegram_message(bot_token, chat_id, "⏳ Filling MyAadhaar form...")
            
            session = await get_or_create_session(chat_id)
            eid = user_aadhaar_state[chat_id]["eid"]
            
            result = await session.myaadhaar_fill_eid(eid, date_str, time_str)
            
            if result.get("captcha_image"):
                user_aadhaar_state[chat_id]["step"] = "awaiting_myaadhaar_captcha"
                await send_telegram_photo(bot_token, chat_id, result["captcha_image"], "🔡 Enter MyAadhaar CAPTCHA:")
            else:
                if result.get("screenshot"):
                    await send_telegram_photo(bot_token, chat_id, result["screenshot"], "Form")
                await send_telegram_message(bot_token, chat_id, "🔡 Type the CAPTCHA:")
                user_aadhaar_state[chat_id]["step"] = "awaiting_myaadhaar_captcha"
        
        # Step: MyAadhaar CAPTCHA
        elif step == "awaiting_myaadhaar_captcha":
            captcha = text.strip()
            user_aadhaar_state[chat_id]["step"] = "sending_otp"
            
            await send_telegram_message(bot_token, chat_id, "⏳ Sending OTP...")
            
            session = await get_or_create_session(chat_id)
            result = await session.myaadhaar_submit_captcha_send_otp(captcha)
            
            if result.get("screenshot"):
                await send_telegram_photo(bot_token, chat_id, result["screenshot"], "OTP page")
            
            user_aadhaar_state[chat_id]["step"] = "awaiting_otp"
            await send_telegram_message(bot_token, chat_id,
                "📱 OTP sent to registered mobile!\n\n"
                "🔢 Enter the 6-digit OTP:"
            )
        
        # Step: OTP verification
        elif step == "awaiting_otp":
            otp = text.strip()
            user_aadhaar_state[chat_id]["step"] = "downloading"
            
            await send_telegram_message(bot_token, chat_id, "⏳ Verifying OTP & downloading Aadhaar...")
            
            session = await get_or_create_session(chat_id)
            result = await session.myaadhaar_verify_otp_download(otp)
            
            if result.get("success") and result.get("file_path"):
                file_path = result["file_path"]
                name = user_aadhaar_state[chat_id].get("name", "Unknown")
                
                await send_telegram_message(bot_token, chat_id, "⏳ Cracking PDF password...")
                
                # Crack password
                passwords = generate_passwords(name)
                found_password = None
                
                for password in passwords:
                    try:
                        with pikepdf.open(file_path, password=password) as pdf:
                            found_password = password
                            break
                    except:
                        continue
                
                if found_password:
                    await send_telegram_document(bot_token, chat_id, file_path,
                        f"✅ <b>Aadhaar Downloaded!</b>\n\n🔑 Password: <b>{found_password}</b>"
                    )
                else:
                    await send_telegram_document(bot_token, chat_id, file_path,
                        "✅ Aadhaar Downloaded!\n\n❌ Could not crack password."
                    )
                
                await cleanup_session(chat_id)
                del user_aadhaar_state[chat_id]
            else:
                if result.get("screenshot"):
                    await send_telegram_photo(bot_token, chat_id, result["screenshot"], "Result")
                await send_telegram_message(bot_token, chat_id,
                    f"❌ Download failed: {result.get('message')}\n\nSend /aadhaar to retry."
                )
                await cleanup_session(chat_id)
                del user_aadhaar_state[chat_id]
        
        else:
            await send_telegram_message(bot_token, chat_id, "❌ Unknown step. Send /aadhaar to restart.")
            await cleanup_session(chat_id)
            if chat_id in user_aadhaar_state:
                del user_aadhaar_state[chat_id]
    
    except Exception as e:
        logging.error(f"Aadhaar flow error: {e}")
        await send_telegram_message(bot_token, chat_id, f"❌ Error: {str(e)}\n\nSend /aadhaar to retry.")
        await cleanup_session(chat_id)
        if chat_id in user_aadhaar_state:
            del user_aadhaar_state[chat_id]


# ============== API ROUTES ==============

@api_router.get("/")
async def root():
    return {"message": "PDF Cracker + Aadhaar Bot API"}

@api_router.get("/settings")
async def get_settings():
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if not settings:
        settings = {"bot_token": "", "chat_id": "", "updated_at": ""}
    return settings

@api_router.post("/settings")
async def update_settings(settings: BotSettingsUpdate):
    global telegram_bot_running, telegram_polling_task
    
    telegram_bot_running = False
    if telegram_polling_task:
        telegram_polling_task.cancel()
        try:
            await telegram_polling_task
        except:
            pass
        telegram_polling_task = None
    
    # Validate token
    if settings.bot_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as http_client:
                response = await http_client.get(f"https://api.telegram.org/bot{settings.bot_token}/getMe")
                data = response.json()
                if not data.get("ok"):
                    raise HTTPException(status_code=400, detail=f"Invalid token: {data.get('description')}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"Token validation failed: {str(e)}")
    
    doc = {
        "bot_token": settings.bot_token,
        "chat_id": settings.chat_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.bot_settings.update_one({}, {"$set": doc}, upsert=True)
    
    if settings.bot_token:
        telegram_bot_running = True
        telegram_polling_task = asyncio.create_task(handle_telegram_updates())
    
    return {"message": "Settings updated", "bot_started": bool(settings.bot_token)}

@api_router.get("/status")
async def get_bot_status():
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    return BotStatus(
        is_running=telegram_bot_running,
        bot_token_set=bool(settings and settings.get("bot_token")),
        chat_id_set=bool(settings and settings.get("chat_id")),
        last_checked=datetime.now(timezone.utc).isoformat()
    )

@api_router.get("/attempts")
async def get_attempts():
    attempts = await db.crack_attempts.find({}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return attempts

@api_router.post("/bot/start")
async def start_bot():
    global telegram_bot_running, telegram_polling_task
    
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if not settings or not settings.get("bot_token"):
        raise HTTPException(status_code=400, detail="Bot token not configured")
    
    if not telegram_bot_running:
        telegram_bot_running = True
        telegram_polling_task = asyncio.create_task(handle_telegram_updates())
    
    return {"message": "Bot started"}

@api_router.post("/bot/stop")
async def stop_bot():
    global telegram_bot_running, telegram_polling_task
    
    telegram_bot_running = False
    if telegram_polling_task:
        telegram_polling_task.cancel()
        telegram_polling_task = None
    
    return {"message": "Bot stopped"}


# ============== APP SETUP ==============

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@app.on_event("startup")
async def startup():
    global telegram_bot_running, telegram_polling_task
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if settings and settings.get("bot_token"):
        telegram_bot_running = True
        telegram_polling_task = asyncio.create_task(handle_telegram_updates())
        logging.info("Telegram bot started automatically")

@app.on_event("shutdown")
async def shutdown():
    global telegram_bot_running
    telegram_bot_running = False
    client.close()
