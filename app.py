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
            disp_df = sorted_df[['season', 'date', 'match_id', 'name', 'number', 'amount']]
            st.dataframe(disp_df, use_container_width=True)
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
                    st.success(f"{in_section} vs {in_opp} を追加しました！")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("入力していない項目があります")

# === Tab 5: 設定 ===
with tab5:
    st.header("⚙️ アプリ設定")
    if st.session_state['role'] != 'admin':
        st.warning("管理者のみ変更可能です")
    else:
        st.subheader("💰 レート設定")
        edited_rates = st.data_editor(df_rates, num_rows="dynamic", use_container_width=True, key="editor_rates")
        st.markdown("※ 抽選忘れは **9999** を入力")

        if st.button("レート設定を保存する"):
            try:
                ws = get_worksheet("rates")
                ws.clear()
                ws.update([edited_rates.columns.values.tolist()] + edited_rates.astype(str).values.tolist())
                st.success("レート設定を更新しました！")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"保存エラー: {e}")

        st.divider()

        st.subheader("👥 メンバー管理")
        st.info("※ `is_active` を **TRUE** で表示、**FALSE** で非表示")
        edited_mem = st.data_editor(
            df_mem, num_rows="dynamic", use_container_width=True, key="editor_members",
            column_config={
                "is_active": st.column_config.SelectboxColumn("有効", options=["TRUE", "FALSE"], required=True),
                "display_order": st.column_config.NumberColumn("並び順", min_value=1, step=1)
            }
        )
        
        if st.button("メンバー設定を保存する"):
            try:
                ws = get_worksheet("members")
                ws.clear()
                ws.update([edited_mem.columns.values.tolist()] + edited_mem.astype(str).values.tolist())
                st.success("メンバー情報を更新しました！")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"保存エラー: {e}")
