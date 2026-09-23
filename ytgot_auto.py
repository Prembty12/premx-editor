import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def download_video_fully(youtube_url):
    print("Browser shuru ho raha hai...")
    
    # Download folder set karna
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # Browser preferences to force download into the 'downloads' folder
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
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
        
        print("Initial Download button par click kar rahe hain...")
        download_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Download')]")))
        driver.execute_script("arguments[0].scrollIntoView(true);", download_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", download_btn)
        
        print("10 seconds wait kar rahe hain taaki 'Start' button load ho jaye...")
        time.sleep(10)
        
        print("'Start' button par click kar rahe hain...")
        start_clicked = False
        
        for i in range(15):
            try:
                start_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Start')]")
                for btn in start_buttons:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", btn)
                        start_clicked = True
                        print("Start button par successfully click ho gaya!")
                        break
                if start_clicked:
                    break
            except:
                time.sleep(2)
                
        if start_clicked:
            print("Video download ho rahi hai, 30 seconds wait karte hain...")
            time.sleep(30)
            
            # Check karna ki file download hui ya nahi
            files = os.listdir(download_dir)
            print(f"Downloads folder ki files: {files}")
            print(f"\nKaam ho gaya! File releases mein upload hone ke liye ready hai.")
        else:
            print("Error: 'Start' button nahi mila.")

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
    download_video_fully(link)
