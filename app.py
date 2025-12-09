import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import plotly.express as px
import requests
from bs4 import BeautifulSoup

# --- ページ設定 ---
st.set_page_config(page_title="男気チャンス", page_icon="⚽", layout="wide")

# --- 定数・接続設定 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# --- 関数: スプレッドシート接続 ---
@st.cache_resource
def get_worksheet(sheet_name):
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(st.secrets["spreadsheet_key"])
    return sheet.worksheet(sheet_name)

# --- 関数: データ取得 ---
def load_data_from_sheet(sheet_name):
    ws = get_worksheet(sheet_name)
    all_values = ws.get_all_values()
    if not all_values:
        return pd.DataFrame()
    headers = all_values[0]
    data = all_values[1:]
    return pd.DataFrame(data, columns=headers)

def load_data():
    df_trans = load_data_from_sheet("transactions")
    df_sched = load_data_from_sheet("schedule")
    df_rates = load_data_from_sheet("rates")
    df_mem = load_data_from_sheet("members")
    
    # 型変換
    if not df_trans.empty:
        df_trans.columns = df_trans.columns.str.strip()
        if 'amount' in df_trans.columns:
            df_trans['amount'] = pd.to_numeric(df_trans['amount'], errors='coerce').fillna(0)
        if 'number' in df_trans.columns:
            df_trans['number'] = pd.to_numeric(df_trans['number'], errors='coerce').fillna(0)
            
    if not df_rates.empty:
        df_rates.columns = df_rates.columns.str.strip()
        cols = ['min_rank', 'max_rank', 'amount']
        for c in cols:
            if c in df_rates.columns:
                df_rates[c] = pd.to_numeric(df_rates[c], errors='coerce').fillna(0).astype(int)
        
    if not df_mem.empty:
        df_mem.columns = df_mem.columns.str.strip()
        df_mem['display_order'] = pd.to_numeric(df_mem['display_order'], errors='coerce').fillna(999)

    return df_trans, df_sched, df_rates, df_mem

# --- 関数: 男気金額計算 ---
def calculate_amount(number, df_rates):
    if number == 0: return 0
    for _, row in df_rates.iterrows():
        try:
            min_r = int(row['min_rank'])
            max_r = int(row['max_rank'])
            amt = int(row['amount'])
            if min_r <= number <= max_r:
                return amt
        except:
            continue
    return 1000

# --- 関数: RSSニュース取得 (改良版) ---
@st.cache_data(ttl=3600) # 1時間ごとに更新
def get_jef_rss_news():
    url = "http://rss.phew.homeip.net/v10/10010.xml"
    # ブラウザのふりをする
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # ステータスコードエラーチェック
        
        # 文字化け対策
        response.encoding = response.apparent_encoding

        # 'xml' パーサーではなく 'html.parser' を使用 (追加インストール不要で安定)
        soup = BeautifulSoup(response.content, "html.parser")
        
        items = soup.find_all("item")
        news_list = []
        
        # 最新5件を取得
        for item in items[:5]:
            title = item.title.text
            link = item.link.text
            
            # 日付情報の取得 (dc:date タグを探す)
            date_str = ""
            dc_date = item.find("dc:date")
            if dc_date:
                # 例: 2025-12-09T... -> 12/09
                try:
                    dt = datetime.strptime(dc_date.text[:10], "%Y-%m-%d")
                    date_str = dt.strftime("%m/%d")
                except:
                    pass
            
            news_list.append({"date": date_str, "title": title, "link": link})
            
        return news_list
    except Exception as e:
        # ログにエラーを出力 (管理画面で確認可能)
        print(f"RSS Error: {e}")
        return []

# --- 関数: ログイン処理 ---
def login():
    if 'role' in st.session_state:
        return True
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.title("⚽ 男気チャンス")
        st.markdown("##### 合言葉を入力してください")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if password == st.secrets["passwords"]["admin"]:
                st.session_state['role'] = 'admin'
                st.rerun()
            elif password == st.secrets["passwords"]["guest"]:
                st.session_state['role'] = 'guest'
                st.rerun()
            else:
                st.error("パスワードが違います")
    
    # --- ニュース表示エリア (RSS) ---
    st.divider()
    st.subheader("📰 公式最新ニュース") # 【変更】タイトル修正
    
    news_items = get_jef_rss_news()
    
    if news_items:
        for news in news_items:
            if news['date']:
                st.markdown(f"**{news['date']}** [{news['title']}]({news['link']})")
            else:
                st.markdown(f"- [{news['title']}]({news['link']})")
        
        st.caption("Source: JEF UNITED RSS")
    else:
        st.caption("ニュースの読み込みに失敗しました。")

    return False

# ==========================================
# メイン処理
# ==========================================
if not login():
    st.stop()

st.sidebar.markdown(f"User: **{st.session_state['role'].upper()}**")

try:
    df_trans, df_sched, df_rates, df_mem = load_data()
except Exception as e:
    st.error(f"データ読み込みエラー: {e}")
    st.stop()

# --- シーズン選択 ---
current_year = str(datetime.now().year)
season_list = []
if not df_sched.empty and 'season' in df_sched.columns:
    season_list = sorted(df_sched['season'].astype(str).unique().tolist(), reverse=True)

season_options = ["全期間"] + season_list
default_idx = 1 if len(season_options) > 1 else 0
selected_season = st.sidebar.selectbox("シーズン表示切替", season_options, index=default_idx)

# フィルタリング
current_sched = pd.DataFrame()
current_trans = pd.DataFrame()

if selected_season == "全期間":
    current_trans = df_trans
    if not df_sched.empty:
        latest = season_list[0] if season_list else current_year
        current_sched = df_sched[df_sched['season'].astype(str) == str(latest)]
else:
    if not df_sched.empty:
        current_sched = df_sched[df_sched['season'].astype(str) == str(selected_season)]
    if not df_trans.empty:
        current_trans = df_trans[df_trans['season'].astype(str) == str(selected_season)]

# --- タブ構成 ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 ランキング", "📝 入力", "📜 履歴", "📅 日程追加", "⚙️ 設定"])

# === Tab 1: ランキング ===
with tab1:
    st.header(f"{selected_season} 男気ランキング")
    if not current_trans.empty:
        if 'timestamp' in current_trans.columns and 'amount' in current_trans.columns:
            df_latest = current_trans.sort_values('timestamp').drop_duplicates(subset=['match_id', 'name'], keep='last')
            ranking = df_latest.groupby('name')['amount'].sum().reset_index().sort_values('amount', ascending=False)
            total = ranking['amount'].sum()
            st.metric("男気トータル", f"¥{total:,}")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = px.pie(ranking, values='amount', names='name', title='男気シェア', hole=0.4)
                fig.update_traces(textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.subheader("詳細データ")
                st.dataframe(ranking.style.format({"amount": "¥{:,.0f}"}), hide_index=True, use_container_width=True)
        else:
             st.error(f"列不足エラー: {current_trans.columns.tolist()}")
    else:
        st.info("データがまだありません")

# === Tab 2: 入力 (Adminのみ) ===
with tab2:
    if st.session_state['role'] != 'admin':
        st.warning("ゲストは閲覧のみです")
    else:
        with st.expander("💰 現在のレート表を確認する"):
            st.dataframe(df_rates, hide_index=True)
            st.caption("※ 抽選忘れは **9999** を入力してください")

        home_games = pd.DataFrame()
        if not current_sched.empty:
            home_games = current_sched[current_sched['type'] == 'Home']
        
        if home_games.empty:
            st.info(f"シーズン {selected_season} のホームゲーム予定が見つかりません。")
            st.info("「📅 日程追加」タブから日程を登録してください。")
        else:
            match_options = []
            match_ids = []
            today = datetime.now().date()
            default_index = 0
            future_found = False
            
            for idx, row in home_games.iterrows():
                label = f"{row['date']} {row['section']} (vs {row['opponent']})"
                match_options.append(label)
                match_ids.append(row['section'])
                if not future_found:
                    try:
                        match_date = datetime.strptime(str(row['date']).strip(), '%Y/%m/%d').date()
                        if match_date >= today:
                            default_index = len(match_options) - 1
                            future_found = True
                    except:
                        pass
            
            if not future_found and match_options:
                default_index = len(match_options) - 1

            sel_label = st.selectbox("試合を選択", match_options, index=default_index)
            sel_index = match_options.index(sel_label)
            sel_match_id = match_ids[sel_index]
            
            st.subheader("一括入力")
            st.info("💡 抽選忘れの場合は **9999** を入力してください")

            with st.form("input_form"):
                active_mem = df_mem[df_mem['is_active'] == "TRUE"].sort_values('display_order')
                inputs = {}
                cols = st.columns(2)
                for idx, row in active_mem.iterrows():
                    with cols[idx % 2]:
                        inputs[row['name']] = st.number_input(f"{row['name']}", min_value=0, step=1, key=f"in_{row['name']}")
                
                if st.form_submit_button("登録・更新"):
                    ws_trans = get_worksheet("transactions")
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    date_str = datetime.now().strftime('%Y/%m/%d')
                    tgt_season = selected_season if selected_season != "全期間" else str(datetime.now().year)
                    new_rows = []
                    cnt = 0
                    for name, num in inputs.items():
                        if num > 0:
                            amt = calculate_amount(num, df_rates)
                            new_rows.append([date_str, str(tgt_season), sel_match_id, name, num, amt, now_str])
                            cnt += 1
                    
                    if new_rows:
                        ws_trans.append_rows(new_rows)
                        st.success(f"{cnt}件 保存しました！")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("番号を入力してください")

# === Tab 3: 履歴 ===
with tab3:
    if not current_trans.empty:
        if 'timestamp' in current_trans.columns and 'date' in current_trans.columns:
            sorted_df = current_trans.sort_values(['date', 'timestamp'], ascending=[False, False])
            
            display_df = sorted_df.copy()
            if not df_sched.empty and 'section' in df_sched.columns and 'opponent' in df_sched.columns:
                sorted_df_merge = sorted_df.copy()
                sorted_df_merge['season'] = sorted_df_merge['season'].astype(str)
                sorted_df_merge['match_id'] = sorted_df_merge['match_id'].astype(str)
                df_sched_merge = df_sched[['season', 'section', 'opponent']].copy()
                df_sched_merge['season'] = df_sched_merge['season'].astype(str)
                df_sched_merge['section'] = df_sched_merge['section'].astype(str)
                
                merged_df = pd.merge(
                    sorted_df_merge,
                    df_sched_merge,
                    left_on=['season', 'match_id'],
                    right_on=['season', 'section'],
                    how='left'
                )
                merged_df['opponent'] = merged_df['opponent'].fillna('-')
                display_cols = ['season', 'date', 'match_id', 'opponent', 'name', 'number', 'amount']
                display_cols = [c for c in display_cols if c in merged_df.columns]
                st.dataframe(merged_df[display_cols], use_container_width=True)
            else:
                st.dataframe(sorted_df[['season', 'date', 'match_id', 'name', 'number', 'amount']], use_container_width=True)
        else:
            st.dataframe(current_trans, use_container_width=True)
    else:
        st.write("履歴なし")

# === Tab 4: 日程追加 (Adminのみ) ===
with tab4:
    st.header("📅 新しい試合日程の追加")
    if st.session_state['role'] != 'admin':
        st.warning("管理者のみ追加可能です")
    else:
        with st.form("add_schedule_form"):
            c1, c2 = st.columns(2)
            with c1:
                in_season = st.text_input("シーズン (例: 2025)", value=str(datetime.now().year))
                in_section = st.text_input("節 (例: 第5節)")
                in_date = st.text_input("日付 (例: 2025/4/1)")
            with c2:
                in_opp = st.text_input("対戦相手")
                in_type = st.selectbox("開催", ["Home", "Away"])
                in_stad = st.text_input("スタジアム", value="フクアリ")

            if st.form_submit_button("日程を追加する"):
                if in_section and in_date and in_opp:
                    get_worksheet("schedule").append_row([in_season, in_section, in_date, in_opp, in_type, in_stad])
                    st.success(f"{in_section} vs {in_
