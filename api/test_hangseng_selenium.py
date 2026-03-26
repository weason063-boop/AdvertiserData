from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

def test_selenium():
    print("Starting Selenium Debugging...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        url = "https://www.hangseng.com/zh-cn/personal/banking/rates/foreign-exchange-rates/"
        print(f"Navigating to {url}...")
        driver.get(url)
        
        # Wait for table to load
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
            print("Table found!")
        except:
            print("Timeout waiting for table.")
            
        time.sleep(5)
        
        # Scroll down to ensure lazy loading is handled (if any)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # Find all rows
        rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
        print(f"Found {len(rows)} rows.")
        
        for i, row in enumerate(rows):
            # Print the text of the row
            print(f"Row {i} Text: {row.text.replace(chr(10), ' | ')}")
            # Also try to print the inner HTML of the first cell to check structure
            try:
                cols = row.find_elements(By.TAG_NAME, "td")
                if cols:
                    print(f"  Cols: {len(cols)}")
                    print(f"  Col 0: {cols[0].text}")
            except:
                pass
            
        driver.quit()
        
    except Exception as e:
        print(f"Selenium Error: {e}")

if __name__ == "__main__":
    test_selenium()
