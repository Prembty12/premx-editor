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
        
        print("Download button par click kar rahe hain...")
        try:
            download_btn = download_box.find_element(By.TAG_NAME, "button")
            download_btn.click()
        except:
            download_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Download')]")
            download_btn.click()
            
        print("Video info aur thumbnail load hone ka wait ho raha hai (10 seconds)...")
        time.sleep(10) # 10 seconds ka poora wait taaki card achhe se load ho jaye
        
        print("Start button ko dhoond kar click kar rahe hain...")
        start_btn = None
        
        # Alag-alag tareeqon se button dhoondenge taaki TimeoutException na aaye
        try:
            # Pehle download-box ke andar ka akhiri button try karo (jo Start button hota hai)
            start_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@id='download-box']//button[last()]")))
        except:
            try:
                # Agar woh na mile toh kisi bhi button ko dhoondo jisme purple ya gradient class ho ya text ho
                start_btn = driver.find_element(By.XPATH, "//button[.//span or contains(@class, 'btn')]")
            except Exception as ex:
                print(f"Buttons nahi mile, page ka source check kar rahe hain...")
                print(driver.page_source[:500]) # Debug ke liye thoda source print hoga
                raise ex
                
        driver.execute_script("arguments[0].scrollIntoView(true);", start_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", start_btn)
        
        print("File prepare ho rahi hai, wait kiya ja raha hai...")
        final_link = None
        
        for i in range(25):
            time.sleep(2)
            try:
                download_file_btn = driver.find_element(By.XPATH, "//a[contains(text(), 'Download File') or contains(text(), 'Download')]")
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
            print("Error: Link nikalne mein samay lag gaya.")

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
