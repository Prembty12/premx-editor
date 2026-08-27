import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def take_ytgot_screenshot(youtube_url):
    print("Browser shuru ho raha hai...")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        print("Website khol rahe hain: https://ytgot.com/")
        driver.get("https://ytgot.com/")
        time.sleep(5)
        
        wait = WebDriverWait(driver, 25)
        
        print("Input box mein link paste kiya ja raha hai...")
        search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='text' or contains(@placeholder, 'Paste')]")))
        search_box.clear()
        search_box.send_keys(youtube_url)
        print("Link successfully paste ho gaya!")
        
        print("10 seconds wait kar rahe hain...")
        time.sleep(10)
        
        screenshot_path = "ytgot_screenshot.png"
        driver.save_screenshot(screenshot_path)
        print(f"\nScreenshot successfully save ho gaya: {screenshot_path}")
        
    except Exception as e:
        import traceback
        print(f"\nCRITICAL ERROR DETAILS:")
        traceback.print_exc()
    
    finally:
        driver.quit()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        link = sys.argv[1]
    else:
        link = input("YouTube ka link yahan paste karein: ")
    take_ytgot_screenshot(link)
