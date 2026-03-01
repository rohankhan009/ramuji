# PDF Cracker + Aadhaar Bot - Deployment Guide

## 🚀 Quick Start (Indian VPS)

### 1. Requirements
- Ubuntu 20.04+ / Debian 11+
- Python 3.10+
- MongoDB
- 2GB RAM minimum

### 2. Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python
sudo apt install python3.11 python3.11-venv python3-pip -y

# Install MongoDB
sudo apt install mongodb -y
sudo systemctl enable mongodb
sudo systemctl start mongodb

# Install Playwright dependencies
sudo apt install libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 -y
```

### 3. Setup Project

```bash
# Create directory
mkdir -p /opt/aadhaar-bot
cd /opt/aadhaar-bot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python packages
pip install fastapi uvicorn motor pymongo pikepdf httpx python-dotenv playwright

# Install Playwright browsers
playwright install chromium
```

### 4. Configuration

Create `.env` file:
```bash
nano /opt/aadhaar-bot/.env
```

Add these lines:
```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=pdf_cracker
UMANG_MOBILE=9503939471
UMANG_MPIN=989162
```

### 5. Copy Files

Copy these files to `/opt/aadhaar-bot/`:
- `server.py`
- `aadhaar_automation.py`

### 6. Run the Server

```bash
cd /opt/aadhaar-bot
source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8001
```

### 7. Setup Telegram Bot

1. Open Telegram, search @BotFather
2. Send `/newbot`
3. Follow instructions, get token
4. Open: `http://YOUR_SERVER_IP:8001/api/settings`
5. Or use curl:

```bash
curl -X POST "http://localhost:8001/api/settings" \
  -H "Content-Type: application/json" \
  -d '{"bot_token": "YOUR_BOT_TOKEN", "chat_id": ""}'
```

### 8. Run as Service (Optional)

Create systemd service:
```bash
sudo nano /etc/systemd/system/aadhaar-bot.service
```

Add:
```ini
[Unit]
Description=Aadhaar PDF Bot
After=network.target mongodb.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aadhaar-bot
Environment=PATH=/opt/aadhaar-bot/venv/bin
ExecStart=/opt/aadhaar-bot/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable aadhaar-bot
sudo systemctl start aadhaar-bot
sudo systemctl status aadhaar-bot
```

---

## 📱 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Show menu |
| `/aadhaar` | Start Aadhaar download |
| `/status` | Show recent attempts |
| `/cancel` | Cancel current operation |

## 🔄 Aadhaar Flow

1. Send `/aadhaar`
2. Bot auto-logs into Umang
3. Enter NAME (as per Aadhaar)
4. Solve CAPTCHA (image sent by bot)
5. Get EID automatically
6. Enter enrollment date/time
7. Solve MyAadhaar CAPTCHA
8. Enter OTP (sent to phone)
9. Receive PDF + Password!

## 🔧 Troubleshooting

### Bot not responding
```bash
# Check logs
sudo journalctl -u aadhaar-bot -f

# Restart service
sudo systemctl restart aadhaar-bot
```

### MongoDB issues
```bash
sudo systemctl restart mongodb
```

### Playwright issues
```bash
# Reinstall browsers
playwright install chromium --with-deps
```

---

## 📁 File Structure

```
/opt/aadhaar-bot/
├── venv/
├── server.py
├── aadhaar_automation.py
└── .env
```

---

## 🔒 Security Notes

1. Change default Umang credentials in `.env`
2. Use firewall to restrict port 8001
3. Don't expose API to public internet
4. Use HTTPS in production

```bash
# Allow only localhost
sudo ufw allow from 127.0.0.1 to any port 8001
```

---

## 🇮🇳 Indian VPS Recommendations

| Provider | Price | Location |
|----------|-------|----------|
| DigitalOcean | $6/mo | Mumbai |
| AWS Lightsail | $5/mo | Mumbai |
| Hostinger | ₹299/mo | India |
| Linode | $5/mo | Mumbai |

---

## 📞 Support

If issues persist, check:
1. MongoDB is running
2. Correct bot token
3. Server has Indian IP
4. Playwright browsers installed
