import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import google.generativeai as genai
import json # For parsing potential structured responses from Gemini, though not strictly used for current dummy.
import os
import pandas as pd

# --- データベース関連の関数 ---
DATABASE_NAME = "food_items.db"

def init_db():
    """データベースを初期化し、テーブルを作成します。"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS food_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            purchase_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            quantity REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def add_ingredient_to_db(name, purchase_date, expiry_date, quantity):
    """食材をデータベースに追加します。"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO food_items (name, purchase_date, expiry_date, quantity) VALUES (?, ?, ?, ?)",
            (name, purchase_date, expiry_date, quantity)
        )
        conn.commit()
        st.success("食材が追加されました。")
    except sqlite3.Error as e:
        st.error(f"食材の追加中にエラーが発生しました: {e}")
    finally:
        conn.close()

def get_all_ingredients():
    """データベースからすべての食材を取得し、期限が近い順にソートします。"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, purchase_date, expiry_date, quantity FROM food_items ORDER BY expiry_date ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_ingredient_from_db(ingredient_name_like):
    """指定された食材をデータベースから削除します（部分一致）。"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM food_items WHERE name LIKE ?", (f"%{ingredient_name_like}%",))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count
    except sqlite3.Error as e:
        st.error(f"食材の削除中にエラーが発生しました: {e}")
        return 0
    finally:
        conn.close()

api_key = os.environ.get("GOOGLE_API_KEY")
gemini_configured_successfully = False

if api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        gemini_configured_successfully = True
    except Exception as e:
        st.error(f"Gemini APIの設定中にエラーが発生しました: {e}")
else:
    st.error("APIキーが環境変数 GOOGLE_API_KEY に設定されていません。")
    st.info("ローカルで実行する場合: 環境変数に GOOGLE_API_KEY を設定してください。")
    st.info("Streamlit Cloudにデプロイする場合: アプリ設定のSecretsに GOOGLE_API_KEY = \"あなたのAPIキー\" を追加してください。")
    model = None # モデルが利用できないことを示す


# # --- データベースの初期化ボタン ---
def clear_database():
    """food_items テーブルのデータをすべて削除します。"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM food_items")
        conn.commit()
        st.success("データベースの食材データを初期化しました。")
    except sqlite3.Error as e:
        st.error(f"データベースの初期化中にエラーが発生しました: {e}")
    finally:
        conn.close()

# --- Streamlit UI ---
def run_app():
    st.set_page_config(layout="wide")
    st.title("献立生成AIアプリ")
    st.write("このアプリは、食材の管理と献立の提案を行います。")
    st.sidebar.header("設定")
    if st.button("データベースの食材データを初期化"):
        clear_database()      

    # データベースの初期化（初回実行時のみ）
    if 'db_initialized' not in st.session_state:
        init_db()
    st.session_state.db_initialized = True
    # --- 食材追加セクション ---
    st.header("食材の追加")
    with st.form("add_ingredient_form", clear_on_submit=True): # clear_on_submit を使用
        col1, col2 = st.columns(2)
        submitted = st.form_submit_button("食材を追加")
        with col1:
            name = st.text_input("食材名:", key="ingredient_name_input")
            purchase_date_str = st.text_input("購入日 (YYYY-MM-DD):", value=datetime.now().strftime("%Y-%m-%d"), key="purchase_date_input")
        with col2:
            expiry_date_str = st.text_input("期限 (YYYY-MM-DD):", value=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"), key="expiry_date_input")
            quantity = st.number_input("数量:", min_value=0.01, value=1.0, step=0.1, key="quantity_input")


    if submitted:
        if not all([name, purchase_date_str, expiry_date_str, quantity]):
            st.warning("すべてのフィールドを入力してください。")
        else:
            try:
                datetime.strptime(purchase_date_str, "%Y-%m-%d")
                datetime.strptime(expiry_date_str, "%Y-%m-%d")
                add_ingredient_to_db(name, purchase_date_str, expiry_date_str, quantity)
                # clear_on_submit=True を使用しているため、以下の手動リセットは不要になるはずです。
                # st.session_state.ingredient_name_input = ""
                # st.session_state.purchase_date_input = datetime.now().strftime("%Y-%m-%d")
                # st.session_state.expiry_date_input = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                # st.session_state.quantity_input = 1.0
            except ValueError:
                st.error("日付はYYYY-MM-DD形式、数量は数値で入力してください。")

    # --- 現在の食材リスト表示セクション ---
    st.header("現在の食材")
    ingredients_data = get_all_ingredients()
    if ingredients_data:
    # Streamlitのdataframeは列名を自動で設定しないため、手動で指定
    
        df_ingredients = pd.DataFrame(ingredients_data, columns=["ID", "食材名", "購入日", "期限", "数量"])
        st.dataframe(df_ingredients, use_container_width=True)
    else:
        st.info("データベースに食材がありません。")

    # --- 献立提案セクション ---
    st.header("献立提案")
    col_menu_input, col_menu_output = st.columns(2)

    with col_menu_input:
        serving_size = st.text_input("分量 (例: 2人分):", key="serving_size_input")
        preferences = st.text_input("好み (例: 和食、簡単):", key="preferences_input")

    if st.button("献立を提案"):
        if not ingredients_data:
            st.warning("食材がデータベースにありません。献立を提案できません。")
        else:
            with st.spinner("献立を生成中..."):
                ingredient_list_for_prompt = []
                for _, name, _, expiry_date, quantity in ingredients_data:
                    ingredient_list_for_prompt.append(f"{name} (期限: {expiry_date}, 数量: {quantity})")

                prompt = f"""
                以下の食材を使用して、献立を提案してください。
                提案は具体的なレシピ名、使用する食材、簡単な調理手順を含めてください。
                献立検討時には以下リンクの情報を参考にして、提案する際にはURLを添付してください。
                https://panasonic.jp/cooking/recipe/autocooker.html
                https://cookpad.com/jp
                期限が近い食材を優先的に使用してください。
                分量: {serving_size if serving_size else '指定なし'}
                好み: {preferences if preferences else '指定なし'}

                食材リスト:
                {', '.join(ingredient_list_for_prompt)}

                提案例:
                レシピ名: 鶏肉と野菜の炒め物
                使用食材: 鶏もも肉、玉ねぎ、ピーマン、にんじん
                調理手順: 1. 鶏肉と野菜を切る。2. フライパンで炒める。3. 塩コショウで味を調える。
                """

                if model:
                    try:
                        # Gemini API呼び出し
                        response = model.generate_content(prompt)
                        suggested_menu = response.text
                    except Exception as e:
                        st.error(f"Gemini API呼び出し中にエラーが発生しました: {e}")
                        suggested_menu = "献立の生成に失敗しました。"
                else:
                    # ダミー応答
                    suggested_menu = f"""
                    レシピ名: 鶏肉と野菜の彩り炒め (ダミー)
                    使用食材: 鶏もも肉、玉ねぎ、ピーマン、にんじん、キャベツ
                    調理手順: ダミーの調理手順です。

                    レシピ名: 大根と豚バラの煮物 (ダミー)
                    使用食材: 大根、豚バラ肉、生姜
                    調理手順: ダミーの調理手順です。
                    """
                st.session_state.current_suggested_menu = suggested_menu
                st.rerun() # 献立表示を更新するため再実行

    with col_menu_output:
        st.subheader("提案された献立:")
    if 'current_suggested_menu' in st.session_state and st.session_state.current_suggested_menu:
        st.text_area("献立", st.session_state.current_suggested_menu, height=300, key="menu_output_area")
        if st.button("この献立を選択"):
            suggested_menu_text = st.session_state.current_suggested_menu
            lines = suggested_menu_text.split('\n')
            used_ingredients = set()
            for line in lines:
                if "使用食材:" in line:
                    ingredients_str = line.split("使用食材:")[1].strip()
                    # カンマ、句読点、スペースで分割し、重複を避けるためにセットに追加
                    for item in ingredients_str.replace("、", ",").replace(" ", "").split(','):
                        if item:
                            used_ingredients.add(item.strip())

            if not used_ingredients:
                st.warning("使用された食材を特定できませんでした。")
            else:
                # Streamlitではmessagebox.askyesnoの代わりに確認UIを構築
                st.write(f"以下の食材をデータベースから削除しますか？\n{', '.join(used_ingredients)}")
                if st.button("はい、削除します"):
                    total_deleted_count = 0
                    for ingredient_name in used_ingredients:
                        deleted_count = delete_ingredient_from_db(ingredient_name)
                        total_deleted_count += deleted_count
                    st.success(f"{total_deleted_count}個の食材がデータベースから削除されました。")
                    st.session_state.current_suggested_menu = "" # 献立をクリア
                    st.rerun() # リストを更新するため再実行
                elif st.button("いいえ、削除しません"):
                    st.info("食材の削除はキャンセルされました。")
    else:
        st.info("献立を提案してください。")

if __name__ == "__main__":
    run_app()