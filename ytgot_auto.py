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
        
        wait = WebDriverWait(driver, 25)
        
        print("Link paste kiya ja raha hai...")
        download_box = wait.until(EC.presence_of_element_located((By.ID, "download-box")))
        search_box = download_box.find_element(By.TAG_NAME, "input")
        search_box.clear()
        search_box.send_keys(youtube_url)
        
        print("Download/Search button par click kar rahe hain...")
        try:
            download_btn = download_box.find_element(By.TAG_NAME, "button")
            download_btn.click()
        except:
            download_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Download')]")
            download_btn.click()
            
        print("Link paste karne ke baad 5 second wait kar rahe hain...")
        time.sleep(5)  # Aapka bataya hua 5 second ka wait
        
        print("Ab Start button par click kar rahe hain...")
        start_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@id='download-box']//button[last()]")))
        driver.execute_script("arguments[0].scrollIntoView(true);", start_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", start_btn)
        
        print("File prepare ho rahi hai, 'Download File' button aane ka wait kar rahe hain...")
        
        final_link = None
        # 35 seconds tak wait karenge jab tak file ready hokar 'Download File' button na aa jaye
        for i in range(35):
            time.sleep(2)
            try:
                dl_button = driver.find_element(By.XPATH, "//a[contains(text(), 'Download File')] | //button[contains(text(), 'Download File')]")
                if dl_button:
                    print("Download File button mil gaya! Us par click kar rahe hain...")
                    driver.execute_script("arguments[0].scrollIntoView(true);", dl_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", dl_button)
                    time.sleep(3)
                    
                    if dl_button.tag_name == 'a':
                        final_link = dl_button.get_attribute("href")
                    break
            except:
                pass
                
        if not final_link:
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href")
                if href and any(ext in href for ext in ["googlevideo.com", "download", ".mp4", "stream"]):
                    final_link = href
                    break

        if final_link:
            print("\n==========================================")
            print("MIL GAYA DIRECT DOWNLOAD LINK:")
            print(final_link)
            print("==========================================")
        else:
            print("Link capture nahi ho paya.")

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
