from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def find_elements(driver, by, item, wait_time:int = 10):
    return WebDriverWait(driver, wait_time).until(
        EC.visibility_of_all_elements_located((by, item))
    )


def find_element(driver, by, item, wait_time: int = 10):
    WebDriverWait(driver, wait_time).until(
        EC.visibility_of_element_located((by, item))
    )


def find_element_clickable(driver, by, item, wait_time: int = 10):
    WebDriverWait(driver, wait_time).until(
        EC.element_to_be_clickable((by, item))
    )


def wait_invisibility(driver, by, item, wait_time: int = 20):
    """Waits for an element (like a loading circle)
    to become invisible on the page.

    Args:
        driver (WebDriver): A Selenium web driver instance.
        timeout (int, optional): The maximum time to wait for the element
        to become invisible. Defaults to 20.

    Raises:
        TimeoutError: If the element does not become invisible
        within the specified timeout.
    """
    WebDriverWait(driver, wait_time).until(
        EC.invisibility_of_element_located((by, item))
    )
