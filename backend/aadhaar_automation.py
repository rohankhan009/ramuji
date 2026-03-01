"""
Aadhaar Automation Service
Handles Umang login, EID retrieval, and Aadhaar PDF download
"""
import asyncio
import logging
import os
import tempfile
from playwright.async_api import async_playwright, Page, Browser
from typing import Optional, Dict, Any
import base64

logger = logging.getLogger(__name__)

class AadhaarAutomation:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.session_data: Dict[str, Any] = {}
    
    async def init_browser(self):
        """Initialize headless browser"""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            self.page = await self.browser.new_page()
            # Set viewport and user agent to look like real browser
            await self.page.set_viewport_size({"width": 1366, "height": 768})
            await self.page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
    
    async def close_browser(self):
        """Close browser and cleanup"""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
    
    async def login_umang(self, mobile: str, mpin: str) -> Dict[str, Any]:
        """Login to Umang portal"""
        try:
            await self.init_browser()
            
            # Go to Umang login page
            await self.page.goto("https://web.umang.gov.in/landing/login", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Enter mobile number
            mobile_input = await self.page.query_selector('input[type="tel"], input[placeholder*="mobile"], input[name*="mobile"]')
            if mobile_input:
                await mobile_input.fill(mobile)
            else:
                # Try alternative selectors
                await self.page.fill('input[type="text"]', mobile)
            
            await asyncio.sleep(1)
            
            # Click continue/next button
            continue_btn = await self.page.query_selector('button:has-text("Continue"), button:has-text("Next"), button:has-text("Proceed")')
            if continue_btn:
                await continue_btn.click()
            
            await asyncio.sleep(2)
            
            # Enter MPIN
            mpin_input = await self.page.query_selector('input[type="password"], input[placeholder*="MPIN"], input[name*="mpin"]')
            if mpin_input:
                await mpin_input.fill(mpin)
            
            # Click login button
            login_btn = await self.page.query_selector('button:has-text("Login"), button:has-text("Submit"), button[type="submit"]')
            if login_btn:
                await login_btn.click()
            
            await asyncio.sleep(3)
            
            # Check if login successful
            current_url = self.page.url
            if "dashboard" in current_url or "home" in current_url:
                return {"success": True, "message": "Login successful"}
            else:
                # Take screenshot for debugging
                screenshot = await self.page.screenshot()
                return {"success": False, "message": "Login may have failed", "screenshot": base64.b64encode(screenshot).decode()}
            
        except Exception as e:
            logger.error(f"Umang login error: {e}")
            return {"success": False, "message": str(e)}
    
    async def navigate_to_eid_retrieval(self) -> Dict[str, Any]:
        """Navigate to Retrieve EID/Aadhaar page"""
        try:
            # Go to Aadhaar services
            await self.page.goto("https://web.umang.gov.in/web_new/department/service/1756/aadhaar", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Click on "Retrieve EID/Aadhaar Number"
            eid_link = await self.page.query_selector('text=Retrieve EID, text=Retrieve Aadhaar, a:has-text("Retrieve")')
            if eid_link:
                await eid_link.click()
                await asyncio.sleep(2)
            
            return {"success": True, "message": "Navigated to EID retrieval page"}
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return {"success": False, "message": str(e)}
    
    async def fill_eid_form_and_get_captcha(self, name: str, mobile: str) -> Dict[str, Any]:
        """Fill the EID retrieval form and return CAPTCHA image"""
        try:
            # Select Enrollment ID option
            select_option = await self.page.query_selector('select, [role="listbox"]')
            if select_option:
                await select_option.select_option(label="Enrollment ID")
            
            await asyncio.sleep(1)
            
            # Fill Name
            name_input = await self.page.query_selector('input[placeholder*="Name"], input[name*="name"]')
            if name_input:
                await name_input.fill(name)
            
            # Fill Mobile
            mobile_input = await self.page.query_selector('input[placeholder*="Mobile"], input[name*="mobile"], input[type="tel"]')
            if mobile_input:
                await mobile_input.fill(mobile)
            
            await asyncio.sleep(1)
            
            # Get CAPTCHA image
            captcha_img = await self.page.query_selector('img[src*="captcha"], img[alt*="captcha"], .captcha-image img')
            if captcha_img:
                captcha_screenshot = await captcha_img.screenshot()
                return {
                    "success": True, 
                    "captcha_image": base64.b64encode(captcha_screenshot).decode(),
                    "message": "CAPTCHA image captured"
                }
            else:
                # Take full page screenshot if CAPTCHA not found
                screenshot = await self.page.screenshot()
                return {
                    "success": False,
                    "message": "CAPTCHA image not found",
                    "screenshot": base64.b64encode(screenshot).decode()
                }
            
        except Exception as e:
            logger.error(f"Form fill error: {e}")
            return {"success": False, "message": str(e)}
    
    async def submit_captcha_and_get_eid(self, captcha_text: str) -> Dict[str, Any]:
        """Submit CAPTCHA and get Enrollment ID"""
        try:
            # Fill CAPTCHA
            captcha_input = await self.page.query_selector('input[placeholder*="captcha"], input[name*="captcha"], input[placeholder*="Enter the text"]')
            if captcha_input:
                await captcha_input.fill(captcha_text)
            
            # Click Submit
            submit_btn = await self.page.query_selector('button:has-text("Submit"), button:has-text("Get"), button[type="submit"]')
            if submit_btn:
                await submit_btn.click()
            
            await asyncio.sleep(3)
            
            # Look for Enrollment ID in response
            page_content = await self.page.content()
            
            # Try to find EID in the page
            eid_element = await self.page.query_selector('[class*="eid"], [class*="enrollment"], [id*="eid"]')
            if eid_element:
                eid_text = await eid_element.inner_text()
                return {"success": True, "eid": eid_text, "message": "EID retrieved successfully"}
            
            # Take screenshot to see result
            screenshot = await self.page.screenshot()
            return {
                "success": False,
                "message": "Could not find EID in response",
                "screenshot": base64.b64encode(screenshot).decode(),
                "page_content": page_content[:2000]  # First 2000 chars for debugging
            }
            
        except Exception as e:
            logger.error(f"CAPTCHA submit error: {e}")
            return {"success": False, "message": str(e)}
    
    async def download_aadhaar(self, eid: str, aadhaar_number: str = None) -> Dict[str, Any]:
        """Navigate to UIDAI and initiate Aadhaar download"""
        try:
            # Go to UIDAI download page
            await self.page.goto("https://myaadhaar.uidai.gov.in/genricDownloadAadhaar", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Select Enrollment ID option if available
            eid_radio = await self.page.query_selector('input[value="eid"], input[name*="eid"], label:has-text("Enrollment")')
            if eid_radio:
                await eid_radio.click()
            
            await asyncio.sleep(1)
            
            # Fill EID
            eid_input = await self.page.query_selector('input[placeholder*="Enrollment"], input[name*="eid"], input[id*="eid"]')
            if eid_input:
                await eid_input.fill(eid)
            
            # Get CAPTCHA if present
            captcha_img = await self.page.query_selector('img[src*="captcha"], img[alt*="captcha"]')
            if captcha_img:
                captcha_screenshot = await captcha_img.screenshot()
                return {
                    "success": True,
                    "step": "captcha_required",
                    "captcha_image": base64.b64encode(captcha_screenshot).decode(),
                    "message": "CAPTCHA required for UIDAI"
                }
            
            return {"success": True, "step": "ready_for_otp", "message": "Ready to request OTP"}
            
        except Exception as e:
            logger.error(f"UIDAI navigation error: {e}")
            return {"success": False, "message": str(e)}
    
    async def request_otp(self) -> Dict[str, Any]:
        """Request OTP for Aadhaar download"""
        try:
            # Click Send OTP button
            otp_btn = await self.page.query_selector('button:has-text("OTP"), button:has-text("Send"), button:has-text("Generate")')
            if otp_btn:
                await otp_btn.click()
            
            await asyncio.sleep(3)
            
            return {"success": True, "message": "OTP requested. Check your phone."}
            
        except Exception as e:
            logger.error(f"OTP request error: {e}")
            return {"success": False, "message": str(e)}
    
    async def submit_otp_and_download(self, otp: str) -> Dict[str, Any]:
        """Submit OTP and download Aadhaar PDF"""
        try:
            # Fill OTP
            otp_input = await self.page.query_selector('input[placeholder*="OTP"], input[name*="otp"], input[maxlength="6"]')
            if otp_input:
                await otp_input.fill(otp)
            
            # Click Verify/Download button
            verify_btn = await self.page.query_selector('button:has-text("Verify"), button:has-text("Download"), button:has-text("Submit")')
            if verify_btn:
                await verify_btn.click()
            
            await asyncio.sleep(5)
            
            # Wait for download
            # Set up download handling
            download_path = tempfile.mkdtemp()
            
            async with self.page.expect_download() as download_info:
                download_btn = await self.page.query_selector('button:has-text("Download"), a:has-text("Download")')
                if download_btn:
                    await download_btn.click()
            
            download = await download_info.value
            file_path = os.path.join(download_path, "aadhaar.pdf")
            await download.save_as(file_path)
            
            return {"success": True, "file_path": file_path, "message": "Aadhaar PDF downloaded"}
            
        except Exception as e:
            logger.error(f"OTP submit/download error: {e}")
            return {"success": False, "message": str(e)}
    
    async def take_screenshot(self) -> bytes:
        """Take screenshot of current page"""
        if self.page:
            return await self.page.screenshot()
        return None


# Global instance for session management
aadhaar_sessions: Dict[int, AadhaarAutomation] = {}

async def get_or_create_session(chat_id: int) -> AadhaarAutomation:
    """Get existing session or create new one for a chat"""
    if chat_id not in aadhaar_sessions:
        aadhaar_sessions[chat_id] = AadhaarAutomation()
    return aadhaar_sessions[chat_id]

async def cleanup_session(chat_id: int):
    """Cleanup session for a chat"""
    if chat_id in aadhaar_sessions:
        await aadhaar_sessions[chat_id].close_browser()
        del aadhaar_sessions[chat_id]
