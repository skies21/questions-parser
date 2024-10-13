import os

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
import requests
from bs4 import BeautifulSoup
import re
import json

import urllib3
from django.utils.encoding import smart_str

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def index(request):
    return render(request, 'index.html')


progress_data = {}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    'Connection': 'keep-alive',
}

projects = {
    "math_ege_profil": "AC437B34557F88EA4115D2F374B0A07B",
    "math_ege_base": "E040A72A1A3DABA14C90C97E0B6EE7DC",
    "math_oge": "DE0E276E497AB3784C3FC4CC20248DC0",
    "eng_oge": "8BBD5C99F37898B6402964AB11955663",
    "eng_ege": "4B53A6CB75B0B5E1427E596EB4931A2A"
}

q_count_re = re.compile(r"window\.parent\.setQCount\((\d+)\)")

BASE_URLS = {
    'ege': 'https://ege.fipi.ru/bank/questions.php?proj={}&page={}&pagesize={}',
    'oge': 'https://oge.fipi.ru/bank/questions.php?proj={}&page={}&pagesize={}',
}


def page_gen(base_url: str, proj_id: str, start_page: int = 0, max_page_size: int = 100):
    while True:
        curr_url = base_url.format(proj_id, start_page, max_page_size)
        yield requests.get(curr_url, headers=headers, verify=False)
        start_page += 1


def get_base_url(proj_id):
    if 'ege' in proj_id:
        return BASE_URLS['ege']
    return BASE_URLS['oge']


def clean_m_tags(soup):
    for tag in soup.find_all(True):
        if tag.name.startswith('m:'):
            tag.name = tag.name[2:]
    return soup


def process_table(p, problem_html, table_found):
    """Обработка таблицы MsoNormalTable или MsoTableGrid."""
    if table_found:
        return problem_html, table_found

    table = p.find_parent('table', class_='MsoNormalTable')
    if not table:
        table = p.find_parent('table', class_='MsoTableGrid')

    if table:
        for tag in table.find_all(True):
            tag.attrs = {key: value for key, value in tag.attrs.items() if key not in ['class', 'style']}
        problem_html += str(table)
        table_found = True
    return problem_html, table_found


def process_image(p, question_id, number_in_group, img_number, img_paths, img_urls, exam_type):
    """Обработка изображений с учетом расширений"""
    img_tag = p.find('img')
    if img_tag and img_tag.get('src'):
        # Извлекаем расширение из src
        img_src = img_tag['src']
        img_extension = os.path.splitext(img_src)[1]  # Получаем расширение файла (например, '.gif', '.png')

        # Формируем путь для сохранения изображения с правильным расширением
        img_file_path = f"{question_id}/{img_number}{img_extension}" if question_id else f"{number_in_group}/{img_number}{img_extension}"
        img_paths.append(img_file_path)

        # Формируем полный URL для загрузки изображения
        img_url = f"https://{exam_type}.fipi.ru/{img_src}"
        img_urls.append(img_url)

        # Обновляем атрибут 'src' тега img, заменяя его на путь сохранения
        img_tag['src'] = img_file_path

        # Увеличиваем счетчик изображений
        img_number += 1

    return img_number


def move_tables_to_end(problem_html):
    # Парсим HTML
    soup = BeautifulSoup(problem_html, 'html.parser')

    # Найдем distractors и answer таблицы
    distractors_table = soup.find('table', class_='distractors-table')
    answer_table = soup.find('table', class_='answer-table')

    tables_to_move = []

    # Если есть distractors таблица, вырезаем ее и очищаем
    if distractors_table:
        distractors_table.extract()
        distractors_table_html = str(distractors_table)
        cleaned_distractors_table_html = re.sub(r'\bm:', '', distractors_table_html)
        tables_to_move.append(cleaned_distractors_table_html)

    # Если есть answer таблица, вырезаем ее и очищаем
    if answer_table:
        answer_table.extract()
        answer_table_html = str(answer_table)
        cleaned_answer_table_html = re.sub(r'\bm:', '', answer_table_html)
        tables_to_move.append(cleaned_answer_table_html)

    # Преобразуем оставшийся контент в строку
    remaining_content = str(soup)

    # Добавляем очищенные таблицы в конец контента
    updated_problem_html = remaining_content + ''.join(tables_to_move)

    return updated_problem_html


def remove_non_radio_duplicate_images(problem_html):
    # Парсим HTML-код
    soup = BeautifulSoup(problem_html, 'html.parser')

    # Найдем таблицу с радиокнопками
    radio_table = soup.find('table', class_='distractors-table')

    # Собираем все изображения из таблицы с радиокнопками
    table_images = {img['src'] for img in radio_table.find_all('img')} if radio_table else set()

    # Найдем все изображения вне таблицы с радиокнопками
    for img in soup.find_all('img'):
        # Если изображение вне таблицы и его src совпадает с изображением из таблицы, удаляем его
        if img['src'] in table_images and not img.find_parent('table'):
            img.decompose()

    return str(soup)


def clean_problem_text(problem_html):
    cleaned_problem = problem_html.replace('xml:namespace prefix = m ns = "http://www.w3.org/1998/Math/MathML" /', '')
    return cleaned_problem


def remove_duplicate_paragraphs(problem_html):
    # Парсим HTML-код
    soup = BeautifulSoup(problem_html, 'html.parser')

    # Найдем таблицу с радиокнопками
    radio_table = soup.find('table', class_='distractors-table')

    if radio_table:
        # Собираем тексты всех <p> элементов внутри таблицы
        table_p_texts = [p_element.get_text(strip=True) for p_element in radio_table.find_all('p')]

        # Удаляем <p> теги вне таблицы, если текст совпадает с любым из текстов в таблице
        for p_element in soup.find_all('p'):
            if p_element.get_text(strip=True) in table_p_texts and p_element.find_parent('table') is None:
                p_element.decompose()

    return str(soup)


def remove_special_characters_tags(problem_html):
    # Парсим HTML-код
    soup = BeautifulSoup(problem_html, 'html.parser')

    # Удаляем теги, если внутри есть символ замены
    for tag in soup.find_all(['math', 'mstyle', 'semantics', 'mi']):
        # Получаем текст тега и проверяем наличие символа замены
        text_content = tag.get_text()
        if '�' in text_content:
            tag.unwrap()  # Удаляем тег, если найден символ замены

    return str(soup)


def clean_problem_char(problem_text):
    # Удаляем специальные символы и теги
    problem_text = remove_special_characters_tags(problem_text)

    # Определяем словарь замены для символа � в контексте
    replace_dict = {
        'бо�ьш': 'больш',  # "бо�ьш" → "больш"
        'сто�т': 'стоит',  # "сто�т" → "стоит"
        'у�е': 'уже',  # "у�е" → "уже"
        'they�ll': "they'll"  # "they�ll" → "they'll"
    }

    # Парсим входной текст как HTML
    soup = BeautifulSoup(problem_text, 'html.parser')

    # Ищем все текстовые элементы
    for tag in soup.find_all(text=True):
        tag_text = tag.strip()
        tag_text = re.sub(r'\s*�\s*', '�', tag_text)

        # Проходим по всем ключам из словаря замены
        for key, replacement in replace_dict.items():
            # Заменяем только точные вхождения ключа
            if key in tag_text:
                updated_text = tag_text.replace(key, replacement)
                tag.replace_with(updated_text)

    # Возвращаем изменённый HTML как строку
    return str(soup)


def remove_duplicate_tables(problem_html):
    # Парсим HTML-код
    soup = BeautifulSoup(problem_html, 'html.parser')

    # Находим все таблицы
    tables = soup.find_all('table')

    seen_tables = set()
    for table in tables:
        # Извлекаем полный текст таблицы
        table_text = table.get_text(separator=' ').strip()

        # Если таблица с таким содержимым уже встречалась, удаляем её
        if table_text in seen_tables:
            table.decompose()
        else:
            # Добавляем уникальный текст таблицы в множество для проверки
            seen_tables.add(table_text)

    # Возвращаем обновленный HTML
    return str(soup)


def process_table_content(table_soup):
    # Обработать формулы
    maths = table_soup.find_all('m:math')  # Найти все формулы
    for math in maths:
        for child in math.findChildren():
            if 'm:' in child.name:
                child.name = child.name.replace('m:', '')  # Убираем префикс m:
        math.name = math.name.replace('m:', '')  # Убираем префикс m: у самой формулы

    # Удалить ненужные атрибуты и теги
    for child in table_soup.findChildren():
        # Убрать заливку
        if 'bgcolor' in child.attrs:
            del child['bgcolor']

        # Убрать подсказку
        if 'id' in child.attrs and child['id'] == 'hint':
            child.decompose()  # Удаляем тег с подсказкой

    return table_soup


def find_and_extract_tables(question):
    tables_to_move = []
    bs = question.find_all('b')  # Ищем все <b> теги в вопросе

    # Удаляем <b> теги, пока первый не имеет <u>
    while bs and not bs[0].u:
        del bs[0]

    header = bs[0].u if bs else None  # Получаем заголовок, если он существует

    if header:
        parent = header.parent
        headers = []
        # Ищем таблицу, у которой есть 2 заголовка
        while parent and (parent.name != 'table' or len(headers) < 2):
            parent = parent.parent
            headers = parent.find_all('u') if parent else []

        # Если нашли нужную таблицу
        if parent and parent.name == 'table' and len(headers) >= 2:
            correspond_table = parent
            correspond_table.extract()
            tables_to_move.append(correspond_table)

    # Ищем и вырезаем таблицу с классом answer-table, если она существует
    answer_table = question.find('table', class_='answer-table')
    if answer_table:
        answer_table.extract()
        tables_to_move.append(answer_table)

    # Обрабатываем каждую таблицу
    processed_tables = []
    for table in tables_to_move:
        processed_table = process_table_content(table)
        processed_tables.append(processed_table)

    return processed_tables


def remove_math_prefix(html):
    # Парсим HTML-код
    soup = BeautifulSoup(html, 'html.parser')

    # Находим все теги с префиксом 'm:'
    maths = soup.find_all(lambda tag: tag.name.startswith('m:'))

    for math in maths:
        # Убираем префикс 'm:' из имени тега
        math.name = math.name.replace('m:', '')

        # Также проходим по дочерним элементам, чтобы удалить префиксы
        for child in math.findChildren():
            if child.name.startswith('m:'):
                child.name = child.name.replace('m:', '')

    # Возвращаем HTML как строку
    return str(soup)


def append_tables_if_not_exist(problem_html, tables_to_move):
    # Гарантируем, что таблицы будут добавлены в конец
    for table in tables_to_move:
        table_str = str(table)  # Преобразуем таблицу в строку
        if table_str not in problem_html:  # Проверяем, нет ли уже этой таблицы
            problem_html = problem_html.strip() + table_str  # Добавляем в конец
    return problem_html


def parse(request):
    bank_type = request.GET.get('bank')
    exam_type = 'ege' if 'ege' in bank_type else 'oge'
    proj_id = projects.get(bank_type)
    if not proj_id:
        return JsonResponse({'error': 'proj id not found'}, status=404)

    base_url = get_base_url(bank_type)
    resp_gen = page_gen(base_url, proj_id)
    response = next(resp_gen)

    if response.status_code != 200:
        return JsonResponse({'error': 'Failed to fetch data from the source'}, status=500)

    match = q_count_re.search(response.text)
    q_count = int(match.group(1))
    parsed_data = []

    while q_count > 0:
        soup = BeautifulSoup(response.text, 'html.parser')
        for span in soup.find_all('span'):
            span.unwrap()

        questions = soup.find_all('div', class_='qblock')

        for question in questions:
            question_id = question.get('id')[1:] if question.get('id') else ""
            img_number = 0
            problem_html = ""
            img_paths = []
            img_urls = []

            # Ищем и вырезаем таблицы соответствий и ответов
            tables_to_move = find_and_extract_tables(question)

            hint = question.find_next('div', class_='hint').get_text(strip=True)

            answer_table = question.find('table', class_='answer-table')
            if answer_table:
                for tag in answer_table.find_all(True):
                    tag.attrs = {key: value for key, value in tag.attrs.items() if
                                 key not in ['class', 'style']}
                problem_html += str(answer_table)

            distractors_table = question.find('table', class_='distractors-table')
            if distractors_table:
                for tag in distractors_table.find_all(True):
                    tag.attrs = {key: value for key, value in tag.attrs.items() if
                                 key not in ['class', 'style']}
                problem_html += str(distractors_table)

            next_td = question.find_next_sibling('div')
            codifiers = []
            answer_type = ""
            number_in_group = ""
            if next_td:
                next_td_row = next_td.find('td', class_='param-row')
                if next_td_row:
                    codifier_elements = next_td_row.find_all()
                    for codifier_element in codifier_elements:
                        codifier_text = codifier_element.get_text(strip=True)
                        if codifier_text:
                            codifiers.append(codifier_text)
                    answer_type = next_td_row.find_next('td', class_='param-name').find_next().get_text(strip=True)

                # Ищем number_in_group в текущем элементе
                number_in_group_tag = next_td.find('div', class_='number-in-group')

                # Если не найдено, проверяем в следующем элементе, только если question_id не найден
                if not number_in_group_tag and not question_id:
                    number_in_group_tag = next_td.find_next('div', class_='number-in-group')

                # Получаем текст из найденного элемента
                number_in_group = number_in_group_tag.get_text(strip=True) if number_in_group_tag else ""
                if not answer_type and not question_id and number_in_group:
                    q_count += 1
                    number_in_group = re.sub(r'^\S+', '0', number_in_group, count=1)

            p_elements = question.find_all('p')
            span_elements = question.find_all('span')
            elements = p_elements if p_elements else span_elements
            table_found = False

            in_list = False

            for p in elements:
                # Проверяем, является ли элемент параграфом задания или частью таблицы ответов
                if elements is p_elements and ('MsoNormal' in p.get('class', []) or 'Basis' in p.get('class', [])):
                    if not p.find_parent('table', class_='MsoNormalTable') and not p.find_parent('table',
                                                                                                 class_='MsoTableGrid'):
                        # Проверка на наличие списка
                        text = p.get_text()
                        if text.startswith('·'):
                            # Если список еще не начат, добавляем тег <ul>
                            if not in_list:
                                problem_html += '<ul>'
                                in_list = True

                            # Добавляем пункт списка
                            problem_html += f'<li>{text.replace("·", "").strip()}</li>'

                        else:
                            # Если список был начат, закрываем его перед добавлением обычного текста
                            if in_list:
                                problem_html += '</ul>'
                                in_list = False

                            # Просто добавляем содержимое параграфа
                            problem_html += ''.join([str(child) for child in p.children])

                    else:
                        # Если нашли таблицу, закрываем список перед таблицей
                        if in_list:
                            problem_html += '</ul>'
                            in_list = False

                        problem_html, table_found = process_table(p, problem_html, table_found)

                    img_number = process_image(p, question_id, number_in_group, img_number, img_paths, img_urls,
                                               exam_type)

                else:
                    if not p.find_parent('table', class_='MsoNormalTable') and not p.find_parent('table',
                                                                                                 class_='MsoTableGrid'):
                        text = p.get_text()
                        if text.startswith('·'):
                            if not in_list:
                                problem_html += '<ul>'
                                in_list = True

                            problem_html += f'<li>{text.replace("·", "").strip()}</li>'

                        else:
                            if in_list:
                                problem_html += '</ul>'
                                in_list = False

                            problem_html += ''.join([str(child) for child in p.children])

                    else:
                        if in_list:
                            problem_html += '</ul>'
                            in_list = False

                        problem_html, table_found = process_table(p, problem_html, table_found)

                    img_number = process_image(p, question_id, number_in_group, img_number, img_paths, img_urls,
                                               exam_type)

            if in_list:
                problem_html += '</ul>'

            # Обработка скриптов с картинками
            if tables_to_move:
                correspond_table_soup = BeautifulSoup(problem_html, 'html.parser')
                script_tags = correspond_table_soup.find_all('script')
            else:
                script_tags = question.find_all('script')

            # Инициализируем переменную для хранения files_abs_location
            files_abs_location = None

            # Поиск скрипта с files_abs_location
            for script in question.find_all('script'):
                if script.string and re.search(r"files_abs_location", script.string):
                    # Ищем значение переменной files_abs_location
                    files_abs_match = re.search(r"files_abs_location=['\"](.*?)['\"];", script.string)
                    if files_abs_match:
                        files_abs_location = files_abs_match.group(1)  # Сохраняем путь из скрипта

            # Основная обработка скриптов ShowPicture и ShowPictureQ
            for script in script_tags:
                if script.string and re.search(r"ShowPictureQ|ShowPicture", script.string):
                    img_match = re.findall(r"ShowPicture(Q)?\(['\"](.*?)['\"]", script.string)

                    for img_src_tuple in img_match:
                        img_src = img_src_tuple[1]

                        # Если найден files_abs_location, добавляем его к пути
                        if files_abs_location:
                            img_src = files_abs_location + img_src

                        img_url = f"https://{exam_type}.fipi.ru/{img_src}"
                        img_urls.append(img_url)

                        # Получаем расширение файла из оригинальной ссылки (gif, png и т.д.)
                        img_extension = os.path.splitext(img_src)[1]  # Вернет '.gif', '.png' и т.д.

                        # Формируем путь для сохранения изображения с правильным расширением
                        img_file_path = f"{question_id}/{img_number}{img_extension}" if question_id else f"{number_in_group}/{img_number}{img_extension}"
                        img_paths.append(img_file_path)

                        img_tag_html = f'<sub><img src="{img_file_path}"/></sub>'

                        # Заменяем скрипт на HTML-тег с изображением
                        problem_html = re.sub(re.escape(str(script)), img_tag_html, problem_html,
                                              flags=re.IGNORECASE)
                        img_number += 1

                    # Удаляем тег скрипта после обработки
                    script.extract()

            problem_html = append_tables_if_not_exist(problem_html, tables_to_move)
            problem_html = remove_duplicate_tables(problem_html)

            question_text = [p.get_text(strip=True) for p in p_elements] if p_elements else [""]
            question_text_combined = "; ".join(question_text)

            problem_html = re.sub(r'<script.*?>.*?</script>', '', problem_html, flags=re.DOTALL)
            problem_html = move_tables_to_end(problem_html)
            problem_html = remove_non_radio_duplicate_images(problem_html)
            problem_html = remove_duplicate_paragraphs(problem_html)
            problem_html = clean_problem_text(problem_html)
            problem_html = remove_math_prefix(problem_html)
            problem_html = clean_problem_char(problem_html)
            question_text_combined = clean_problem_char(question_text_combined)

            new_data = {
                "id": question_id,
                "hint": hint,
                "codifier": codifiers,
                "question": question_text_combined,
                "problem": problem_html,
                "img": img_paths,
                "img_urls": img_urls,
                "number_in_group": number_in_group,
                "answer_type": answer_type,
                "answer": "",
            }

            for item in parsed_data:
                if item == new_data:
                    # Если нашли идентичный объект, выходим из цикла
                    break
            else:
                parsed_data.append(new_data)

        q_count -= len(questions)
        if q_count <= 0:
            break

        response = next(resp_gen)
        if response.status_code != 200:
            return JsonResponse({'error': 'Failed to fetch data from the source'}, status=500)

    response = HttpResponse(
        json.dumps(parsed_data, ensure_ascii=False, indent=4),
        content_type='application/json'
    )
    response['Content-Disposition'] = f'attachment; filename="{smart_str(bank_type)}_parsed_data.json"'

    return response
