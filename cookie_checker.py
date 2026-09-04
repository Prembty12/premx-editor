import os
import requests

def check_fb_cookies_status():
    c_user = os.environ.get("FB_C_USER")
    xs = os.environ.get("FB_XS")
    
    if not c_user or not xs:
        print("❌ Status: FB_C_USER ya FB_XS environment variables missing hain!")
        return False

    cookies = {'c_user': c_user, 'xs': xs}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        response = requests.get('https://www.facebook.com/profile.php', cookies=cookies, headers=headers, allow_redirects=True, timeout=10)
        
        if 'login' in response.url or 'checkpoint' in response.url:
            print("❌ Status: Cookies EXPIRE ho chuki hain! Please naye c_user aur xs update karo.")
            return False
        
        if c_user in response.text or 'logout' in response.text.lower():
            print("✅ Status: Facebook Cookies bilkul SAHI aur ACTIVE hain!")
            return True
        else:
            print("⚠️ Status: Cookies invalid lag rahi hain, session check failed.")
            return False

    except Exception as e:
        print(f"⚠️ Network connection error while checking cookies: {e}")
        return False

if __name__ == "__main__":
    is_valid = check_fb_cookies_status()
    if not is_valid:
        exit(1)
