import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def snapscooper_click_flow(youtube_url):
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
    
    def take_screenshot(name):
        path = os.path.join(download_dir, f"screenshot_{name}.png")
        driver.save_screenshot(path)
        print(f"Screenshot saved: {path}")

    try:
        print("Website khol rahe hain: https://snapscooper.com/")
        driver.get("https://snapscooper.com/")
        time.sleep(4)
        take_screenshot("1_home")
        
        wait = WebDriverWait(driver, 20)
        
        print("Input box mein exact Svelte class ke zariye link daal rahe hain...")
        search_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.search-input.svelte-7ccykd")))
        
        # JavaScript se value set karke Svelte events trigger karna
        driver.execute_script("""
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
        """, search_box, youtube_url)
        
        time.sleep(2)
        take_screenshot("2_link_pasted_check")
        
        print("Arrow button (`button.search-input-action`) par click kar rahe hain...")
        arrow_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.search-input-action.svelte-7ccykd")))
        driver.execute_script("arguments[0].scrollIntoView(true);", arrow_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", arrow_btn)
        
        print("Arrow button click ho gaya! Screenshot le rahe hain...")
        time.sleep(3)
        take_screenshot("3_arrow_clicked")
        
        print("10 seconds wait kar rahe hain formats load hone ke liye...")
        time.sleep(10)
        take_screenshot("4_formats_ready")
        
        print("Process complete! Sabhi screenshots save ho chuke hain.")
        
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
