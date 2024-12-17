# Парсер вопросов с сайта FIPI
## Описание
Этот проект представляет собой веб-приложение на Django для парсинга и обработки 
вопросов с сайта FIPI. Вопросы парсятся в формате JSON и содержат различные данные, 
включая текст вопроса, изображения, подсказки, ответ и т.д.

Каждый вопрос представлен в формате JSON следующего вида:
```json lines
{
    "id": "4F5745",
    "guid": "00011EA767B997BD431096F9DE1CA7F1",
    "hint": "Впишите правильный ответ.",
    "codifier": [
        "7.3 Многоугольники",
        "7.5 Измерение геометрических величин"
    ],
    "question": "Один из углов прямоугольной трапеции равен 64°. Найдите больший угол этой трапеции. Ответ дайте в градусах.",
    "problem": "<table align=\"right\" border=\"1\" cellpadding=\"0\" cellspacing=\"0\" class=\"MsoTableGrid\">...</table>",
    "img": [
        "4F5745/0.png"
    ],
    "img_urls": [
        "https://oge.fipi.ru/.../xs3qstsrc0088136AD101954045CAED9DA7A77650_1_1485782157.png"
    ],
    "number_in_group": "",
    "answer_type": "Краткий ответ",
    "answer": ""
}
```

# Установка
1. Клонируйте репозиторий проекта:
```bash
git clone https://github.com/skies21/questions-parser.git
```
2. Перейдите в папку проекта:
```bash
cd questions-parser
```
3. Создайте и активируйте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/macOS
venv\Scripts\activate  # для Windows
```
4. Установите зависимости из файла requirements.txt:
```bash
pip install -r requirements.txt
```
5. Запустите сервер разработки:
```bash
python manage.py runserver
```