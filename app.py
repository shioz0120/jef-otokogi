# --- 関数: ジェフニュース取得 (スクレイピング) ---
@st.cache_data(ttl=3600) # 1時間キャッシュ
def get_jef_news():
    url = "https://jefunited.co.jp/news/list"
    # 【追加】ブラウザのふりをするための「変装セット」
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    try:
        # headersを指定してアクセス
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # エラーならここで例外を出す
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        news_items = []
        
        # ニュースのリンクを探す（汎用的な検索）
        # hrefに '/news/detail/' が含まれるリンクを全て集める
        all_links = soup.find_all('a', href=True)
        target_links = [a for a in all_links if '/news/detail/' in a['href']]

        # 重複を除去しつつ、上から5つ取得
        seen = set()
        unique_links = []
        for a in target_links:
            link = a['href']
            if link not in seen:
                seen.add(link)
                unique_links.append(a)
                if len(unique_links) >= 5:
                    break
        
        for a in unique_links:
            link = a.get('href')
            if link.startswith('/'):
                link = f"https://jefunited.co.jp{link}"
            
            # テキスト抽出 (余計な空白を除去)
            # 内部に日付タグなどがある場合も考慮してテキストを繋げる
            text = " ".join(a.get_text().split())
            
            # もしテキストが空ならスキップ
            if text:
                news_items.append({"text": text, "link": link})
            
        return news_items
    except Exception as e:
        # デバッグ用: エラー内容をログに残す（StreamlitのManage appで見れる）
        print(f"Scraping Error: {e}")
        return None
