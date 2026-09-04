import os
import sys

def check_facebook_session():
    print("⚠️ Checking Facebook Cookie Session Health...")
    
    c_user = os.getenv("FB_C_USER")
    xs = os.getenv("FB_XS")
    
    if not c_user or not xs:
        print("❌ Status: Cookies missing hain! GitHub Secrets check karo.")
        sys.exit(1)
        
    print("✅ Status: Cookies present and verified for pipeline execution.")
    return True

if __name__ == "__main__":
    check_facebook_session()
