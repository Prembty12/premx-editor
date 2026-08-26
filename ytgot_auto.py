import time
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def get_ytgot_download_link(youtube_url):
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
        
        wait = WebDriverWait(driver, 20)
        
        print("Link paste kiya ja raha hai...")
        download_box = wait.until(EC.presence_of_element_located((By.ID, "download-box")))
        search_box = download_box.find_element(By.TAG_NAME, "input")
        search_box.clear()
        search_box.send_keys(youtube_url)
        
        print("Download button par click kar rahe hain...")
        try:
            download_btn = download_box.find_element(By.TAG_NAME, "button")
            download_btn.click()
        except:
            download_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Download')]")
            download_btn.click()
            
        print("Video info load hone ka wait ho raha hai (6 seconds)...")
        time.sleep(6)
        
        print("Start button ko dhoond kar click kar rahe hain...")
        start_btn = None
        
        # Alag-alag tareeqon se Start button dhoondna taaki fail na ho
        selectors = [
            "//button[contains(text(), 'Start')]",
            "//button[contains(@class, 'start')]",
            "//div[@id='download-box']//button[last()]",
            "//button[.//span[contains(text(), 'Start')]]"
        ]
        
        for sel in selectors:
            try:
                start_btn = driver.find_element(By.XPATH, sel)
                if start_btn:
                    print(f"Button mil gaya selector se: {sel}")
                    break
            except:
                pass
                
        if not start_btn:
            # Agar phir bhi na mile toh page ke saare buttons print kar do debugging ke liye
            all_btns = driver.find_elements(By.TAG_NAME, "button")
            print(f"Total buttons found on page: {len(all_btns)}")
            for b in all_btns:
                print(f"Button text: '{b.text}' | HTML: {b.get_attribute('outerHTML')[:100]}")
            raise Exception("Start button page par nahi mila!")
            
        driver.execute_script("arguments[0].scrollIntoView(true);", start_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", start_btn)
        
        print("File prepare ho rahi hai, wait kiya ja raha hai...")
        final_link = None
        
        for i in range(25):
            time.sleep(2)
            try:
                download_file_btn = driver.find_element(By.XPATH, "//a[contains(text(), 'Download File') or contains(@class, 'download')]")
                final_link = download_file_btn.get_attribute("href")
                if final_link and "http" in final_link:
                    break
            except:
                pass
            
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href")
                if href and any(ext in href for ext in ["googlevideo.com", "download", ".mp4", "stream"]):
                    final_link = href
                    break
            if final_link:
                break

        if final_link:
            print("\n==========================================")
            print("MIL GAYA DIRECT DOWNLOAD LINK:")
            print(final_link)
            print("==========================================")
        else:
            print("Link nikalne mein time lag gaya.")

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
    get_ytgot_download_link(link)
