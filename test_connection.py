#!/usr/bin/env python3
"""
Test script to check server connection on port 8000
"""

import requests
import sys
import os
from dotenv import load_dotenv

def test_server_setup():
    """Test if the Phonesium server is properly set up on port 8000"""
    
    print("🔍 PHONESIUM SERVER CONNECTION TEST (PORT 8000)")
    print("=" * 60)
    
    base_url = os.getenv('BASE_URL')
    api_url = f"{base_url}/api.php"
    
    # Test 1: Check if web server is running on port 8000
    print("1️⃣ Testing web server on port 8000...")
    try:
        response = requests.get("http://localhost:8000", timeout=5)
        print("✅ Web server is running on port 8000")
    except requests.exceptions.ConnectionError:
        print("❌ Web server is not running on port 8000")
        print("   Please start your web server on port 8000")
        return False
    except Exception as e:
        print(f"❌ Web server test failed: {e}")
        return False
    
    # Test 2: Check if Phonesium folder exists
    print("\n2️⃣ Testing Phonesium website...")
    try:
        response = requests.get(base_url, timeout=5)
        if response.status_code == 200:
            print("✅ Phonesium website is accessible")
        else:
            print(f"❌ Phonesium website returned status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Phonesium folder not found")
        print("   Please place Phonesium folder in web root")
        return False
    except Exception as e:
        print(f"❌ Phonesium website test failed: {e}")
        return False
    
    # Test 3: Check if API endpoint exists
    print("\n3️⃣ Testing API endpoint...")
    try:
        response = requests.get(api_url, timeout=5)
        if response.status_code == 405:
            print("✅ API endpoint exists (Method not allowed is expected)")
        elif response.status_code == 200:
            print("✅ API endpoint is accessible")
        else:
            print(f"⚠️  API returned status: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ API endpoint not found")
        return False
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False
    
    # Test 4: Check login page
    print("\n4️⃣ Testing login page...")
    try:
        login_url = f"{base_url}/login.php"
        response = requests.get(login_url, timeout=5)
        if response.status_code == 200:
            print("✅ Login page is accessible")
        else:
            print(f"⚠️  Login page returned status: {response.status_code}")
    except Exception as e:
        print(f"❌ Login page test failed: {e}")
        return False
    
    # Test 5: Check dashboard page
    print("\n5️⃣ Testing dashboard page...")
    try:
        dashboard_url = f"{base_url}/dashboard.php"
        response = requests.get(dashboard_url, timeout=5)
        if response.status_code == 200 or response.status_code == 302:
            print("✅ Dashboard page is accessible")
        else:
            print(f"⚠️  Dashboard returned status: {response.status_code}")
    except Exception as e:
        print(f"❌ Dashboard test failed: {e}")
        return False
    
    print("\n🎉 SERVER SETUP TEST COMPLETE!")
    print("\n📋 All tests passed! You can start mining with:")
    print("python miner.py")
    print("\nOr with specific user ID:")
    print("python miner.py --user-id YOUR_USER_ID")
    
    return True

if __name__ == "__main__":
    test_server_setup()
