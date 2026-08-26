import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def download_video_via_browser(youtube_url):
    print("Browser download ke liye shuru ho raha hai...")
    
    # Download folder set karna
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # Browser ko automatically file download karne ki permission dena
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        print("Website khol rahe hain: https://www.seekin.ai/")
        driver.get("https://www.seekin.ai/")
        
        wait = WebDriverWait(driver, 25)
        
        print("Input box mein link paste kiya ja raha hai...")
        search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='text' or contains(@placeholder, 'http')]")))
        search_box.clear()
        search_box.send_keys(youtube_url)
        
        print("5 seconds wait kar rahe hain...")
        time.sleep(5)
        
        print("Analyze / Download button par click kar rahe hain...")
        try:
            analyze_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Analyze Video')] | //button[contains(., 'Download')]")))
            driver.execute_script("arguments[0].scrollIntoView(true);", analyze_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", analyze_btn)
        except Exception as e:
            print("Button click mein error aaya:", e)
            
        print("Download buttons aane ka wait ho raha hai...")
        time.sleep(8)
        
        print("Browser ke zariye download button par click kar rahe hain...")
        download_clicked = False
        
        for i in range(15):
            try:
                # Page par jitne bhi Download buttons hain, unme se pehle wale par click kar do
                download_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Download')] | //a[contains(., 'Download')]")
                for btn in download_buttons:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", btn)
                        download_clicked = True
                        print("Download button par click ho gaya hai!")
                        break
                if download_clicked:
                    break
            except:
                time.sleep(2)
                
        if download_clicked:
            print("File download ho rahi hai, 15 seconds wait karte hain...")
            time.sleep(15)
            print(f"\nKaam ho gaya! File aapke folder mein save ho gayi hogi.")
        else:
            print("Error: Browser download button nahi daba paya.")

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
    download_video_via_browser(link)
    
