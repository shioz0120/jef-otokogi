import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import plotly.express as px

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

# --- 関数: ログイン処理 ---
def login():
    if 'role' in st.session_state:
        return True
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

#
