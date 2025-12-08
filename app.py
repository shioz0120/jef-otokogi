import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

# --- ページ設定 ---
st.set_page_config(page_title="JEF Otokogi", page_icon="⚽", layout="wide")

# --- 定数・接続設定 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# --- 関数: スプレッドシート接続 ---
@st.cache_resource
def get_worksheet(sheet_name):
    # Secretsから認証情報を取得
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    # スプレッドシートを開く
    sheet = client.open_by_key(st.secrets["spreadsheet_key"])
    return sheet.worksheet(sheet_name)

# --- 関数: データ取得 ---
def load_data():
    # キャッシュを無効化して常に最新を取得したい場合は ttl=0 を指定するか、st.cache_dataを外す
    # ここでは簡易的に直接取得
    ws_trans = get_worksheet("transactions")
    ws_sched = get_worksheet("schedule")
    ws_rates = get_worksheet("rates")
    ws_mem = get_worksheet("members")
    
    df_trans = pd.DataFrame(ws_trans.get_all_records())
    df_sched = pd.DataFrame(ws_sched.get_all_records())
    df_rates = pd.DataFrame(ws_rates.get_all_records())
    df_mem = pd.DataFrame(ws_mem.get_all_records())
    
    # 型変換（数値計算のため）
    if not df_trans.empty:
        df_trans['amount'] = pd.to_numeric(df_trans['amount'], errors='coerce').fillna(0)
    
    return df_trans, df_sched, df_rates, df_mem

# --- 関数: 男気金額計算 ---
def calculate_amount(number, df_rates):
    if number == 0: return 0
    # ratesテーブルに基づいて計算
    for _, row in df_rates.iterrows():
        if row['min_rank'] <= number <= row['max_rank']:
            return row['amount']
    return 1000 # 範囲外デフォルト

# --- 関数: ログイン処理 ---
def login():
    if 'role' in st.session_state:
        return True

    st.title("⚽ JEF千葉 男気チャレンジ")
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
    return False

# ==========================================
# メイン処理
# ==========================================
if not login():
    st.stop()

# ユーザー権限表示
st.sidebar.markdown(f"User: **{st.session_state['role'].upper()}**")

# データロード
try:
    df_trans, df_sched, df_rates, df_mem = load_data()
except Exception as e:
    st.error(f"データ読み込みエラー: {e}")
    st.stop()

# --- シーズン選択 ---
# データが空の場合は現在年をデフォルトに
current_year = str(datetime.now().year)
season_list = [current_year]
if not df_sched.empty and 'season' in df_sched.columns:
    # 文字列としてユニーク値を取得してソート
    season_list = sorted(df_sched['season'].astype(str).unique().tolist(), reverse=True)

selected_season = st.sidebar.selectbox("シーズン選択", season_list)

# フィルタリング
# データフレームのseason列も文字列型に合わせて比較
current_sched = pd.DataFrame()
current_trans = pd.DataFrame()

if not df_sched.empty:
    current_sched = df_sched[df_sched['season'].astype(str) == str(selected_season)]
if not df_trans.empty:
    current_trans = df_trans[df_trans['season'].astype(str) == str(selected_season)]

# --- タブ構成 ---
tab1, tab2, tab3 = st.tabs(["📊 ランキング", "📝 入力", "📜 履歴"])

# === Tab 1: ランキング ===
with tab1:
    st.header(f"{selected_season} シーズン 結果")
    
    if not current_trans.empty:
        # 最新状態を取得（重複排除）
        # match_idとnameが同じなら、timestampが新しいものを採用
        df_latest = current_trans.sort_values('timestamp').drop_duplicates(subset=['match_id', 'name'], keep='last')
        
        # 集計
        ranking = df_latest.groupby('name')['amount'].sum().reset_index()
        ranking = ranking.sort_values('amount', ascending=False)
        
        # グラフ
        st.bar_chart(ranking, x='name', y='amount', color='#FFFF00') # JEF Yellow
        
        # 合計
        total = ranking['amount'].sum()
        st.metric("忘年会プール金", f"¥{total:,}")
    else:
        st.info("データがまだありません")

# === Tab 2: 入力 (Adminのみ) ===
with tab2:
    if st.session_state['role'] != 'admin':
        st.warning("ゲストは閲覧のみです")
    else:
        # Home試合のみ抽出
        home_games = pd.DataFrame()
        if not current_sched.empty:
            home_games = current_sched[current_sched['type'] == 'Home']
        
        if home_games.empty:
            st.info("対象のホームゲームが見つかりません（scheduleシートを確認してください）")
        else:
            # プルダウン作成
            match_dict = {f"{row['section']} (vs {row['opponent']})": row['section'] for _, row in home_games.iterrows()}
            selected_label = st.selectbox("試合を選択", list(match_dict.keys()))
            selected_match_id = match_dict[selected_label]
            
            st.subheader("一括入力")
            with st.form("input_form"):
                # アクティブメンバー取得
                active_mem = df_mem[df_mem['is_active'] == "TRUE"].sort_values('display_order')
                
                inputs = {}
                cols = st.columns(2)
                for idx, row in active_mem.iterrows():
                    with cols[idx % 2]:
                        # keyをユニークにする
                        inputs[row['name']] = st.number_input(f"{row['name']}", min_value=0, step=1, key=f"in_{row['name']}")
                
                submitted = st.form_submit_button("登録・更新")
                
                if submitted:
                    ws_trans = get_worksheet("transactions")
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    date_str = datetime.now().strftime('%Y/%m/%d')
                    
                    new_rows = []
                    cnt = 0
                    for name, num in inputs.items():
                        if num > 0:
                            amt = calculate_amount(num, df_rates)
                            # 追加データ: date, season, match_id, name, number, amount, timestamp
                            new_rows.append([
                                date_str,
                                str(selected_season),
                                selected_match_id,
                                name,
                                num,
                                amt,
                                now_str
                            ])
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
        st.dataframe(current_trans.sort_values('timestamp', ascending=False), use_container_width=True)
    else:
        st.write("履歴なし")
