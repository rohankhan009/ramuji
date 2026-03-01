#!/usr/bin/env python3
import requests
import sys
import json
import tempfile
import os
from datetime import datetime
from pathlib import Path

class PDFCrackerAPITester:
    def __init__(self):
        self.base_url = "https://xenodochial-torvalds-1.preview.emergentagent.com/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_result(self, test_name, passed, details="", error_msg=""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            
        result = {
            "test": test_name,
            "passed": passed,
            "details": details,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"\n{status} - {test_name}")
        if details:
            print(f"   Details: {details}")
        if error_msg:
            print(f"   Error: {error_msg}")

    def run_test(self, test_name, method, endpoint, expected_status=200, data=None, files=None):
        """Execute HTTP request and validate response"""
        url = f"{self.base_url}/{endpoint}"
        headers = {}
        
        print(f"\n🔍 Testing {test_name}...")
        print(f"   URL: {url}")
        print(f"   Method: {method}")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method == "POST":
                if files:
                    # For multipart form data (file uploads)
                    response = requests.post(url, data=data, files=files, headers=headers, timeout=30)
                elif data:
                    headers['Content-Type'] = 'application/json'
                    response = requests.post(url, json=data, headers=headers, timeout=30)
                else:
                    response = requests.post(url, headers=headers, timeout=30)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=30)
            
            success = response.status_code == expected_status
            
            if success:
                try:
                    response_data = response.json()
                    details = f"Status: {response.status_code}, Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Non-dict response'}"
                except:
                    details = f"Status: {response.status_code}, Response: {response.text[:100]}"
                self.log_result(test_name, True, details)
                return True, response_data if 'response_data' in locals() else {}
            else:
                try:
                    error_detail = response.json() if response.text else "Empty response"
                except:
                    error_detail = response.text
                self.log_result(test_name, False, f"Expected {expected_status}, got {response.status_code}", str(error_detail))
                return False, {}
                
        except Exception as e:
            self.log_result(test_name, False, "", str(e))
            return False, {}

    def test_api_root(self):
        """Test API root endpoint"""
        return self.run_test("API Root", "GET", "")

    def test_get_settings(self):
        """Test getting bot settings"""
        success, response = self.run_test("Get Bot Settings", "GET", "settings")
        if success and isinstance(response, dict):
            # Check response structure
            expected_keys = {"bot_token", "chat_id", "updated_at"}
            has_keys = all(key in response for key in expected_keys)
            if has_keys:
                print(f"   ✓ Response has all expected keys: {expected_keys}")
                return True, response
            else:
                print(f"   ✗ Missing keys. Expected: {expected_keys}, Got: {list(response.keys())}")
        return success, response

    def test_update_settings(self):
        """Test updating bot settings"""
        test_settings = {
            "bot_token": "test_token_12345",
            "chat_id": "test_chat_123"
        }
        return self.run_test("Update Bot Settings", "POST", "settings", data=test_settings)

    def test_get_status(self):
        """Test getting bot status"""
        success, response = self.run_test("Get Bot Status", "GET", "status")
        if success and isinstance(response, dict):
            expected_keys = {"is_running", "bot_token_set", "chat_id_set", "last_checked"}
            has_keys = all(key in response for key in expected_keys)
            if has_keys:
                print(f"   ✓ Status response structure is correct")
                print(f"   Bot running: {response.get('is_running')}")
                print(f"   Token set: {response.get('bot_token_set')}")
                print(f"   Chat ID set: {response.get('chat_id_set')}")
                return True, response
            else:
                print(f"   ✗ Missing keys in status. Expected: {expected_keys}, Got: {list(response.keys())}")
        return success, response

    def test_get_attempts(self):
        """Test getting crack attempts"""
        success, response = self.run_test("Get Crack Attempts", "GET", "attempts")
        if success:
            attempts_count = len(response) if isinstance(response, list) else 0
            print(f"   ✓ Found {attempts_count} crack attempts")
            if attempts_count > 0:
                # Check structure of first attempt
                attempt = response[0]
                expected_keys = {"id", "filename", "name_used", "status", "created_at"}
                has_keys = all(key in attempt for key in expected_keys)
                if has_keys:
                    print(f"   ✓ Attempt structure is correct")
                else:
                    print(f"   ✗ Attempt missing keys. Expected: {expected_keys}, Got: {list(attempt.keys())}")
        return success, response

    def create_test_pdf(self):
        """Create a simple test PDF with known password"""
        try:
            import pikepdf
            
            # Create a simple PDF
            pdf = pikepdf.new()
            page = pdf.add_blank_page()
            
            # Create temporary file
            temp_dir = tempfile.mkdtemp()
            pdf_path = os.path.join(temp_dir, "test_document.pdf")
            
            # Save without password first
            pdf.save(pdf_path)
            pdf.close()
            
            # Now encrypt it with known password
            password = "TEST2023"  # This should match format: TEST + year
            with pikepdf.open(pdf_path) as source_pdf:
                encrypted_path = os.path.join(temp_dir, "encrypted_test.pdf")
                source_pdf.save(encrypted_path, encryption=pikepdf.Encryption(owner=password, user=password))
            
            return encrypted_path, password, "TEST"  # Return path, password, and name to try
            
        except ImportError:
            print("   ⚠️ pikepdf not available for creating test PDF")
            return None, None, None
        except Exception as e:
            print(f"   ⚠️ Error creating test PDF: {e}")
            return None, None, None

    def test_manual_crack(self):
        """Test manual PDF cracking functionality"""
        pdf_path, expected_password, test_name = self.create_test_pdf()
        
        if not pdf_path:
            self.log_result("Manual Crack (PDF Creation)", False, "", "Could not create test PDF")
            return False, {}
        
        try:
            # Prepare multipart form data
            with open(pdf_path, 'rb') as f:
                files = {'file': ('test_document.pdf', f, 'application/pdf')}
                data = {'name': test_name}
                
                success, response = self.run_test(
                    "Manual PDF Crack", 
                    "POST", 
                    "crack", 
                    expected_status=200,
                    data=data,
                    files=files
                )
                
                if success and isinstance(response, dict):
                    if "attempt_id" in response:
                        print(f"   ✓ Crack started with ID: {response['attempt_id']}")
                        
                        # Wait a moment and check attempts to see if it was created
                        import time
                        time.sleep(2)
                        attempts_success, attempts = self.test_get_attempts()
                        if attempts_success and attempts:
                            recent_attempt = attempts[0]  # Most recent should be first
                            if recent_attempt.get('id') == response['attempt_id']:
                                print(f"   ✓ Crack attempt recorded successfully")
                                print(f"   Status: {recent_attempt.get('status')}")
                                return True, response
                        
                return success, response
                        
        except Exception as e:
            self.log_result("Manual Crack (Execution)", False, "", str(e))
            return False, {}
        finally:
            # Cleanup
            try:
                if pdf_path and os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    # Also remove the directory
                    temp_dir = os.path.dirname(pdf_path)
                    if os.path.exists(temp_dir):
                        os.rmdir(temp_dir)
            except:
                pass

    def test_bot_control(self):
        """Test bot start/stop endpoints"""
        # Test bot start
        start_success, start_response = self.run_test("Start Bot", "POST", "bot/start", expected_status=200)
        
        # Test bot stop  
        stop_success, stop_response = self.run_test("Stop Bot", "POST", "bot/stop", expected_status=200)
        
        return start_success and stop_success

    def run_all_tests(self):
        """Execute all API tests"""
        print("🚀 Starting PDF Cracker API Tests")
        print(f"📡 Base URL: {self.base_url}")
        print("=" * 60)
        
        # Test API availability
        self.test_api_root()
        
        # Test core endpoints
        self.test_get_settings()
        self.test_update_settings()
        self.test_get_status()
        self.test_get_attempts()
        
        # Test bot control
        self.test_bot_control()
        
        # Test manual crack functionality
        self.test_manual_crack()
        
        # Print final results
        print("\n" + "=" * 60)
        print(f"📊 TEST SUMMARY")
        print(f"   Total Tests: {self.tests_run}")
        print(f"   Passed: {self.tests_passed}")
        print(f"   Failed: {self.tests_run - self.tests_passed}")
        print(f"   Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%" if self.tests_run > 0 else "   Success Rate: 0%")
        
        if self.tests_passed == self.tests_run:
            print("🎉 ALL TESTS PASSED!")
            return 0
        else:
            print("⚠️ SOME TESTS FAILED")
            
            # Print failed tests
            failed_tests = [r for r in self.test_results if not r['passed']]
            if failed_tests:
                print("\n❌ FAILED TESTS:")
                for test in failed_tests:
                    print(f"   • {test['test']}: {test['error']}")
            
            return 1

def main():
    """Main test execution"""
    tester = PDFCrackerAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())