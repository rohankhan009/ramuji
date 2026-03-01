"""
Aadhaar Automation Service - Complete Version
Handles Umang login, EID retrieval, and Aadhaar PDF download from MyAadhaar
"""
import asyncio
import logging
import os
import tempfile
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from typing import Optional, Dict, Any
import base64
import re

logger = logging.getLogger(__name__)

class AadhaarAutomation:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.session_data: Dict[str, Any] = {}
    
    async def init_browser(self):
        """Initialize headless browser with anti-detection"""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox', 
                    '--disable-setuid-sandbox', 
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            self.context = await self.browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-IN",
                timezone_id="Asia/Kolkata"
            )
            self.page = await self.context.new_page()
            
            # Anti-detection scripts
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            """)
    
    async def close_browser(self):
        """Close browser and cleanup"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except:
            pass
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
    
    async def take_screenshot(self) -> Optional[str]:
        """Take screenshot and return base64"""
        try:
            if self.page:
                screenshot = await self.page.screenshot()
                return base64.b64encode(screenshot).decode()
        except:
            pass
        return None

    # ============== UMANG FUNCTIONS ==============
    
    async def umang_login(self, mobile: str, mpin: str) -> Dict[str, Any]:
        """Login to Umang portal"""
        try:
            await self.init_browser()
            
            # Go to Umang login page
            logger.info("Going to Umang login page...")
            await self.page.goto("https://web.umang.gov.in/landing/login", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Wait for page to load
            await self.page.wait_for_load_state("networkidle")
            
            # Find and fill mobile number - try multiple selectors
            mobile_filled = False
            selectors_mobile = [
                'input[type="tel"]',
                'input[placeholder*="mobile" i]',
                'input[placeholder*="Mobile" i]',
                'input[name*="mobile" i]',
                'input[id*="mobile" i]',
                '#mobileNo',
                '.mobile-input input',
                'input[maxlength="10"]'
            ]
            
            for selector in selectors_mobile:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=3000)
                    if el:
                        await el.fill(mobile)
                        mobile_filled = True
                        logger.info(f"Mobile filled using: {selector}")
                        break
                except:
                    continue
            
            if not mobile_filled:
                screenshot = await self.take_screenshot()
                return {"success": False, "message": "Could not find mobile input", "screenshot": screenshot}
            
            await asyncio.sleep(1)
            
            # Click continue/proceed button
            continue_clicked = False
            selectors_continue = [
                'button:has-text("Continue")',
                'button:has-text("Proceed")',
                'button:has-text("Next")',
                'button:has-text("Submit")',
                'button[type="submit"]',
                '.continue-btn',
                '.proceed-btn'
            ]
            
            for selector in selectors_continue:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        continue_clicked = True
                        logger.info(f"Continue clicked using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(3)
            
            # Enter MPIN
            mpin_filled = False
            selectors_mpin = [
                'input[type="password"]',
                'input[placeholder*="MPIN" i]',
                'input[placeholder*="mpin" i]',
                'input[placeholder*="PIN" i]',
                'input[name*="mpin" i]',
                'input[name*="pin" i]',
                '#mpin',
                '.mpin-input input'
            ]
            
            for selector in selectors_mpin:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=3000)
                    if el:
                        await el.fill(mpin)
                        mpin_filled = True
                        logger.info(f"MPIN filled using: {selector}")
                        break
                except:
                    continue
            
            if not mpin_filled:
                screenshot = await self.take_screenshot()
                return {"success": False, "message": "Could not find MPIN input", "screenshot": screenshot}
            
            await asyncio.sleep(1)
            
            # Click login button
            selectors_login = [
                'button:has-text("Login")',
                'button:has-text("Sign In")',
                'button:has-text("Submit")',
                'button[type="submit"]',
                '.login-btn',
                '.submit-btn'
            ]
            
            for selector in selectors_login:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        logger.info(f"Login clicked using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(5)
            
            # Check if login successful
            current_url = self.page.url
            page_content = await self.page.content()
            
            if "dashboard" in current_url.lower() or "home" in current_url.lower() or "department" in current_url.lower():
                return {"success": True, "message": "Login successful"}
            elif "error" in page_content.lower() or "invalid" in page_content.lower():
                screenshot = await self.take_screenshot()
                return {"success": False, "message": "Invalid credentials", "screenshot": screenshot}
            else:
                screenshot = await self.take_screenshot()
                return {"success": True, "message": "Login attempted - check screenshot", "screenshot": screenshot}
            
        except Exception as e:
            logger.error(f"Umang login error: {e}")
            screenshot = await self.take_screenshot()
            return {"success": False, "message": str(e), "screenshot": screenshot}
    
    async def umang_goto_eid_retrieval(self) -> Dict[str, Any]:
        """Navigate to Retrieve EID/Aadhaar page in Umang"""
        try:
            # Go to Aadhaar department page
            logger.info("Going to Aadhaar services...")
            await self.page.goto(
                "https://web.umang.gov.in/web_new/department?url=dept%2F17&dept_id=17&dept_name=Aadhaar",
                wait_until="networkidle",
                timeout=60000
            )
            await asyncio.sleep(3)
            
            # Click on "Retrieve EID/Aadhaar Number"
            selectors = [
                'text=Retrieve EID',
                'text=Retrieve Aadhaar',
                'a:has-text("Retrieve")',
                'div:has-text("Retrieve EID")',
                '[class*="service"]:has-text("Retrieve")'
            ]
            
            clicked = False
            for selector in selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=3000)
                    if el:
                        await el.click()
                        clicked = True
                        logger.info(f"Clicked Retrieve EID using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(3)
            
            screenshot = await self.take_screenshot()
            return {"success": clicked, "message": "Navigated to EID page" if clicked else "Could not find EID link", "screenshot": screenshot}
            
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            screenshot = await self.take_screenshot()
            return {"success": False, "message": str(e), "screenshot": screenshot}
    
    async def umang_fill_eid_form(self, name: str, mobile: str) -> Dict[str, Any]:
        """Fill EID retrieval form and get CAPTCHA"""
        try:
            await asyncio.sleep(2)
            
            # Select "Enrollment ID" option if dropdown exists
            try:
                select = await self.page.query_selector('select')
                if select:
                    await select.select_option(label="Enrollment ID")
                    await asyncio.sleep(1)
            except:
                pass
            
            # Fill Name
            name_selectors = [
                'input[placeholder*="Name" i]',
                'input[name*="name" i]',
                'input[id*="name" i]',
                '#fullName',
                '#name'
            ]
            
            for selector in name_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.fill(name)
                        logger.info(f"Name filled using: {selector}")
                        break
                except:
                    continue
            
            # Fill Mobile
            mobile_selectors = [
                'input[placeholder*="Mobile" i]',
                'input[type="tel"]',
                'input[name*="mobile" i]',
                'input[maxlength="10"]',
                '#mobile'
            ]
            
            for selector in mobile_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        current_val = await el.get_attribute("value")
                        if not current_val:  # Don't overwrite if already filled
                            await el.fill(mobile)
                            logger.info(f"Mobile filled using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(1)
            
            # Get CAPTCHA image
            captcha_selectors = [
                'img[src*="captcha" i]',
                'img[alt*="captcha" i]',
                '.captcha img',
                '#captchaImage',
                'img[id*="captcha" i]'
            ]
            
            captcha_base64 = None
            for selector in captcha_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=3000)
                    if el:
                        captcha_screenshot = await el.screenshot()
                        captcha_base64 = base64.b64encode(captcha_screenshot).decode()
                        logger.info(f"CAPTCHA captured using: {selector}")
                        break
                except:
                    continue
            
            if captcha_base64:
                return {"success": True, "captcha_image": captcha_base64, "message": "CAPTCHA captured"}
            else:
                screenshot = await self.take_screenshot()
                return {"success": False, "message": "Could not find CAPTCHA", "screenshot": screenshot}
            
        except Exception as e:
            logger.error(f"Form fill error: {e}")
            screenshot = await self.take_screenshot()
            return {"success": False, "message": str(e), "screenshot": screenshot}
    
    async def umang_submit_captcha(self, captcha_text: str) -> Dict[str, Any]:
        """Submit CAPTCHA and get EID"""
        try:
            # Fill CAPTCHA
            captcha_input_selectors = [
                'input[placeholder*="captcha" i]',
                'input[placeholder*="Enter the text" i]',
                'input[name*="captcha" i]',
                'input[id*="captcha" i]',
                '#captcha',
                '#captchaInput'
            ]
            
            for selector in captcha_input_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.fill(captcha_text)
                        logger.info(f"CAPTCHA filled using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(1)
            
            # Click Submit
            submit_selectors = [
                'button:has-text("Submit")',
                'button:has-text("Get")',
                'button:has-text("Retrieve")',
                'button[type="submit"]',
                'input[type="submit"]',
                '.submit-btn'
            ]
            
            for selector in submit_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        logger.info(f"Submit clicked using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(5)
            
            # Look for EID in response
            page_content = await self.page.content()
            
            # Try to find EID (28 digit or 14 digit number)
            eid_pattern = r'\b(\d{14}|\d{28})\b'
            matches = re.findall(eid_pattern, page_content)
            
            if matches:
                eid = matches[0]
                return {"success": True, "eid": eid, "message": f"EID found: {eid}"}
            
            # Try to find in specific elements
            eid_selectors = [
                '[class*="eid" i]',
                '[class*="enrollment" i]',
                '[id*="eid" i]',
                '.result-text',
                '.eid-number'
            ]
            
            for selector in eid_selectors:
                try:
                    el = await self.page.query_selector(selector)
                    if el:
                        text = await el.inner_text()
                        matches = re.findall(eid_pattern, text)
                        if matches:
                            return {"success": True, "eid": matches[0], "message": f"EID found: {matches[0]}"}
                except:
                    continue
            
            screenshot = await self.take_screenshot()
            return {"success": False, "message": "Could not find EID in response", "screenshot": screenshot}
            
        except Exception as e:
            logger.error(f"CAPTCHA submit error: {e}")
            screenshot = await self.take_screenshot()
            return {"success": False, "message": str(e), "screenshot": screenshot}

    # ============== MYAADHAAR FUNCTIONS ==============
    
    async def myaadhaar_goto_download(self) -> Dict[str, Any]:
        """Go to MyAadhaar download page"""
        try:
            await self.init_browser()
            
            logger.info("Going to MyAadhaar download page...")
            await self.page.goto(
                "https://myaadhaar.uidai.gov.in/genricDownloadAadhaar",
                wait_until="networkidle",
                timeout=60000
            )
            await asyncio.sleep(3)
            
            screenshot = await self.take_screenshot()
            return {"success": True, "message": "MyAadhaar page loaded", "screenshot": screenshot}
            
        except Exception as e:
            logger.error(f"MyAadhaar navigation error: {e}")
            screenshot = await self.take_screenshot()
            return {"success": False, "message": str(e), "screenshot": screenshot}
    
    async def myaadhaar_fill_eid(self, eid: str, date: str, time: str) -> Dict[str, Any]:
        """Fill EID form on MyAadhaar - returns CAPTCHA image"""
        try:
            await asyncio.sleep(2)
            
            # Select "Enrolment ID Number" radio button
            eid_radio_selectors = [
                'input[value*="eid" i]',
                'input[id*="eid" i]',
                'label:has-text("Enrolment ID")',
                'input[type="radio"]:nth-child(2)',
                '#eidRadio'
            ]
            
            for selector in eid_radio_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        logger.info(f"EID radio selected using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(1)
            
            # Fill 14 digit Enrolment Number
            eid_input_selectors = [
                'input[placeholder*="Enrolment" i]',
                'input[placeholder*="14 digit" i]',
                'input[name*="eid" i]',
                'input[maxlength="14"]',
                '#eidNumber',
                '#enrolmentNumber'
            ]
            
            for selector in eid_input_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.fill(eid[:14])  # First 14 digits
                        logger.info(f"EID filled using: {selector}")
                        break
                except:
                    continue
            
            # Fill Date
            date_selectors = [
                'input[placeholder*="date" i]',
                'input[type="date"]',
                'input[name*="date" i]',
                '#date',
                '.date-input'
            ]
            
            for selector in date_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        await el.fill(date)
                        logger.info(f"Date filled using: {selector}")
                        break
                except:
                    continue
            
            # Fill Time
            time_selectors = [
                'input[placeholder*="time" i]',
                'input[type="time"]',
                'input[name*="time" i]',
                '#time',
                '.time-input'
            ]
            
            for selector in time_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        await el.fill(time)
                        logger.info(f"Time filled using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(1)
            
            # Get CAPTCHA image
            captcha_selectors = [
                'img[src*="captcha" i]',
                'img[alt*="captcha" i]',
                '.captcha img',
                '#captchaImage',
                'canvas'  # Some sites use canvas for CAPTCHA
            ]
            
            captcha_base64 = None
            for selector in captcha_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=3000)
                    if el:
                        captcha_screenshot = await el.screenshot()
                        captcha_base64 = base64.b64encode(captcha_screenshot).decode()
                        logger.info(f"CAPTCHA captured using: {selector}")
                        break
                except:
                    continue
            
            if captcha_base64:
                return {"success": True, "captcha_image": captcha_base64, "message": "Form filled, CAPTCHA captured"}
            else:
                screenshot = await self.take_screenshot()
                return {"success": True, "message": "Form filled, check screenshot for CAPTCHA", "screenshot": screenshot}
            
        except Exception as e:
            logger.error(f"MyAadhaar form error: {e}")
            screenshot = await self.take_screenshot()
            return {"success": False, "message": str(e), "screenshot": screenshot}
    
    async def myaadhaar_submit_captcha_send_otp(self, captcha_text: str) -> Dict[str, Any]:
        """Submit CAPTCHA and send OTP"""
        try:
            # Fill CAPTCHA
            captcha_input_selectors = [
                'input[placeholder*="captcha" i]',
                'input[placeholder*="Enter Captcha" i]',
                'input[name*="captcha" i]',
                '#captcha',
                '#captchaInput'
            ]
            
            for selector in captcha_input_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.fill(captcha_text)
                        logger.info(f"CAPTCHA filled using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(1)
            
            # Click Send OTP
            otp_btn_selectors = [
                'button:has-text("Send OTP")',
                'button:has-text("Get OTP")',
                'button:has-text("Request OTP")',
                'input[value*="OTP" i]',
                '#sendOtp',
                '.send-otp-btn'
            ]
            
            for selector in otp_btn_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        logger.info(f"Send OTP clicked using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(5)
            
            screenshot = await self.take_screenshot()
            page_content = await self.page.content()
            
            if "otp sent" in page_content.lower() or "otp has been" in page_content.lower():
                return {"success": True, "message": "OTP sent successfully", "screenshot": screenshot}
            else:
                return {"success": True, "message": "OTP request submitted - check phone", "screenshot": screenshot}
            
        except Exception as e:
            logger.error(f"Send OTP error: {e}")
            screenshot = await self.take_screenshot()
            return {"success": False, "message": str(e), "screenshot": screenshot}
    
    async def myaadhaar_verify_otp_download(self, otp: str) -> Dict[str, Any]:
        """Verify OTP and download Aadhaar PDF"""
        try:
            # Fill OTP
            otp_input_selectors = [
                'input[placeholder*="OTP" i]',
                'input[placeholder*="Enter OTP" i]',
                'input[name*="otp" i]',
                'input[maxlength="6"]',
                '#otp',
                '#otpInput'
            ]
            
            for selector in otp_input_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=3000)
                    if el:
                        await el.fill(otp)
                        logger.info(f"OTP filled using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(1)
            
            # Click Verify/Download button
            verify_selectors = [
                'button:has-text("Verify")',
                'button:has-text("Download")',
                'button:has-text("Submit")',
                'button[type="submit"]',
                '#verifyOtp',
                '#download',
                '.verify-btn',
                '.download-btn'
            ]
            
            for selector in verify_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        logger.info(f"Verify clicked using: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(5)
            
            # Handle download
            download_path = tempfile.mkdtemp()
            file_path = os.path.join(download_path, "aadhaar.pdf")
            
            # Try to catch download
            try:
                async with self.page.expect_download(timeout=30000) as download_info:
                    # Click download button if visible
                    download_btn = await self.page.query_selector('a:has-text("Download"), button:has-text("Download PDF")')
                    if download_btn:
                        await download_btn.click()
                
                download = await download_info.value
                await download.save_as(file_path)
                
                if os.path.exists(file_path):
                    return {"success": True, "file_path": file_path, "message": "Aadhaar PDF downloaded"}
            except Exception as download_error:
                logger.error(f"Download error: {download_error}")
            
            # Alternative: check for inline PDF or download link
            pdf_link = await self.page.query_selector('a[href*=".pdf"], a[download]')
            if pdf_link:
                href = await pdf_link.get_attribute("href")
                return {"success": True, "pdf_url": href, "message": "PDF link found"}
            
            screenshot = await self.take_screenshot()
            return {"success": False, "message": "Could not download PDF", "screenshot": screenshot}
            
        except Exception as e:
            logger.error(f"OTP verify error: {e}")
            screenshot = await self.take_screenshot()
            return {"success": False, "message": str(e), "screenshot": screenshot}


# Global session storage
aadhaar_sessions: Dict[int, AadhaarAutomation] = {}

async def get_or_create_session(chat_id: int) -> AadhaarAutomation:
    """Get existing session or create new one"""
    if chat_id not in aadhaar_sessions:
        aadhaar_sessions[chat_id] = AadhaarAutomation()
    return aadhaar_sessions[chat_id]

async def cleanup_session(chat_id: int):
    """Cleanup session"""
    if chat_id in aadhaar_sessions:
        try:
            await aadhaar_sessions[chat_id].close_browser()
        except:
            pass
        del aadhaar_sessions[chat_id]
