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
    """Обработка изображений"""
    img_tag = p.find('img')
    if img_tag and img_tag.get('src'):
        img_file_path = f"{question_id}/{img_number}.gif" if question_id else f"{number_in_group}/{img_number}.gif"
        img_paths.append(img_file_path)
        img_url = f"https://{exam_type}.fipi.ru/{img_tag['src']}"
        img_urls.append(img_url)
        img_tag['src'] = img_file_path
        img_number += 1
    return img_number


def process_content(p):
    """Обработка контента элемента"""
    p_html = str(clean_m_tags(p))
    if 'MsoNormal' in p.get('class', []) or 'Basis' in p.get('class', []):
        p_html = ''.join([str(child) for child in p.children])
    return p_html


def move_radio_table_to_end(problem_html):
    # Парсим HTML
    soup = BeautifulSoup(problem_html, 'html.parser')

    # Найдем таблицы с радиокнопками
    radio_table = soup.find('table', class_='distractors-table')

    if radio_table and radio_table.find('input', {'type': 'radio'}):
        # Вырезаем таблицу с вариантами ответов
        radio_table.extract()

        # Очищаем теги внутри таблицы от префиксов 'm:'
        radio_table_html = str(radio_table)
        cleaned_radio_table_html = re.sub(r'\bm:', '', radio_table_html)

        # Преобразуем оставшийся контент в строку
        remaining_content = str(soup)

        # Добавляем очищенную таблицу в конец контента
        updated_problem_html = remaining_content + cleaned_radio_table_html

        return updated_problem_html

    return problem_html  # Если нет радиокнопок, возвращаем исходный HTML


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


def remove_special_characters(problem_html):
    # Парсим HTML-код
    soup = BeautifulSoup(problem_html, 'html.parser')

    # Удаляем теги <mi> с символом �
    for mi_tag in soup.find_all('mi'):
        if mi_tag.text == '�':
            mi_tag.decompose()  # Удаляем тег <mi>

    # Удаляем теги <semantics> с <mi> внутри
    for semantics_tag in soup.find_all('semantics'):
        mi_inside = semantics_tag.find('mi')
        if mi_inside and mi_inside.text == '�':
            semantics_tag.decompose()  # Удаляем тег <semantics>

    return str(soup)


def clean_problem_char(problem_text):
    # Удаляем символы �
    cleaned_text = problem_text.replace('�', '')
    return cleaned_text


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
    task_number = 1

    while q_count > 0:
        soup = BeautifulSoup(response.text, 'html.parser')
        for span in soup.find_all('span'):
            span.unwrap()

        questions = soup.find_all('div', class_='qblock')

        for question in questions:
            question_id = question.get('id')[1:] if question.get('id') else ""
            img_number = 0
            task_number += 1
            problem_html = ""
            img_paths = []
            img_urls = []

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

            for p in elements:
                # Проверяем, является ли элемент параграфом задания или частью таблицы ответов
                if elements is p_elements and ('MsoNormal' in p.get('class', []) or 'Basis' in p.get('class', [])):
                    if not p.find_parent('table', class_='MsoNormalTable') and not p.find_parent('table',
                                                                                                 class_='MsoTableGrid'):
                        problem_html += process_content(p)
                    else:
                        problem_html, table_found = process_table(p, problem_html, table_found)

                    img_number = process_image(p, question_id, number_in_group, img_number, img_paths, img_urls,
                                               exam_type)
                else:
                    if not p.find_parent('table', class_='MsoNormalTable') and not p.find_parent('table',
                                                                                                 class_='MsoTableGrid'):
                        problem_html += process_content(p)
                    else:
                        problem_html, table_found = process_table(p, problem_html, table_found)

                    img_number = process_image(p, question_id, number_in_group, img_number, img_paths, img_urls,
                                               exam_type)

                # Обработка скриптов с картинками
                script_tags = p.find_all('script')
                for script in script_tags:
                    if script.string and re.search(r"ShowPictureQ|ShowPicture", script.string):
                        img_match = re.findall(r"ShowPicture(Q)?\(['\"](.*?)['\"]", script.string)
                        for img_src_tuple in img_match:
                            img_src = img_src_tuple[1]
                            img_url = f"https://{exam_type}.fipi.ru/{img_src}"
                            img_urls.append(img_url)
                            img_file_path = f"{question_id}/{img_number}.gif" if question_id else \
                                f"{number_in_group}/{img_number}.gif"
                            img_paths.append(img_file_path)
                            img_tag_html = f'<sub><img src="{img_file_path}"/></sub>'

                            # Заменяем скрипт на HTML-тег с изображением
                            problem_html = re.sub(re.escape(str(script)), img_tag_html, problem_html,
                                                  flags=re.IGNORECASE)
                            img_number += 1

                        # Удаляем тег скрипта после обработки
                        script.extract()

            question_text = [p.get_text(strip=True) for p in p_elements] if p_elements else [""]
            question_text_combined = "; ".join(question_text)

            problem_html = re.sub(r'<script.*?>.*?</script>', '', problem_html, flags=re.DOTALL)
            problem_html = move_radio_table_to_end(problem_html)
            problem_html = remove_non_radio_duplicate_images(problem_html)
            problem_html = remove_duplicate_paragraphs(problem_html)
            problem_html = clean_problem_text(problem_html)
            problem_html = remove_special_characters(problem_html)
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
