# PDF Cracker + Aadhaar Bot - PRD

## Problem Statement
Telegram bot for:
1. PDF password cracking (NAME + YEAR format: ROHI2006)
2. Aadhaar PDF download via Umang + MyAadhaar automation

## User Personas
- User who forgot PDF password
- User who needs to download Aadhaar with auto password crack

## Core Features

### 1. PDF Password Cracker ✅
- Upload PDF to Telegram
- Enter name
- Bot tries NAME(4 caps) + YEAR (1900-2026)
- Returns cracked password

### 2. Aadhaar Automation ✅
- Auto login to Umang (credentials saved)
- Get Enrollment ID (EID)
- Go to MyAadhaar
- Fill form + solve CAPTCHA
- Enter OTP
- Download PDF + crack password

## Tech Stack
- Backend: FastAPI (Python)
- Database: MongoDB
- Automation: Playwright
- PDF: pikepdf
- Bot: Telegram Bot API (httpx)

## Files Created
- `/app/backend/server.py` - Main API + Telegram bot
- `/app/backend/aadhaar_automation.py` - Umang/MyAadhaar automation
- `/app/backend/Dockerfile` - Docker deployment
- `/app/docker-compose.yml` - Full stack deployment
- `/app/DEPLOYMENT.md` - Deployment guide
- `/app/frontend/` - Admin dashboard

## Bot Commands
| Command | Description |
|---------|-------------|
| /start | Menu |
| /aadhaar | Start Aadhaar download |
| /status | Recent attempts |
| /cancel | Cancel operation |

## Aadhaar Flow
1. /aadhaar → Auto Umang login
2. Enter NAME → Navigate to EID page
3. Solve CAPTCHA → Get EID
4. Enter date/time → Go to MyAadhaar
5. Solve CAPTCHA → Send OTP
6. Enter OTP → Download PDF
7. Auto crack password → Send PDF + Password

## Deployment Notes
- **REQUIRES INDIAN SERVER** - Umang/MyAadhaar block non-Indian IPs
- Recommended: DigitalOcean Mumbai, AWS Mumbai, Hostinger India

## Current Status (Jan 2026)
- [x] PDF Cracker working
- [x] Telegram bot working
- [x] Aadhaar automation code ready
- [x] Deployment files ready
- [ ] Needs Indian VPS to work (CloudFront blocks)

## Default Credentials
- Umang Mobile: 9503939471
- Umang MPIN: 989162
(Change in .env or server.py)

## Next Steps
1. Deploy on Indian VPS
2. Test Aadhaar flow end-to-end
3. Fine-tune selectors if needed
