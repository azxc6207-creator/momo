"""台灣麻將計台器（Streamlit，手機優先）。執行：streamlit run app.py"""
import hashlib
import json
from dataclasses import asdict

import pandas as pd
import streamlit as st

from cloud_store import connect
from mahjong_core import (DEFAULT_TAI_TABLE, ZIMO, Game, Rules, check_conflicts,
                          compute_hand_tai)

st.set_page_config(page_title="台灣麻將計台器", page_icon="🀄", layout="centered")

RULE_DEFAULTS = asdict(Rules())

# 座位編號 = 輪莊順序。畫面位置依真實牌桌逆時針：0 下 → 1 右 → 2 上 → 3 左
POS_NAMES = {0: "下", 1: "右", 2: "上", 3: "左"}

# 手機版：十字座位與工具列即使在窄螢幕也維持橫向並排（Streamlit 預設會把欄位直向堆疊）
CSS = """
<style>
.st-key-seat_board [data-testid="stHorizontalBlock"],
.st-key-newgame_board [data-testid="stHorizontalBlock"],
.st-key-seatswap_board [data-testid="stHorizontalBlock"],
.st-key-toolbar [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 0.4rem !important;
}
.st-key-seat_board [data-testid="stColumn"],
.st-key-newgame_board [data-testid="stColumn"],
.st-key-seatswap_board [data-testid="stColumn"],
.st-key-toolbar [data-testid="stColumn"],
.st-key-seat_board [data-testid="column"],
.st-key-newgame_board [data-testid="column"],
.st-key-seatswap_board [data-testid="column"],
.st-key-toolbar [data-testid="column"] {
    min-width: 0 !important;
    flex: 1 1 0 !important;
    width: auto !important;
}
.stButton button, .stDownloadButton button {
    width: 100%;
    min-height: 2.75rem;
}
.st-key-seat_board .stButton button {
    min-height: 5rem;
    padding: 0.25rem 0.25rem;
}
.st-key-seat_board .stButton button p {
    white-space: pre-line;
    line-height: 1.3;
    overflow-wrap: anywhere;
}
.seat-center {
    text-align: center;
    font-size: 0.9rem;
    line-height: 1.4;
    padding-top: 0.6rem;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------------ 狀態初始化
def init_state():
    for k, v in RULE_DEFAULTS.items():
        st.session_state.setdefault(k, v)
    st.session_state.setdefault("tai_base", pd.DataFrame(DEFAULT_TAI_TABLE))
    st.session_state.setdefault("tai_current", st.session_state["tai_base"])
    st.session_state.setdefault("game", None)
    st.session_state.setdefault("flash", None)
    st.session_state.setdefault("roster_text", "")
    st.session_state.setdefault("pending_winner", None)
    st.session_state.setdefault("open_dialog", None)
    st.session_state.setdefault("dlg_v", 0)


def rules_from_state() -> Rules:
    return Rules(**{k: st.session_state[k] for k in RULE_DEFAULTS})


def tai_table_from_df(df: pd.DataFrame) -> dict:
    table = {}
    for _, row in df.iterrows():
        name = str(row.get("名稱", "") or "").strip()
        tai = row.get("台數")
        if name and pd.notna(tai):
            table[name] = int(tai)
    return table


def parse_roster(text: str) -> list:
    names = []
    for part in text.replace("，", "\n").replace(",", "\n").splitlines():
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def flash(kind: str, msg: str):
    st.session_state["flash"] = (kind, msg)


# ------------------------------------------------------------------ callbacks
def set_preset(base, tai):
    st.session_state["base"] = base
    st.session_state["tai_value"] = tai


def reset_tai_table():
    st.session_state["tai_base"] = pd.DataFrame(DEFAULT_TAI_TABLE)
    st.session_state.pop("tai_editor", None)


def select_player(i: int):
    st.session_state["pending_winner"] = i


def request_dialog(name: str):
    st.session_state["open_dialog"] = name


def end_game():
    g = st.session_state["game"]
    if g is not None:  # 保留一份，按錯「結束牌局」時還能還原
        st.session_state["last_game"] = g.to_json(indent=None)
    st.session_state["game"] = None


def restore_last_game():
    text = st.session_state.get("last_game")
    if not text:
        return
    try:
        g = Game.from_json(text)
    except Exception:
        flash("error", "上一局資料損毀，無法還原。")
        return
    for k, v in asdict(g.rules).items():
        st.session_state[k] = v
    st.session_state["game"] = g
    st.session_state["last_game"] = ""
    flash("success", "已還原上一局。")


def load_game():
    up = st.session_state.get("upload")
    if up is None:
        return
    try:
        g = Game.from_json(up.getvalue().decode("utf-8"))
    except Exception:
        flash("error", "讀檔失敗，請確認是本程式匯出的 JSON。")
        return
    for k, v in asdict(g.rules).items():
        st.session_state[k] = v
    st.session_state["game"] = g
    flash("success", "已載入牌局。")


# ------------------------------------------------------------------ 雲端存檔（Google 試算表）
TAI_COLUMNS = ["名稱", "台數", "說明"]


@st.cache_resource(show_spinner=False)
def get_store():
    """未設定 Secrets → None；設定了卻連不上 → 丟出例外。"""
    try:
        secrets = st.secrets
        secrets["gsheet"]  # 沒有 secrets 檔或沒這個區段時，會在這裡失敗
    except Exception:
        return None
    return connect(secrets)


def tai_records(df: pd.DataFrame) -> list:
    out = []
    for _, row in df.iterrows():
        name = str(row.get("名稱", "") or "").strip()
        tai = row.get("台數")
        if name and pd.notna(tai):
            out.append({"名稱": name, "台數": int(tai), "說明": str(row.get("說明", "") or "")})
    return out


def collect_state() -> dict:
    """要存到雲端的全部資料，每個值都是文字。"""
    g = st.session_state["game"]
    return {
        "game": g.to_json(indent=None) if g is not None else "",
        "last_game": st.session_state.get("last_game") or "",
        "roster": st.session_state["roster_text"],
        "rules": json.dumps({k: st.session_state[k] for k in RULE_DEFAULTS}),
        "tai_table": json.dumps(tai_records(st.session_state["tai_current"]),
                                ensure_ascii=False),
    }


def state_signature(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def restore_state(data: dict):
    """把雲端資料放回畫面狀態。任何一項損毀就丟出例外（呼叫端會停用自動存檔，避免蓋掉雲端）。"""
    if data.get("roster"):
        st.session_state["roster_text"] = data["roster"]
    if data.get("rules"):
        saved = json.loads(data["rules"])
        for k in RULE_DEFAULTS:
            if k in saved:
                st.session_state[k] = saved[k]
    if data.get("tai_table"):
        df = pd.DataFrame(json.loads(data["tai_table"]), columns=TAI_COLUMNS)
        st.session_state["tai_base"] = df
        st.session_state["tai_current"] = df
    st.session_state["last_game"] = data.get("last_game", "")
    if data.get("game"):
        st.session_state["game"] = Game.from_json(data["game"])


def retry_cloud():
    st.session_state.pop("_cloud_ok", None)


def load_from_cloud(store):
    """每個新連線只在第一次執行時載入。失敗時 _cloud_ok=False，之後不會存檔、不會蓋掉雲端。"""
    if store is None or "_cloud_ok" in st.session_state:
        return
    try:
        restore_state(store.load_all())
    except Exception as e:
        st.session_state["_cloud_ok"] = False
        st.session_state["_cloud_msg"] = f"讀取雲端資料失敗：{e}"
        return
    st.session_state["_cloud_ok"] = True
    st.session_state["_cloud_msg"] = ""
    st.session_state["_saved_sig"] = state_signature(collect_state())
    st.session_state["_saved_game"] = collect_state()["game"]


def autosave(store, status, store_error=""):
    """每次執行結束時，若資料有變就存到雲端，並在畫面最上方顯示狀態。"""
    if store is None:
        if store_error:
            status.error(f"雲端存檔連線失敗（目前不會自動存檔）：{store_error}")
        else:
            status.caption("資料只存在這個網頁，重新整理會消失；請到「紀錄」分頁下載存檔，"
                           "或在 Secrets 設定 Google 試算表自動存檔。")
        return
    if not st.session_state.get("_cloud_ok"):
        with status.container():
            st.error(st.session_state.get("_cloud_msg") or "雲端存檔尚未連線。")
            st.button("重新連線雲端", on_click=retry_cloud)
        return

    data = collect_state()
    sig = state_signature(data)
    notes = []
    if sig != st.session_state.get("_saved_sig"):
        try:
            store.save_all(data)
        except Exception as e:
            status.warning(f"☁️ 雲端存檔失敗，下次操作會再試一次：{e}")
            return
        st.session_state["_saved_sig"] = sig
    # 「牌局紀錄」分頁（給人看的表）只在牌局內容變動時更新；失敗會在下次再試
    if data["game"] != st.session_state.get("_saved_game"):
        try:
            store.save_log(st.session_state["game"])
            st.session_state["_saved_game"] = data["game"]
        except Exception as e:
            notes.append(f"（資料已存，但「牌局紀錄」分頁更新失敗：{e}）")
    status.caption("☁️ 已自動存到 Google 試算表" + "".join(notes))


# ------------------------------------------------------------------ 共用版面
def seat_cross(cell, center=None, key="seat_board"):
    """十字座位：上 / 左 中 右 / 下。cell(i) 畫第 i 號座位，center() 畫中央。"""
    with st.container(key=key):
        _, top, _ = st.columns(3)
        with top:
            cell(2)
        left, mid, right = st.columns(3)
        with left:
            cell(3)
        with mid:
            if center:
                center()
        with right:
            cell(1)
        _, bottom, _ = st.columns(3)
        with bottom:
            cell(0)


# ------------------------------------------------------------------ 對話視窗
@st.dialog("開始新牌局")
def new_game_dialog(roster: list):
    if len(roster) < 4:
        st.warning("玩家名單不足 4 人，請先到「設定」分頁新增玩家名稱。")
        return
    st.caption("依玩家在桌上的位置選擇（輪莊順序：下 → 右 → 上 → 左）。")
    sig = abs(hash(tuple(roster)))  # 名單變動時重置下拉選單，避免殘留已刪除的名字
    picks = {}

    def cell(i):
        picks[i] = st.selectbox(POS_NAMES[i], roster, index=i, key=f"ng_{i}_{sig}")

    seat_cross(cell, key="newgame_board")
    first = st.selectbox("起莊（東家）", [0, 1, 2, 3], key=f"ng_first_{sig}",
                         format_func=lambda i: f"{POS_NAMES[i]}：{picks[i]}")
    if st.button("開始", type="primary"):
        names = [picks[i] for i in range(4)]
        if len(set(names)) < 4:
            st.error("四個位置的玩家不能重複。")
        else:
            st.session_state["game"] = Game(players=names, rules=rules_from_state(),
                                            dealer=first)
            flash("success", "牌局開始。點選玩家即可記錄胡牌。")
            st.rerun()


@st.dialog("記錄胡牌")
def win_dialog(winner: int, v: int, tai_table: dict):
    g: Game = st.session_state["game"]
    st.markdown(f"#### {g.players[winner]}（{g.seat_wind(winner)}家）")
    way = st.radio("方式", ["自摸", "胡牌（別人放槍）"], horizontal=True, key=f"w_kind_{v}")
    kind = "自摸" if way == "自摸" else "放槍"
    discarder = None
    if kind == "放槍":
        others = [i for i in range(4) if i != winner]
        discarder = st.selectbox("胡誰的（放槍者）", others, key=f"w_dis_{v}",
                                 format_func=lambda i: g.players[i])

    choices = [n for n in tai_table if n != ZIMO]
    picked = st.multiselect("牌型台數（可多選，自摸會自動加入）", choices, key=f"w_items_{v}")
    extra = st.number_input("額外台數（花牌、花槓、其他）", min_value=0, step=1, value=0,
                            key=f"w_extra_{v}")
    for m in check_conflicts(picked, kind):
        st.warning(m)

    hand_tai, breakdown = compute_hand_tai(tai_table, picked, kind, extra)
    detail = "、".join(f"{n} {t}" for n, t in breakdown) or "無"
    st.caption(f"牌型台數 {hand_tai} 台（{detail}）")

    calc = g.calc_win(winner, kind, hand_tai, discarder)

    manual = st.checkbox("手動修改金額", key=f"w_man_{v}",
                         help="金額與規則不同時（例如打錯、特殊約定）可逐家自訂")
    override = None
    if manual:
        override = {}
        for p in calc["payments"]:
            override[p["payer"]] = st.number_input(
                f"{g.players[p['payer']]} 付", min_value=0, step=10, value=int(p["amount"]),
                key=f"w_ovr_{v}_{p['payer']}_{p['amount']}")

    final = g.calc_win(winner, kind, hand_tai, discarder, override)
    for p in final["payments"]:
        bonus = f"，含莊家加成 {g.dealer_bonus_tai()} 台" if p["dealer_involved"] else ""
        note = "（手動）" if p["manual"] else f"（{p['tai']} 台{bonus}）"
        st.markdown(f"- **{g.players[p['payer']]}** 付 **{p['amount']:,}** {note}")
    total = sum(p["amount"] for p in final["payments"])
    st.markdown(f"**{g.players[winner]} 共贏 {total:,} 元**")

    if st.button("確認登記", type="primary", key=f"w_ok_{v}"):
        try:
            g.apply_win(winner, kind, hand_tai, discarder, [n for n, _ in breakdown], override)
        except ValueError as e:
            st.error(str(e))
        else:
            flash("success", f"已登記：{g.players[winner]} {way.split('（')[0]}。填錯可按「復原」。")
            st.rerun()


@st.dialog("手動調整積分")
def adjust_dialog(v: int):
    g: Game = st.session_state["game"]
    st.caption("輸入每位玩家要增減的金額（可為負數）。調整不影響莊家、連莊與局數，"
               "也可以用「復原」取消。")
    deltas = []
    for i in range(4):
        deltas.append(st.number_input(f"{g.players[i]}（目前 {g.scores[i]:+,}）",
                                      step=10, value=0, key=f"adj_{v}_{i}"))
    note = st.text_input("備註（選填）", key=f"adj_note_{v}")
    total = sum(deltas)
    if total != 0:
        st.warning(f"調整合計 {total:+,}，不為 0，全桌總積分將不再平衡。")
    if any(deltas):
        st.caption("調整後：" + "、".join(
            f"{g.players[i]} {g.scores[i] + deltas[i]:+,}" for i in range(4)))
    if st.button("套用調整", type="primary", key=f"adj_ok_{v}"):
        try:
            g.apply_adjust(deltas, note.strip())
        except ValueError as e:
            st.error(str(e))
        else:
            flash("success", "已調整積分。")
            st.rerun()


@st.dialog("調整座位")
def seat_dialog(v: int):
    g: Game = st.session_state["game"]
    st.caption("為每個位置重新選擇玩家。積分與紀錄會跟著玩家走，"
               "輪莊順序依「下 → 右 → 上 → 左」重新計算。")
    picks = {}

    def cell(i):
        picks[i] = st.selectbox(POS_NAMES[i], [0, 1, 2, 3], index=i, key=f"seat_{v}_{i}",
                                format_func=lambda k: g.players[k])

    seat_cross(cell, key="seatswap_board")
    if st.button("套用座位", type="primary", key=f"seat_ok_{v}"):
        order = [picks[i] for i in range(4)]
        try:
            g.reseat(order)
        except ValueError:
            st.error("四個位置的玩家不能重複。")
        else:
            flash("success", "已調整座位。")
            st.rerun()


# ------------------------------------------------------------------ 主程式
init_state()
store, store_error = None, ""
try:
    store = get_store()
except Exception as e:
    store_error = str(e)
load_from_cloud(store)  # 新連線的第一次執行：從 Google 試算表載入資料
status = st.empty()
rules = rules_from_state()
tab_game, tab_settings, tab_history = st.tabs(["🀄 牌局", "⚙️ 設定", "📜 紀錄"])

# 先執行設定分頁，讓牌局分頁一定讀到最新設定
with tab_settings:
    st.subheader("玩家名單")
    st.text_area("每行一位玩家（也可用逗號分隔）", key="roster_text", height=140,
                 placeholder="小明\n小華\n阿美\n阿強")
    roster = parse_roster(st.session_state["roster_text"])
    st.caption(f"目前共 {len(roster)} 位。開新牌局時可從下拉選單選擇。"
               "名單只存在這次開啟的網頁中，重新整理後需重新輸入。")

    st.subheader("底與台")
    c1, c2 = st.columns(2)
    c1.number_input("底（元）", min_value=0, step=10, key="base")
    c2.number_input("每台（元）", min_value=0, step=5, key="tai_value")
    p1, p2, p3 = st.columns(3)
    p1.button("100 / 20", on_click=set_preset, args=(100, 20))
    p2.button("300 / 100", on_click=set_preset, args=(300, 100))
    p3.button("50 / 10", on_click=set_preset, args=(50, 10))
    st.caption("每家應付金額 = 底 + 台數 × 每台")

    st.subheader("莊家與連莊")
    c3, c4 = st.columns(2)
    c3.number_input("莊家身分台數", min_value=0, step=1, key="dealer_tai",
                    help="莊家胡牌，或莊家付錢時加的台數")
    c4.number_input("每次連莊加幾台", min_value=0, step=1, key="streak_tai",
                    help="2 = 連 n 拉 n（連 1 拉 1 共 3 台含莊家 1 台）；1 = 只加連莊數")
    st.number_input("連莊最多計到幾次（0 = 不設上限）", min_value=0, step=1,
                    key="streak_cap")
    st.checkbox("流局時原莊家繼續做莊", key="draw_keep_dealer")
    st.checkbox("流局算一次連莊（累計連莊數）", key="draw_count_streak",
                disabled=not st.session_state["draw_keep_dealer"])
    bonus_example = [rules.dealer_tai + n * rules.streak_tai for n in range(0, 4)]
    st.caption("目前莊家加成台數：莊家 0 連 / 1 連 / 2 連 / 3 連 → "
               + " / ".join(f"{t} 台" for t in bonus_example))

    st.subheader("台數表")
    st.caption("可直接修改台數、新增或刪除列（表格左下角的 + 可新增）。"
               "各地台數略有差異，請依你們的規則調整。")
    edited = st.data_editor(
        st.session_state["tai_base"], num_rows="dynamic", hide_index=True,
        key="tai_editor",
        column_config={
            "名稱": st.column_config.TextColumn(required=True),
            "台數": st.column_config.NumberColumn(min_value=0, step=1, required=True),
            "說明": st.column_config.TextColumn(),
        },
    )
    st.session_state["tai_current"] = edited
    st.button("還原預設台數表", on_click=reset_tai_table)

tai_table = tai_table_from_df(st.session_state["tai_current"])

# ------------------------------------------------------------------ 牌局分頁
with tab_game:
    fl = st.session_state.get("flash")
    if fl:
        getattr(st, fl[0])(fl[1])
        st.session_state["flash"] = None

    g = st.session_state["game"]

    if g is None:
        st.subheader("🀄 台灣麻將計台器")
        if len(roster) < 4:
            st.info("先到「設定」分頁新增至少 4 位玩家名稱，開局時就能用下拉選單選人。")
        if st.button("➕ 開始新牌局", type="primary"):
            new_game_dialog(roster)
    else:
        g.rules = rules  # 設定的修改會套用在之後的牌局

        def board_cell(i):
            wind = g.seat_wind(i)
            role = "莊" + (f" 連{g.streak}" if g.streak else "") if i == g.dealer else ""
            label = f"{g.players[i]}\n{wind}家 {role}".rstrip() + f"\n{g.scores[i]:+,}"
            st.button(label, key=f"seat_btn_{i}", type="primary" if i == g.dealer else "secondary",
                      on_click=select_player, args=(i,))

        def board_center():
            streak_txt = f"連莊 {g.streak}" if g.streak else "未連莊"
            st.markdown(
                f"<div class='seat-center'><b>{g.round_label()}</b><br>第 {g.hand_no} 把<br>"
                f"{streak_txt}<br>莊家加成 {g.dealer_bonus_tai()} 台</div>",
                unsafe_allow_html=True)

        seat_cross(board_cell, board_center, key="seat_board")
        st.caption("👆 點選玩家，再選擇「自摸」或「胡牌（胡誰的）」。藍色為莊家。")

        pw = st.session_state.pop("pending_winner", None)
        if pw is not None:
            st.session_state["dlg_v"] += 1
            win_dialog(pw, st.session_state["dlg_v"], tai_table)

        if rules.draw_keep_dealer:
            draw_note = ("莊家連莊 +1" if rules.draw_count_streak else "莊家續莊、連莊數不變")
        else:
            draw_note = "換下一位做莊"
        if st.button(f"🌫️ 流局（{draw_note}）"):
            g.apply_draw()
            flash("success", "已登記流局。")
            st.rerun()

        with st.container(key="toolbar"):
            t1, t2, t3 = st.columns(3)
            with t1:
                if st.button("↩︎ 復原", disabled=not g.history,
                             help="取消上一筆（胡牌、流局或積分調整）"):
                    last = g.history[-1]
                    g.undo()
                    what = {"win": "胡牌", "draw": "流局", "adjust": "積分調整"}[last["type"]]
                    flash("success", f"已復原上一筆（{what}）。")
                    st.rerun()
            with t2:
                st.button("✏️ 調整積分", on_click=request_dialog, args=("adjust",))
            with t3:
                st.button("🔀 換座位", on_click=request_dialog, args=("seat",))

        # 對話視窗在版面容器之外開啟
        which = st.session_state.pop("open_dialog", None)
        if which in ("adjust", "seat"):
            st.session_state["dlg_v"] += 1
            (adjust_dialog if which == "adjust" else seat_dialog)(st.session_state["dlg_v"])

# ------------------------------------------------------------------ 紀錄分頁
with tab_history:
    g = st.session_state["game"]
    if g is None:
        st.info("尚未開始牌局。也可以在這裡載入之前存的牌局。")
        if st.session_state.get("last_game"):
            st.button("↩︎ 還原上一局（剛才按了結束牌局）", on_click=restore_last_game)
    else:
        st.subheader("目前積分")
        st.dataframe(pd.DataFrame({
            "玩家": g.players,
            "門風": [g.seat_wind(i) for i in range(4)],
            "累計": g.scores,
        }), hide_index=True)

        rows = g.history_rows()
        st.subheader("每把紀錄")
        if rows:
            hist_df = pd.DataFrame(rows)
            st.dataframe(hist_df, hide_index=True)
            st.download_button("下載紀錄 CSV", hist_df.to_csv(index=False).encode("utf-8-sig"),
                               "mahjong_history.csv", "text/csv")
        else:
            st.caption("還沒有任何紀錄。")

        st.subheader("存檔 / 結束")
        st.download_button("下載牌局存檔 (JSON)", g.to_json().encode("utf-8"),
                           "mahjong_game.json", "application/json")
        st.button("結束牌局（清除目前資料）", on_click=end_game)

    st.subheader("載入存檔")
    st.file_uploader("選擇先前下載的 JSON", type="json", key="upload")
    st.button("載入", on_click=load_game)

# ------------------------------------------------------------------ 雲端自動存檔（放在最後，涵蓋本次所有變動）
autosave(store, status, store_error)
