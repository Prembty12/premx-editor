import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def download_1080p_exact_steps(youtube_url):
    print("Browser shuru ho raha hai...")
    
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
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
        time.sleep(5)
        
        wait = WebDriverWait(driver, 25)
        
        print("Link paste kiya ja raha hai...")
        search_box = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
        search_box.clear()
        search_box.send_keys(youtube_url)
        print("Link successfully paste ho gaya!")
        
        # Step 1: Link paste ke baad 5 seconds ka wait
        print("5 seconds wait kar rahe hain...")
        time.sleep(5)
        
        print("Download button par click kar rahe hain...")
        try:
            init_btn = driver.find_element(By.XPATH, "//button[contains(., 'Download') or contains(., 'Analyze')]")
            driver.execute_script("arguments[0].scrollIntoView(true);", init_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", init_btn)
        except Exception as e:
            print("Initial click error:", e)

        # Step 2: Format aane ka wait (10 seconds)
        print("10 seconds wait kar rahe hain taaki 1080p format load ho jaye...")
        time.sleep(10)
        
        print("1080p download button dhoond kar click kar rahe hain...")
        download_clicked = False
        
        for i in range(15):
            try:
                # 1080p ya final download button ko dhoondna
                buttons = driver.find_elements(By.XPATH, "//button[contains(., '1080') or contains(., 'Download')] | //a[contains(., 'Download')]")
                for btn in buttons:
                    if btn.is_displayed():
                        text = btn.text.lower()
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", btn)
                        download_clicked = True
                        print(f"1080p download button par click ho gaya: {text}")
                        break
                if download_clicked:
                    break
            except:
                time.sleep(2)
                
        if download_clicked:
            print("File download ho rahi hai, 15 seconds wait karte hain...")
            time.sleep(15)
            print(f"\nKaam ho gaya! File downloads folder mein save ho gayi hogi.")
        else:
            print("Error: 1080p download button nahi mila.")

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
    download_1080p_exact_steps(link)
