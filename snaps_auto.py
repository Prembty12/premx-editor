import time
import sys
import os
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def snapscooper_click_flow(youtube_url):
    print("Undetected browser shuru ho raha hai...")
    
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    # Undetected ChromeDriver use kar rahe hain taaki Cloudflare detect na kare
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = uc.Chrome(options=options, use_subprocess=True)
    
    def take_screenshot(name):
        path = os.path.join(download_dir, f"screenshot_{name}.png")
        driver.save_screenshot(path)
        print(f"Screenshot saved: {path}")

    try:
        print("Website khol rahe hain: https://snapscooper.com/")
        driver.get("https://snapscooper.com/")
        time.sleep(5)
        take_screenshot("1_home")
        
        wait = WebDriverWait(driver, 20)
        
        print("Input box mein link daal rahe hain...")
        search_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.search-input.svelte-7ccykd")))
        
        driver.execute_script("""
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
        """, search_box, youtube_url)
        
        time.sleep(2)
        take_screenshot("2_link_pasted_check")
        
        print("Primary arrow/submit button par click kar rahe hain...")
        arrow_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".submit-btn, button.submit-btn")))
        driver.execute_script("arguments[0].scrollIntoView(true);", arrow_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", arrow_btn)
        
        print("Arrow button click ho gaya! Formats load hone ka wait kar rahe hain...")
        time.sleep(5)
        take_screenshot("3_arrow_clicked")
        
        print("Red 'Download' (4K) button par click kar rahe hain...")
        download_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".submit-btn-group .submit-btn, button.submit-btn")))
        driver.execute_script("arguments[0].scrollIntoView(true);", download_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", download_btn)
        
        print("Download button par click ho gaya! Screenshot le rahe hain...")
        take_screenshot("4_download_clicked")
        
        print("15 seconds wait kar rahe hain final process ke liye...")
        time.sleep(15)
        take_screenshot("5_final_wait_done")
        
        print("Poora process successfully complete ho gaya!")
        
    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        traceback.print_exc()
        take_screenshot("error_state")
    finally:
        driver.quit()

if __name__ == "__main__":
    link = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/..."
    snapscooper_click_flow(link)
