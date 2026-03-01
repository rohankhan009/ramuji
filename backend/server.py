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
from aadhaar_automation import get_or_create_session, cleanup_session, AadhaarAutomation

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Telegram bot instance (will be initialized when settings are loaded)
telegram_bot_running = False
telegram_polling_task = None

# Define Models
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
    status: str  # "pending", "cracking", "success", "failed"
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

# Helper function to generate password combinations
def generate_passwords(name: str) -> List[str]:
    """Generate password combinations: NAME (first 4 letters CAPS) + YEAR (1900-2026)"""
    name_part = name[:4].upper()
    passwords = []
    for year in range(1900, 2027):
        passwords.append(f"{name_part}{year}")
    return passwords

# PDF cracking function
async def crack_pdf(file_path: str, name: str, attempt_id: str, chat_id: int = None, bot_token: str = None):
    """Try to crack PDF password using name+year combinations"""
    passwords = generate_passwords(name)
    total = len(passwords)
    
    # Update attempt with total
    await db.crack_attempts.update_one(
        {"id": attempt_id},
        {"$set": {"total_attempts": total, "status": "cracking", "chat_id": chat_id}}
    )
    
    found_password = None
    attempts_tried = 0
    
    for password in passwords:
        attempts_tried += 1
        try:
            # Try to open PDF with this password
            with pikepdf.open(file_path, password=password) as pdf:
                found_password = password
                break
        except pikepdf.PasswordError:
            continue
        except Exception as e:
            logging.error(f"Error trying password: {e}")
            continue
        
        # Update progress every 50 attempts
        if attempts_tried % 50 == 0:
            await db.crack_attempts.update_one(
                {"id": attempt_id},
                {"$set": {"attempts_tried": attempts_tried}}
            )
    
    # Get attempt details for notification
    attempt = await db.crack_attempts.find_one({"id": attempt_id}, {"_id": 0})
    
    # Update final status
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
        # Send telegram notification directly to the chat
        if chat_id and bot_token:
            message = f"✅ PDF CRACKED!\n\n📄 File: {attempt['filename']}\n👤 Name: {attempt['name_used']}\n🔑 Password: {found_password}\n📊 Attempts: {attempts_tried}/{total}"
            await send_telegram_message(bot_token, chat_id, message)
        else:
            await send_telegram_notification(attempt_id, found_password)
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
            message = f"❌ CRACK FAILED\n\n📄 File: {attempt['filename']}\n👤 Name: {attempt['name_used']}\n📊 Tried: {attempts_tried}/{total} combinations\n\nPassword not in NAME+YEAR format"
            await send_telegram_message(bot_token, chat_id, message)
        else:
            await send_telegram_notification(attempt_id, None)
    
    # Cleanup temp file
    try:
        os.remove(file_path)
    except:
        pass
    
    return found_password

async def send_telegram_notification(attempt_id: str, password: Optional[str]):
    """Send notification to telegram about crack result"""
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if not settings or not settings.get("bot_token") or not settings.get("chat_id"):
        return
    
    attempt = await db.crack_attempts.find_one({"id": attempt_id}, {"_id": 0})
    if not attempt:
        return
    
    bot_token = settings["bot_token"]
    chat_id = settings["chat_id"]
    
    if password:
        message = f"✅ PDF CRACKED!\n\n📄 File: {attempt['filename']}\n👤 Name: {attempt['name_used']}\n🔑 Password: {password}\n📊 Attempts: {attempt['attempts_tried']}"
    else:
        message = f"❌ CRACK FAILED\n\n📄 File: {attempt['filename']}\n👤 Name: {attempt['name_used']}\n📊 Attempts: {attempt['attempts_tried']}/{attempt['total_attempts']}"
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": message}
            )
    except Exception as e:
        logging.error(f"Failed to send telegram message: {e}")

# Telegram bot polling handler
async def handle_telegram_updates():
    """Poll for telegram updates and handle messages"""
    global telegram_bot_running
    
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if not settings or not settings.get("bot_token"):
        telegram_bot_running = False
        return
    
    bot_token = settings["bot_token"]
    last_update_id = 0
    error_count = 0
    
    # First validate the token
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            data = response.json()
            if not data.get("ok"):
                logging.error(f"Invalid bot token: {data.get('description', 'Unknown error')}")
                telegram_bot_running = False
                return
            logging.info(f"Bot connected: @{data['result'].get('username', 'unknown')}")
    except Exception as e:
        logging.error(f"Failed to validate bot token: {e}")
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
                    logging.error(f"Telegram API error: {data.get('description', 'Unknown')}")
                    if error_count >= 5:
                        logging.error("Too many errors, stopping bot")
                        telegram_bot_running = False
                        break
                    await asyncio.sleep(5)
                    continue
                
                error_count = 0  # Reset on success
                
                if data.get("result"):
                    for update in data["result"]:
                        last_update_id = update["update_id"]
                        await process_telegram_update(update, bot_token)
        except asyncio.CancelledError:
            logging.info("Bot polling cancelled")
            break
        except Exception as e:
            logging.error(f"Error polling telegram: {e}")
            error_count += 1
            if error_count >= 5:
                logging.error("Too many errors, stopping bot")
                telegram_bot_running = False
                break
            await asyncio.sleep(5)

async def process_telegram_update(update: dict, bot_token: str):
    """Process a single telegram update"""
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    document = message.get("document")
    
    if not chat_id:
        return
    
    # Handle /start command
    if text == "/start":
        await send_telegram_message(bot_token, chat_id, 
            "🔓 PDF Password Cracker Bot\n\n"
            "📤 Send me a PDF file with the name to try.\n"
            "Format: Send PDF, then reply with name\n\n"
            "Example: If name is 'Rohit' born in 2006\n"
            "Password tried: ROHI2006, ROHI2005, etc."
        )
        return
    
    # Handle /status command
    if text == "/status":
        attempts = await db.crack_attempts.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
        if attempts:
            status_text = "📊 Recent Attempts:\n\n"
            for a in attempts:
                status_emoji = "✅" if a["status"] == "success" else "❌" if a["status"] == "failed" else "⏳"
                status_text += f"{status_emoji} {a['filename'][:20]}... - {a['status']}\n"
        else:
            status_text = "No crack attempts yet."
        await send_telegram_message(bot_token, chat_id, status_text)
        return
    
    # Handle document (PDF file)
    if document:
        file_name = document.get("file_name", "unknown.pdf")
        if not file_name.lower().endswith(".pdf"):
            await send_telegram_message(bot_token, chat_id, "❌ Please send a PDF file only!")
            return
        
        # Store pending file info
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
            f"📄 Received: {file_name}\n\n"
            "👤 Now send the NAME to try (first 4 letters will be used)\n"
            "Example: Send 'Rohit' to try ROHI1900, ROHI1901...ROHI2026"
        )
        return
    
    # Handle name input (if there's a pending file)
    if text and not text.startswith("/"):
        pending = await db.pending_files.find_one({"chat_id": chat_id}, {"_id": 0})
        if pending:
            name = text.strip()
            if len(name) < 4:
                await send_telegram_message(bot_token, chat_id, "❌ Name must be at least 4 characters!")
                return
            
            await send_telegram_message(bot_token, chat_id, 
                f"⏳ Starting crack for: {pending['file_name']}\n"
                f"👤 Name: {name} (using {name[:4].upper()})\n"
                f"🔢 Trying {2027-1900} combinations..."
            )
            
            # Download the file
            try:
                async with httpx.AsyncClient() as http_client:
                    # Get file path
                    file_response = await http_client.get(
                        f"https://api.telegram.org/bot{bot_token}/getFile",
                        params={"file_id": pending["file_id"]}
                    )
                    file_data = file_response.json()
                    file_path = file_data["result"]["file_path"]
                    
                    # Download file
                    download_response = await http_client.get(
                        f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
                    )
                    
                    # Save to temp file
                    temp_dir = tempfile.mkdtemp()
                    local_path = os.path.join(temp_dir, pending["file_name"])
                    with open(local_path, "wb") as f:
                        f.write(download_response.content)
                    
                    # Create crack attempt
                    attempt = CrackAttempt(
                        filename=pending["file_name"],
                        name_used=name,
                        status="pending",
                        created_at=datetime.now(timezone.utc).isoformat()
                    )
                    await db.crack_attempts.insert_one(attempt.model_dump())
                    
                    # Start cracking with chat_id and bot_token for direct notification
                    asyncio.create_task(crack_pdf(local_path, name, attempt.id, chat_id, bot_token))
                    
                    # Remove pending file
                    await db.pending_files.delete_one({"chat_id": chat_id})
                    
            except Exception as e:
                logging.error(f"Error downloading file: {e}")
                await send_telegram_message(bot_token, chat_id, f"❌ Error downloading file: {str(e)}")
        else:
            await send_telegram_message(bot_token, chat_id, 
                "📤 Please send a PDF file first, then I'll ask for the name."
            )

async def send_telegram_message(bot_token: str, chat_id: int, text: str):
    """Send message via telegram bot"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text}
            )
    except Exception as e:
        logging.error(f"Failed to send message: {e}")

# API Routes
@api_router.get("/")
async def root():
    return {"message": "PDF Cracker API"}

@api_router.get("/settings", response_model=BotSettings)
async def get_settings():
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if not settings:
        settings = {"bot_token": "", "chat_id": "", "updated_at": ""}
    return settings

@api_router.post("/settings")
async def update_settings(settings: BotSettingsUpdate):
    global telegram_bot_running, telegram_polling_task
    
    # Stop existing bot if running
    telegram_bot_running = False
    if telegram_polling_task:
        telegram_polling_task.cancel()
        try:
            await telegram_polling_task
        except asyncio.CancelledError:
            pass
        telegram_polling_task = None
    
    # Validate token if provided
    if settings.bot_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as http_client:
                response = await http_client.get(f"https://api.telegram.org/bot{settings.bot_token}/getMe")
                data = response.json()
                if not data.get("ok"):
                    raise HTTPException(status_code=400, detail=f"Invalid bot token: {data.get('description', 'Unknown error')}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"Failed to validate token: {str(e)}")
    
    # Save settings
    doc = {
        "bot_token": settings.bot_token,
        "chat_id": settings.chat_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.bot_settings.update_one({}, {"$set": doc}, upsert=True)
    
    # Start bot if token is set
    bot_started = False
    if settings.bot_token:
        telegram_bot_running = True
        telegram_polling_task = asyncio.create_task(handle_telegram_updates())
        bot_started = True
    
    return {"message": "Settings updated", "bot_started": bot_started}

@api_router.post("/validate-token")
async def validate_token(token: str = Form(...)):
    """Validate a telegram bot token"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = response.json()
            if data.get("ok"):
                return {
                    "valid": True,
                    "bot_name": data["result"].get("first_name", ""),
                    "bot_username": data["result"].get("username", "")
                }
            else:
                return {"valid": False, "error": data.get("description", "Unknown error")}
    except Exception as e:
        return {"valid": False, "error": str(e)}

@api_router.get("/status")
async def get_bot_status():
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    return BotStatus(
        is_running=telegram_bot_running,
        bot_token_set=bool(settings and settings.get("bot_token")),
        chat_id_set=bool(settings and settings.get("chat_id")),
        last_checked=datetime.now(timezone.utc).isoformat()
    )

@api_router.get("/attempts", response_model=List[CrackAttempt])
async def get_attempts():
    attempts = await db.crack_attempts.find({}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return attempts

@api_router.post("/crack")
async def manual_crack(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...)
):
    """Manual crack from dashboard"""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    if len(name) < 4:
        raise HTTPException(status_code=400, detail="Name must be at least 4 characters")
    
    # Save uploaded file
    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, file.filename)
    with open(local_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Create attempt record
    attempt = CrackAttempt(
        filename=file.filename,
        name_used=name,
        status="pending",
        created_at=datetime.now(timezone.utc).isoformat()
    )
    await db.crack_attempts.insert_one(attempt.model_dump())
    
    # Start cracking in background
    background_tasks.add_task(crack_pdf_sync, local_path, name, attempt.id)
    
    return {"message": "Crack started", "attempt_id": attempt.id}

def crack_pdf_sync(file_path: str, name: str, attempt_id: str):
    """Sync wrapper for async crack function"""
    asyncio.run(crack_pdf(file_path, name, attempt_id))

@api_router.delete("/attempts/{attempt_id}")
async def delete_attempt(attempt_id: str):
    result = await db.crack_attempts.delete_one({"id": attempt_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return {"message": "Deleted"}

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

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    global telegram_bot_running, telegram_polling_task
    # Auto-start bot if token exists
    settings = await db.bot_settings.find_one({}, {"_id": 0})
    if settings and settings.get("bot_token"):
        telegram_bot_running = True
        telegram_polling_task = asyncio.create_task(handle_telegram_updates())
        logger.info("Telegram bot started automatically")

@app.on_event("shutdown")
async def shutdown_db_client():
    global telegram_bot_running
    telegram_bot_running = False
    client.close()
