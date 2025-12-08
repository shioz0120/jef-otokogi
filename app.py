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

# --- 関数: データ取得 (最強版) ---
def load_data_from_sheet(sheet_name):
    ws = get_worksheet(sheet_name)
    # get_all_records ではなく get_all_values を使用 (生データを取得)
    all_values = ws.get_all_values()
    
    if not all_values:
        return pd.DataFrame() # 空っぽの場合
    
    # 1行目をヘッダーとして強制的に設定
    headers = all_values[0]
    data = all_values[1:]
    
    df = pd.DataFrame(data, columns=headers)
    return df

def load_data():
    # 改良された読み込み関数を使用
    df_trans = load_data_from_sheet("transactions")
    df_sched = load_data_from_sheet("schedule")
    df_rates = load_data_from_sheet("rates")
    df_mem = load_data_from_sheet("members")
    
    # --- 型変換とデータ整理 ---
    
    # transactions: 数値変換
    if not df_trans.empty:
        # 列名の空白除去
        df_trans.columns = df_trans.columns.str.strip()
        
        # amount, number を数値化
        if 'amount' in df_trans.columns:
            df_trans['amount'] = pd.to_numeric(df_trans['amount'], errors='coerce').fillna(0)
        if 'number' in df_trans.columns:
            df_trans['number'] = pd.to_numeric(df_trans['number'], errors='coerce').fillna(0)
            
    # rates: 数値変換
    if not df_rates.empty:
        df_rates['min_rank'] = pd.to_numeric(df_rates['min_rank'], errors='coerce')
        df_rates['max_rank'] = pd.to_numeric(df_rates['max_rank'], errors='coerce')
        df_rates['amount'] = pd.to_numeric(df_rates['amount'], errors='coerce')
        
    # members: display_order数値化
    if not df_mem.empty:
        df_mem['display_order'] = pd.to_numeric(df_mem['display_order'], errors='coerce')

    return df_trans, df_sched, df_rates, df_mem

# --- 関数: 男気金額計算 ---
def calculate_amount(number, df_rates):
    if number == 0: return 0
    for _, row in df_rates.iterrows():
        # データフレームから値を取り出すとfloatになることがあるのでintへ
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

# データロード
try:
    df_trans, df_sched, df_rates, df_mem = load_data()
except Exception as e:
    st.error(f"データ読み込みエラー: {e}")
    st.stop()

# --- シーズン選択ロジック ---
current_year = str(datetime.now().year)
season_list = []
if not df_sched.empty and 'season' in df_sched.columns:
    season_list = sorted(df_sched['season'].astype(str).unique().tolist(), reverse=True)

season_options = ["全期間"] + season_list
default_index = 1 if len(season_options) > 1 else 0
selected_season = st.sidebar.selectbox("シーズン表示切替", season_options, index=default_index)

# フィルタリング
current_sched = pd.DataFrame()
current_trans = pd.DataFrame()

if selected_season == "全期間":
    current_trans = df_trans
    if not df_sched.empty:
        latest_season = season_list[0] if season_list else current_year
        current_sched = df_sched[df_sched['season'].astype(str) == str(latest_season)]
else:
    if not df_sched.empty:
        current_sched = df_sched[df_sched['season'].astype(str) == str(selected_season)]
    if not df_trans.empty:
        current_trans = df_trans[df_trans['season'].astype(str) == str(selected_season)]

# --- タブ構成 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 ランキング", "📝 入力", "📜 履歴", "📅 日程追加"])

# === Tab 1: ランキング ===
with tab1:
    st.header(f"{selected_season} 男気ランキング")
    
    if not current_trans.empty:
        # 必要な列があるかチェック
        if 'timestamp' in current_trans.columns and 'amount' in current_trans.columns:
            # 最新状態を取得（重複排除）
            df_latest = current_trans.sort_values('timestamp').drop_duplicates(subset=['match_id', 'name'], keep='last')
            
            # 集計
            ranking = df_latest.groupby('name')['amount'].sum().reset_index()
            ranking = ranking.sort_values('amount', ascending=False)
            
            # 合計金額
            total = ranking['amount'].sum()
            st.metric("男気合計", f"¥{total:,}")

            col1, col2 = st.columns([2, 1])
            with col1:
                fig = px.pie(ranking, values='amount', names='name', title='男気シェア', hole=0.4)
                fig.update_traces(textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("詳細データ")
                st.dataframe(ranking.style.format({"amount": "¥{:,.0f}"}), hide_index=True, use_container_width=True)
        else:
             st.error(f"列不足エラー: 現在の列 {current_trans.columns.tolist()}")
    else:
        st.info("データがまだありません")

# === Tab 2: 入力 (Adminのみ) ===
with tab2:
    if st.session_state['role'] != 'admin':
        st.warning("ゲストは閲覧のみです")
    else:
        home_games = pd.DataFrame()
        if not current_sched.empty:
            home_games = current_sched[current_sched['type'] == 'Home']
        
        if home_games.empty:
            st.info(f"シーズン {selected_season} のホームゲーム予定が見つかりません。")
            st.info("「📅 日程追加」タブから日程を登録してください。")
        else:
            match_dict = {f"{row['section']} (vs {row['opponent']})": row['section'] for _, row in home_games.iterrows()}
            selected_label = st.selectbox("試合を選択", list(match_dict.keys()))
            selected_match_id = match_dict[selected_label]
            
            st.subheader("一括入力")
            with st.form("input_form"):
                active_mem = df_mem[df_mem['is_active'] == "TRUE"].sort_values('display_order')
                inputs = {}
                cols = st.columns(2)
                for idx, row in active_mem.iterrows():
                    with cols[idx % 2]:
                        inputs[row['name']] = st.number_input(f"{row['name']}", min_value=0, step=1, key=f"in_{row['name']}")
                
                submitted = st.form_submit_button("登録・更新")
                
                if submitted:
                    ws_trans = get_worksheet("transactions")
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    date_str = datetime.now().strftime('%Y/%m/%d')
                    target_season = selected_season if selected_season != "全期間" else str(datetime.now().year)

                    new_rows = []
                    cnt = 0
                    for name, num in inputs.items():
                        if num > 0:
                            amt = calculate_amount(num, df_rates)
                            new_rows.append([
                                date_str,
                                str(target_season),
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
        if 'timestamp' in current_trans.columns and 'date' in current_trans.columns:
            display_df = current_trans[['date', 'match_id', 'name', 'number', 'amount', 'season']].sort_values(['date', 'timestamp'], ascending=[False, False])
            st.dataframe(display_df, use_container_width=True)
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
            col1, col2 = st.columns(2)
            with col1:
                in_season = st.text_input("シーズン (例: 2025)", value=str(datetime.now().year))
                in_section = st.text_input("節 (例: 第5節)")
                in_date = st.text_input("日付 (例: 4/1)")
            with col2:
                in_opponent = st.text_input("対戦相手")
                in_type = st.selectbox("開催", ["Home", "Away"])
                in_stadium = st.text_input("スタジアム", value="フクアリ")

            submit_sched = st.form_submit_button("日程を追加する")

            if submit_sched:
                if in_section and in_date and in_opponent:
                    ws_sched = get_worksheet("schedule")
                    ws_sched.append_row([in_season, in_section, in_date, in_opponent, in_type, in_stadium])
                    st.success(f"{in_section} vs {in_opponent} を追加しました！")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("入力していない項目があります")
