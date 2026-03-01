# PDF Password Cracker - PRD

## Original Problem Statement
User wants a Telegram bot for PDF password cracking with:
- Password format: NAME (first 4 letters CAPS) + YEAR (1900-2026)
- Example: ROHI2006 for name "Rohit" born in 2006
- Admin Dashboard with edit options for bot token and chat ID

## User Personas
- Individual user needing PDF password recovery using name+birth year combinations

## Core Requirements (Static)
1. Telegram Bot Integration
   - Accept PDF files
   - Accept name input
   - Try password combinations automatically
   - Send notifications on success/failure

2. Admin Dashboard
   - Bot token management
   - Chat ID configuration
   - Manual PDF cracking
   - History/logs view

3. Password Format
   - First 4 letters of name (UPPERCASE)
   - Year from 1900 to 2026
   - Total: 127 combinations per name

## Tech Stack
- Frontend: React with Tailwind CSS
- Backend: FastAPI (Python)
- Database: MongoDB
- PDF Library: pikepdf
- Telegram: httpx (HTTP calls to Telegram API)

## What's Been Implemented (Jan 2026)
- [x] Admin Dashboard with dark hacker theme
- [x] Bot token & Chat ID settings management
- [x] Manual PDF crack from dashboard
- [x] Telegram bot polling for messages
- [x] PDF password cracking with pikepdf
- [x] Crack history with status tracking
- [x] Telegram notifications on crack complete
- [x] All 4 tabs: STATUS, SETTINGS, MANUAL CRACK, HISTORY

## API Endpoints
- GET /api/settings - Get bot configuration
- POST /api/settings - Update bot configuration
- GET /api/status - Get bot running status
- GET /api/attempts - Get crack history
- POST /api/crack - Manual crack (file upload)
- POST /api/bot/start - Start bot polling
- POST /api/bot/stop - Stop bot polling

## Telegram Bot Commands
- /start - Welcome message
- /status - Recent crack attempts
- Send PDF → Bot asks for name → Starts cracking

## Prioritized Backlog
### P0 (Done)
- Core cracking functionality
- Admin dashboard
- Telegram integration

### P1 (Future)
- Add lowercase password variants (rohi2006)
- Add full name support (ROHIT2006)
- Progress bar in dashboard

### P2 (Future)
- Multiple PDF batch processing
- Custom year range selection
- Export crack history

## Next Tasks
1. Get Telegram Bot Token from @BotFather
2. Configure token in Settings
3. Start using bot!
