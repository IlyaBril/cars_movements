
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Настройки
LOGIN = "mv3120"
PASSWORD = "Part17991799####"
URL = "https://qls.moskvich.ru/QLS/ru/" # URL вашего веб-клиента

# Запуск браузера
driver = webdriver.Edge() # или Firefox, Edge
driver.get(URL)

try:
    # 1. Ожидание появления формы входа
    wait = WebDriverWait(driver, 10)
    
    # 2. Поиск полей логина и пароля (селекторы могут отличаться!)
    login_field = wait.until(EC.presence_of_element_located((By.ID, "login")))
    password_field = driver.find_element(By.ID, "password")
    
    # 3. Ввод данных
    login_field.send_keys(LOGIN)
    password_field.send_keys(PASSWORD)
    
    # 4. Нажатие кнопки входа
    submit_button = driver.find_element(By.ID, "submit")
    submit_button.click()
    
    # 5. Ожидание загрузки главной страницы
    time.sleep(5) # Простая пауза, можно заменить на ожидание конкретного элемента
    
    print("✅ Авторизация успешна!")
    
    # 6. Дальше идем в нужный раздел и выгружаем данные
    # Например, переход в справочник "Контрагенты"
    # driver.find_element(By.LINK_TEXT, "Справочники").click()
    # time.sleep(2)
    # driver.find_element(By.LINK_TEXT, "Контрагенты").click()
    # time.sleep(3)
    
    # Получение данных из таблицы
    # rows = driver.find_elements(By.CSS_SELECTOR, ".table-row")
    # for row in rows:
    # print(row.text)
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    driver.save_screenshot("error.png") # Сохраняем скриншот для отладки

finally:
    # Закрываем браузер
    driver.quit()
