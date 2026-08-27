import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def click_and_screenshot(youtube_url):
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
        
        time.sleep(2)
        
        print("Download button par click kar rahe hain...")
        try:
            # Screenshot mein jo 'Download' button dikh raha hai use target karna
            download_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Download')]")))
            driver.execute_script("arguments[0].scrollIntoView(true);", download_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", download_btn)
            print("Download button par click ho gaya!")
        except Exception as e:
            print("Button click error:", e)
        
        # 10 seconds wait taaki naya page/format load ho jaye
        print("10 seconds wait kar rahe hain...")
        time.sleep(10)
        
        # Naye page ka screenshot lena
        screenshot_path = "ytgot_screenshot.png"
        driver.save_screenshot(screenshot_path)
        print(f"\nNaya screenshot successfully save ho gaya: {screenshot_path}")
        
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
    click_and_screenshot(link)
