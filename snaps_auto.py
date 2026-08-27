import time
import sys
import os
import subprocess
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
    
    try:
        print("Website khol rahe hain: https://snapscooper.com/")
        driver.get("https://snapscooper.com/")
        time.sleep(5)
        
        wait = WebDriverWait(driver, 25)
        
        print("Input box mein link paste kiya ja raha hai...")
        search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Paste') or @type='text']")))
        search_box.clear()
        search_box.send_keys(youtube_url)
        time.sleep(2)
        
        print("Arrow button par click kar rahe hain...")
        arrow_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'bg-') and descendant::*[local-name()='svg']] | //button[./svg]")))
        driver.execute_script("arguments[0].click();", arrow_btn)
        
        print("5 seconds wait kar rahe hain...")
        time.sleep(5)
        
        # Error handling & Try Again check
        try:
            try_again = driver.find_elements(By.XPATH, "//button[contains(text(), 'Try Again')]")
            if try_again and try_again[0].is_displayed():
                print("Error detect hua, 'Try Again' par click kar rahe hain...")
                driver.execute_script("arguments[0].click();", try_again[0])
                time.sleep(8)
        except:
            pass
            
        print("Formats load hone ka wait kar rahe hain (10s)...")
        time.sleep(10)
        
        # 1. 2160p (Silent video) download link click karna
        print("2160p video download button dhoondh rahe hain...")
        video_clicked = False
        try:
            # Screenshot ke hisaab se 2160p HDR - Silent wala button
            v_buttons = driver.find_elements(By.XPATH, "//div[contains(., '2160p') and contains(., 'Silent')]//ancestor::div//a[contains(@class, 'download')] | //div[contains(., '2160p')]//following::a[1] | //a[contains(text(), 'Download') and contains(@href, 'http')]")
            for btn in v_buttons:
                if "2160p" in btn.text or "Download" in btn.text:
                    video_url_target = btn.get_attribute("href")
                    print(f"Video Direct Link mila: {video_url_target}")
                    driver.execute_script("arguments[0].click();", btn)
                    video_clicked = True
                    break
        except Exception as e:
            print("Video click error:", e)
            
        if not video_clicked:
            # Fallback direct click via XPath matching 2160p block
            v_alt = wait.until(EC.element_to_be_clickable((By.XPATH, "(//a[contains(., 'Download')])[7]"))) # 2160p position based on screenshot
            driver.execute_script("arguments[0].click();", v_alt)
            
        time.sleep(5)
        
        # 2. Audios tab par click karna
        print("Audios tab par click kar rahe hain...")
        audio_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Audio') or contains(., 'Audios')]")))
        driver.execute_script("arguments[0].click();", audio_tab)
        time.sleep(3)
        
        print("Medium M4A audio download button dhoondh rahe hain...")
        a_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(., 'medium') and contains(., 'M4A')]//a | (//a[contains(., 'Download')])[1]")))
        driver.execute_script("arguments[0].click();", a_btn)
        
        print("Files download hone ka wait kar rahe hain (30s)...")
        time.sleep(30)
        
        files = os.listdir(download_dir)
        print(f"Downloads folder files: {files}")
        
    except Exception as e:
        import traceback
        print(f"\nCRITICAL ERROR DETAILS:")
        traceback.print_exc()
    finally:
        driver.quit()

    # FFmpeg Merge Step
    print("FFmpeg se video aur audio merge kar rahe hain...")
    downloaded_files = os.listdir(download_dir)
    v_file = next((os.path.join(download_dir, f) for f in downloaded_files if f.endswith(('.mp4', '.webm')) and 'audio' not in f), None)
    a_file = next((os.path.join(download_dir, f) for f in downloaded_files if f.endswith(('.m4a', '.mp3', '.webm')) and ('audio' in f or 'medium' in f or f.endswith('.m4a'))), None)
    
    if v_file and a_file:
        output_file = os.path.join(download_dir, "final_merged_video.mp4")
        cmd = f"ffmpeg -i \"{v_file}\" -i \"{a_file}\" -c:v copy -c:a aac \"{output_file}\" -y"
        print(command := f"Running: {cmd}")
        os.system(cmd)
        print("Merge complete! Output file ready.")
    else:
        print("Warning: Separate video or audio file nahi mili, merging skip ho rahi hai.")

if __name__ == "__main__":
    link = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/..."
    snapscooper_download(link)
