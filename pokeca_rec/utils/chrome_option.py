from selenium.webdriver.chrome.options import Options

chrome_opt = Options()
chrome_opt.add_argument("--incognito")
chrome_opt.add_argument("--headless")
chrome_opt.add_argument("disable-extensions")
chrome_opt.add_argument("disable-popup-blocking")
chrome_opt.add_argument("disable-infobars")
