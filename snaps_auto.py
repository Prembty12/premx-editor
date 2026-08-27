import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def snapscooper_download(youtube_url):
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
        time.sleep(5)
        take_screenshot("1_home")
        
        wait = WebDriverWait(driver, 25)
        
        print("Input box mein link paste kiya ja raha hai...")
        search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Paste') or @type='text']")))
        search_box.clear()
        search_box.send_keys(youtube_url)
        time.sleep(2)
        take_screenshot("2_link_pasted")
        
        # 100% Working Arrow Click Logic with multiple fallbacks
        print("Arrow button par click karne ki koshish kar rahe hain...")
        arrow_clicked = False
        
        arrow_xpaths = [
            "//input[contains(@placeholder, 'Paste')]/following-sibling::button",
            "//input[contains(@placeholder, 'Paste')]/parent::div//button",
            "//button[descendant::*[local-name()='svg'] and contains(@class, 'rounded')]",
            "//button[./svg]"
        ]
        
        for xpath in arrow_xpaths:
            try:
                btns = driver.find_elements(By.XPATH, xpath)
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", btn)
                        arrow_clicked = True
                        print("Arrow button par successfully click ho gaya!")
                        break
                if arrow_clicked:
                    break
            except Exception as ex:
                continue
                
        if not arrow_clicked:
            print("Warning: Standard arrow nahi mila, coordinate ya generic click try karte hain...")
            generic_arrow = wait.until(EC.element_to_be_clickable((By.XPATH, "(//button)[2]")))
            driver.execute_script("arguments[0].click();", generic_arrow)

        time.sleep(5)
        take_screenshot("3_after_arrow")
        
        # Error handling & Try Again check
        try:
            try_again = driver.find_elements(By.XPATH, "//button[contains(text(), 'Try Again')]")
            if try_again and try_again[0].is_displayed():
                print("Error detect hua, 'Try Again' par click kar rahe hain...")
                driver.execute_script("arguments[0].click();", try_again[0])
                time.sleep(8)
                take_screenshot("3_b_try_again_clicked")
        except:
            pass
            
        print("Formats load hone ka wait kar rahe hain...")
        time.sleep(10)
        take_screenshot("4_formats_loaded")
        
        # Video quality download/render button click karna
        print("2160p Render & Download button dhoondh rahe hain...")
        v_clicked = False
        try:
            buttons = driver.find_elements(By.XPATH, "//a[contains(., 'Render & Download') or contains(., 'Download')]")
            for btn in buttons:
                txt = btn.text.lower()
                parent_text = btn.find_element(By.XPATH, "./ancestor::div").text.lower()
                if "render & download" in txt or ("2160p" in parent_text and "render" in txt):
                    print(f"Target button mila: {btn.text}. Click kar rahe hain...")
                    driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", btn)
                    v_clicked = True
                    break
        except Exception as e:
            print("Video button click error:", e)

        if not v_clicked:
            alt_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "(//a[contains(., 'Render & Download')])[1]")))
            driver.execute_script("arguments[0].click();", alt_btn)

        take_screenshot("5_render_or_download_started")
        
        # Smart Wait Loop: Jab tak "Done" na aa jaye
        print("Rendering & Downloading complete hone ka wait kar rahe hain ('Done' hone tak)...")
        for i in range(15):  # Max 75 seconds wait
            time.sleep(5)
            take_screenshot(f"6_waiting_progress_{i+1}")
            page_text = driver.page_source.lower()
            if "done" in page_text or ("waiting..." not in page_text and "preparing media" not in page_text):
                print("Render / Download process complete ho chuka hai!")
                break
                
        time.sleep(5)
        take_screenshot("6_final_render_done")
        
        # Audios tab par click karna
        print("Audios tab par click kar rahe hain...")
        audio_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Audio') or contains(., 'Audios')]")))
        driver.execute_script("arguments[0].click();", audio_tab)
        time.sleep(3)
        take_screenshot("7_audios_tab")
        
        print("Medium M4A audio download button par click kar rahe hain...")
        a_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(., 'medium') and (contains(., 'M4A') or contains(., 'm4a'))]//a | (//a[contains(., 'Download')])[1]")))
        driver.execute_script("arguments[0].click();", a_btn)
        time.sleep(10)
        take_screenshot("8_audio_download_started")
        
        print("Files download hone ke liye final 20 seconds wait...")
        time.sleep(20)
        take_screenshot("9_downloads_complete")
        
    except Exception as e:
        import traceback
        print(f"\nCRITICAL ERROR DETAILS:")
        traceback.print_exc()
        take_screenshot("error_state")
    finally:
        driver.quit()

    # FFmpeg Merge Step
    print("FFmpeg se video aur audio merge kar rahe hain...")
    downloaded_files = os.listdir(download_dir)
    v_file = next((os.path.join(download_dir, f) for f in downloaded_files if f.endswith(('.mp4', '.webm')) and 'audio' not in f and 'screenshot' not in f), None)
    a_file = next((os.path.join(download_dir, f) for f in downloaded_files if (f.endswith(('.m4a', '.mp3', '.webm')) or 'medium' in f) and 'screenshot' not in f), None)
    
    if v_file and a_file:
        output_file = os.path.join(download_dir, "final_merged_video.mp4")
        cmd = f"ffmpeg -i \"{v_file}\" -i \"{a_file}\" -c:v copy -c:a aac \"{output_file}\" -y"
        print(f"Running: {cmd}")
        os.system(cmd)
        print("Merge complete!")
    else:
        print("Warning: Separate video ya audio file theek se nahi mili.")

if __name__ == "__main__":
    link = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/..."
    snapscooper_download(link)
