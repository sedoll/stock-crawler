import os
import requests
from bs4 import BeautifulSoup
import json
from fpdf import FPDF
from datetime import datetime, timedelta
from urllib.parse import urljoin

# Discord 웹훅 URL을 여기에 입력하세요. (필수)
# Discord 채널 설정에서 웹훅을 생성하고 URL을 복사하여 붙여넣으세요.
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE"

def send_discord_notification(message, file_paths=None):
    """Discord 채널로 알림 메시지를 보냅니다."""
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL_HERE":
        print("Discord 웹훅 URL이 설정되지 않았습니다. 알림을 보낼 수 없습니다.")
        return
    
    payload = {
        "content": message
    }
    
    files = {}
    if file_paths:
        for i, path in enumerate(file_paths):
            try:
                files[f"file{i}"] = open(path, "rb")
            except FileNotFoundError:
                print(f"파일을 찾을 수 없습니다: {path}")
                continue

    try:
        if files:
            response = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
        else:
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        
        response.raise_for_status() # HTTP 오류가 발생하면 예외를 발생시킵니다.
        print("Discord 알림이 성공적으로 전송되었습니다.")
    except requests.exceptions.RequestException as e:
        print(f"Discord 알림 전송 실패: {e}")
    finally:
        # 열린 파일들을 모두 닫습니다.
        for f in files.values():
            f.close()

# WebCrawler 클래스는 웹 페이지 크롤링, 데이터 추출 및 파일 저장을 담당합니다.
class WebCrawler:
    # 클래스 초기화. URL과 출력 디렉토리를 설정합니다.
    def __init__(self, url, output_dir):
        self.url = url
        self.output_dir = output_dir
        # 웹사이트에 차단되지 않도록 사용자 에이전트를 설정합니다.
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # 출력 디렉토리가 없으면 생성합니다.
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    # 지정된 URL의 HTML 콘텐츠를 가져옵니다.
    def fetch_content(self):
        try:
            response = self.session.get(self.url)
            response.raise_for_status() # HTTP 오류가 발생하면 예외를 발생시킵니다.
            return response.text
        except requests.exceptions.RequestException as e:
            error_message = f"Error fetching content from {self.url}: {e}"
            print(error_message)
            # fetch_content 오류는 즉시 보고
            send_discord_notification(f"[크롤링 실패] {self.url} 에서 콘텐츠를 가져오지 못했습니다: {e}")
            return None

    # JSON 파일용으로, main 태그의 모든 텍스트를 추출합니다.
    def extract_text_content(self, html):
        if not html:
            return None
        soup = BeautifulSoup(html, 'html.parser')
        main_tag = soup.find('main')
        if main_tag:
            return main_tag.get_text(separator='\n', strip=True)
        return None

    # PDF 파일용으로, main 태그에서 이미지, 테이블, 텍스트 등 구조화된 콘텐츠를 추출합니다.
    def extract_structured_content(self, html):
        if not html:
            return None
        soup = BeautifulSoup(html, 'html.parser')
        main_tag = soup.find('main')
        if not main_tag:
            return None

        content = []
        processed_elements = set() # 중복 처리를 방지하기 위해 이미 처리된 요소를 추적합니다.

        # main 태그의 모든 하위 요소를 순회하며 콘텐츠를 추출합니다.
        for element in main_tag.find_all(True, recursive=True):
            if element in processed_elements:
                continue

            # 이미지 태그 처리
            if element.name == 'img':
                src = element.get('src')
                if src:
                    # 상대 경로를 절대 경로로 변환합니다.
                    content.append({'type': 'image', 'src': urljoin(self.url, src)})
                processed_elements.add(element)

            # 테이블 태그 처리
            elif element.name == 'table':
                table_data = []
                for row in element.find_all('tr'):
                    cols = [col.get_text(strip=True) for col in row.find_all(['th', 'td'])]
                    table_data.append(cols)
                content.append({'type': 'table', 'data': table_data})
                # 테이블과 그 하위 요소들을 처리된 것으로 표시하여 중복을 방지합니다.
                for desc in element.find_all(True, recursive=True):
                    processed_elements.add(desc)

            # 텍스트 관련 태그 처리
            elif element.name in ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol'] and element.get_text(strip=True):
                text = element.get_text(strip=True)
                if text:
                    content.append({'type': 'text', 'text': text})
                # 텍스트 블록과 그 하위 요소들을 처리된 것으로 표시합니다.
                for desc in element.find_all(True, recursive=True):
                    processed_elements.add(desc)

        return content

    # 추출된 데이터를 JSON 파일로 저장합니다.
    def save_as_json(self, data):
        if not data:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(self.output_dir, f"data_{timestamp}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({'content': data}, f, ensure_ascii=False, indent=4)
        print(f"Saved data to {file_path}")
        return file_path

    # 추출된 데이터를 PDF 파일로 저장합니다.
    def save_as_pdf(self, data):
        if not data:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(self.output_dir, f"data_{timestamp}.pdf")
        font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Pretendard-Medium.ttf')
        
        pdf = FPDF()
        pdf.add_page()
        
        # 한글 폰트를 설정합니다.
        try:
            pdf.add_font('Pretendard-Medium', '', font_path, uni=True)
            pdf.set_font('Pretendard-Medium', '', 12)
        except Exception as e:
            error_message = f"Could not set font: {e}. Using default font. Korean characters may not display correctly."
            print(error_message)
            send_discord_notification(f"[PDF 오류] {self.url} 의 PDF 폰트 설정 실패: {e}")
            pdf.set_font("Arial", size = 12)

        page_width = pdf.w - 2 * pdf.l_margin

        # 구조화된 데이터 순서대로 PDF에 내용을 추가합니다.
        for i, item in enumerate(data):
            # 이미지 처리
            if item['type'] == 'image':
                try:
                    print(f"Downloading image: {item['src']}")
                    response = requests.get(item['src'], stream=True)
                    response.raise_for_status()
                    # 각 이미지에 대해 고유한 임시 파일 이름을 사용합니다.
                    img_path = os.path.join(self.output_dir, f'temp_image_{i}.png')
                    with open(img_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                    pdf.image(img_path, w=page_width)
                    os.remove(img_path) # 임시 이미지 파일을 삭제합니다.
                except Exception as e:
                    error_message = f"Could not process image {item['src']}: {e}"
                    print(error_message)
                    # send_discord_notification(f"[PDF 오류] {self.url} 이미지 처리 실패 ({item['src']}): {e}") # 알림 제거
                    pdf.cell(page_width, 10, f"Image SRC: {item['src']}")
                    pdf.ln(10)
            # 테이블 처리
            elif item['type'] == 'table':
                if not item['data']: continue
                
                # 열 너비를 계산합니다.
                num_cols = len(item['data'][0])
                col_width = page_width / num_cols
                line_height = pdf.font_size * 2.5

                # 테이블 셀을 그리고 내용을 채웁니다.
                for row in item['data']:
                    for datum in row:
                        pdf.cell(col_width, line_height, datum, border=1)
                    pdf.ln(line_height)
                pdf.ln(line_height)

            # 텍스트 처리
            elif item['type'] == 'text':
                for line in item['text'].split('\n'):
                    if not line:
                        pdf.ln(10)
                        continue
                    pdf.multi_cell(page_width, 10, line)
                    pdf.ln(5)

        pdf.output(file_path)
        print(f"Saved data to {file_path}")
        return file_path

    # 크롤러의 메인 실행 함수입니다.
    def run(self):
        try:
            send_discord_notification(f"[크롤링 시작] {self.url} 크롤링을 시작합니다.")
            html = self.fetch_content()
            if not html:
                # fetch_content에서 이미 알림을 보냈으므로 여기서는 추가 알림 없음
                return

            # JSON 파일용 텍스트 콘텐츠를 추출하고 저장합니다.
            text_content = self.extract_text_content(html)
            json_file_path = self.save_as_json(text_content)

            # PDF 파일용 구조화된 콘텐츠를 추출하고 저장합니다.
            structured_content = self.extract_structured_content(html)
            pdf_file_path = self.save_as_pdf(structured_content)

            # 성공 알림과 함께 파일 전송
            file_paths_to_send = []
            if json_file_path: file_paths_to_send.append(json_file_path)
            if pdf_file_path: file_paths_to_send.append(pdf_file_path)

            send_discord_notification(f"[크롤링 성공] {self.url} 크롤링 및 파일 생성이 완료되었습니다.", file_paths=file_paths_to_send)
        except Exception as e:
            error_message = f"[크롤링 실패] {self.url} 크롤링 중 예상치 못한 오류 발생: {e}"
            print(error_message)
            send_discord_notification(error_message)

# 이 스크립트가 직접 실행될 때만 아래 코드를 실행합니다.
if __name__ == "__main__":
    # 오늘 날짜를 기준으로 URL을 동적으로 생성합니다.
    now = datetime.now()
    if now.hour >= 22: # 오후 10시 (22시) 이후이면 오늘 날짜 사용
        target_date = now
    else: # 오후 10시 이전이면 어제 날짜 사용
        target_date = now - timedelta(days=1)

    formatted_date = target_date.strftime("%Y-%m-%d")

    # 크롤링할 URL 목록입니다.
    URLS = [
        f"https://futuresnow.gitbook.io/newstoday/{formatted_date}/news/today/bloomberg",
        f"https://futuresnow.gitbook.io/newstoday/{formatted_date}/news/today/etc",
        f"https://futuresnow.gitbook.io/newstoday/{formatted_date}/news/today/undefined"
    ]
    # 각 URL에 해당하는 디렉토리 이름입니다.
    DIR_NAMES = ["주요뉴스", "실적발표", "경제지표"]
    # 기본 출력 디렉토리입니다.
    BASE_OUTPUT_DIR = "output"

    # 오늘 날짜로 된 디렉토리 경로를 생성합니다.
    today_dir = os.path.join(BASE_OUTPUT_DIR, formatted_date)

    # 각 URL에 대해 크롤러를 실행합니다.
    for i, url in enumerate(URLS):
        print(f"\nProcessing URL {i+1}/{len(URLS)}: {url}")
        url_dir_name = DIR_NAMES[i]
        url_output_dir = os.path.join(today_dir, url_dir_name)
        
        crawler = WebCrawler(url=url, output_dir=url_output_dir)
        crawler.run()
