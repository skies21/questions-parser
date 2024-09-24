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


def parse(request):
    bank_type = request.GET.get('bank')
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
    q_count = 10
    parsed_data = []
    task_number = 1

    while q_count > 0:
        soup = BeautifulSoup(response.text, 'html.parser')
        questions = soup.find_all('div', class_='qblock')

        for question in questions:
            question_id = question.get('id')[1:]
            img_number = 0
            task_number += 1
            problem_html = ""
            img_paths = []
            img_urls = []

            p_elements = question.find_all('p', class_='MsoNormal')
            for p in p_elements:
                p_html = clean_m_tags(p)
                if p.get('class') == ['MsoNormal']:
                    p_html = ''.join([str(child) for child in p.children])

                problem_html += p_html

                img_tag = p.find('img')
                if img_tag and img_tag.get('src'):
                    img_file_path = f"task_{task_number:0>2}/{question_id}/{img_number}.gif"
                    img_paths.append(img_file_path)
                    img_url = f"https://ege.fipi.ru/{img_tag['src']}"
                    img_urls.append(img_url)
                    img_tag['src'] = img_file_path
                    problem_html += f'<img src="{img_file_path}" />'
                    img_number += 1

                script = p.find('script')
                if script and "ShowPictureQ" in script.string:
                    img_match = re.search(r"ShowPictureQ\(['\"](.*?)['\"]", script.string)
                    if img_match:
                        img_url = f"https://ege.fipi.ru/{img_match.group(1)}"
                        img_urls.append(img_url)
                        img_file_path = f"task_{task_number:0>2}/{question_id}/{img_number}.gif"
                        img_paths.append(img_file_path)
                        problem_html += f'<img src="{img_file_path}" />'
                        img_number += 1

            question_text = [p.get_text(strip=True) for p in p_elements] if p_elements else [""]
            question_text_combined = "; ".join(question_text)

            next_td = question.find_next('td', class_='param-row')
            codifier = next_td.get_text(separator='; ', strip=True) if next_td else ""

            parsed_data.append({
                "id": question_id,
                "codifier": codifier,
                "question": question_text_combined,
                "problem": problem_html,
                "img": img_paths,
                "img_urls": img_urls,
                "answer": "",
            })

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
