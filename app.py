"""台灣麻將計台器（Streamlit，手機優先）。執行：streamlit run app.py"""
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from cloud_store import connect
from mahjong_core import (DEFAULT_TAI_TABLE, WINDS, ZIMO, Game, Rules, check_conflicts,
                          compute_hand_tai, settlement)

st.set_page_config(page_title="台灣麻將計台器", page_icon="🀄", layout="centered")

RULE_DEFAULTS = asdict(Rules())
ss = st.session_state

# 座位編號 = 輪莊順序。畫面位置依真實牌桌逆時針：0 下 → 1 右 → 2 上 → 3 左
POS_NAMES = {0: "下", 1: "右", 2: "上", 3: "左"}
DISPLAY_MODES = ("累計", "本將")

# 手機版：十字座位與工具列即使在窄螢幕也維持橫向並排（Streamlit 預設會把欄位直向堆疊）
CSS = """
<style>
.st-key-seat_board [data-testid="stHorizontalBlock"],
.st-key-newgame_board [data-testid="stHorizontalBlock"],
.st-key-seatswap_board [data-testid="stHorizontalBlock"],
.st-key-toolbar [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 0.35rem !important;
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
.stButton button, .stDownloadButton button { width: 100%; min-height: 2.75rem; }

/* 點擊縮放：按下去縮小一點，放開時回彈 */
.stButton button, .stDownloadButton button {
    transition: transform 0.14s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.14s ease !important;
    -webkit-tap-highlight-color: transparent;
    touch-action: manipulation;
    will-change: transform;
}
.stButton button:active, .stDownloadButton button:active { transform: scale(0.94) !important; }
.st-key-seat_board .stButton button:active { transform: scale(0.95) !important; box-shadow: inset 0 0 0 2px rgba(47, 107, 58, 0.35) !important; }
.st-key-toolbar .stButton button:active { transform: scale(0.9) !important; }
.st-key-seat_board .st-key-btn_mode button:active { transform: scale(0.9) !important; }
@media (prefers-reduced-motion: reduce) {
    .stButton button, .stDownloadButton button { transition: none !important; }
}

/* 分頁列：平均分配寬度 */
.stTabs [data-baseweb="tab-list"] { gap: 0; }
.stTabs [data-baseweb="tab"] { flex: 1; justify-content: center; padding: 0.5rem 0.2rem; }

/* 標題列 */
.game-header {
    background: #2f6b3a; color: #fff; border-radius: 14px;
    padding: 0.65rem 0.8rem; text-align: center; margin-bottom: 0.6rem;
}
.gh-title { font-size: 1.5rem; font-weight: 800; line-height: 1.25; }
.gh-sub { font-size: 0.92rem; opacity: 0.95; }

/* 工具列 */
.st-key-toolbar button { min-height: 4rem; padding: 0.2rem 0.1rem; }
.st-key-toolbar button p { white-space: pre-line; font-size: 0.74rem; line-height: 1.35; }

/* 座位卡片 */
.st-key-seat_board .stButton button {
    min-height: 5.4rem; padding: 0.3rem 0.2rem; background: #fff;
    border: 1.5px solid #cfcfcf; border-radius: 10px;
}
.st-key-seat_board .stButton button p {
    white-space: pre-line; line-height: 1.35; font-size: 0.78rem; overflow-wrap: anywhere;
}
.st-key-seat_board .stButton button strong { font-size: 1.45rem; }
.st-key-seat_board [class*="_dealer"] button { border: 2.5px solid #c62828 !important; background: #fff6f6 !important; }
.st-key-seat_board .st-key-btn_draw button { background: #b0bec5; border: none; min-height: 4.2rem; }
.st-key-seat_board .st-key-btn_mode button {
    border-radius: 50%; aspect-ratio: 1 / 1; min-height: 0; background: #e0e0e0;
    border: 3px solid #bdbdbd; padding: 0.1rem;
}
.st-key-seat_board .st-key-btn_mode button p { font-size: 0.7rem; }
.wind-box {
    background: #444; color: #fff; border-radius: 10px; font-size: 2rem;
    font-weight: 800; text-align: center; padding: 0.3rem 0; line-height: 1.3;
    margin-bottom: 0.3rem;
}
.wind-sub { text-align: center; font-size: 0.72rem; color: #666; margin-bottom: 0.3rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------------ 小工具
def md_escape(text: str) -> str:
    """玩家名稱放進 Markdown 前，跳脫會被當成格式的符號。"""
    out = []
    for ch in str(text):
        out.append("\\" + ch if ch in "\\`*_{}[]<>()#+!|~:" else ch)
    return "".join(out)


def today_str() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")  # 台灣時間


def money(n: int, sign: bool = False) -> str:
    return f"{n:+,}" if sign else f"{n:,}"


def colored(n: int, sign: bool = True) -> str:
    text = money(n, sign)
    if n > 0:
        return f":green[{text}]"
    if n < 0:
        return f":red[{text}]"
    return text


def pick_choice(label: str, options: list, key: str, default=None):
    """折疊式單選：平常只顯示「標題：目前選擇」，點開才出現一排按鈕，選了就更新（取代下拉選單）。"""
    options = list(options)
    if not options:
        return None
    vkey, pkey = f"{key}__val", f"{key}__pill"
    if vkey not in ss or ss[vkey] not in options:
        ss[vkey] = default if default in options else options[0]
    if pkey in ss and ss[pkey] not in options:
        del ss[pkey]

    def _cb():
        v = ss.get(pkey)
        if v in options:
            ss[vkey] = v

    cur = ss[vkey]
    with st.expander(f"{label}：{cur}", expanded=False):
        st.pills(label, options, selection_mode="single", default=cur, key=pkey,
                 on_change=_cb, label_visibility="collapsed")
    return ss[vkey]


def pick_multi(label: str, options: list, key: str) -> list:
    """折疊式多選：標題列顯示已選項目，點開後可複選。"""
    options = list(options)
    vkey, pkey = f"{key}__val", f"{key}__pill"
    ss[vkey] = [v for v in ss.get(vkey, []) if v in options]
    if pkey in ss:
        ss[pkey] = [v for v in ss[pkey] if v in options]

    def _cb():
        ss[vkey] = [v for v in (ss.get(pkey) or []) if v in options]

    cur = ss[vkey]
    summary = "、".join(cur) if cur else "無"
    with st.expander(f"{label}：{summary}", expanded=False):
        st.pills(label, options, selection_mode="multi", default=cur, key=pkey,
                 on_change=_cb, label_visibility="collapsed")
    return list(ss[vkey])


# ------------------------------------------------------------------ 狀態初始化
def init_state():
    for k, v in RULE_DEFAULTS.items():
        ss.setdefault(k, v)
    ss.setdefault("tai_base", pd.DataFrame(DEFAULT_TAI_TABLE))
    ss.setdefault("tai_current", ss["tai_base"])
    ss.setdefault("game", None)
    ss.setdefault("archive", [])
    ss.setdefault("flash", None)
    ss.setdefault("roster_text", "")
    ss.setdefault("pending_winner", None)
    ss.setdefault("open_dialog", None)
    ss.setdefault("dlg_v", 0)
    ss.setdefault("view_rot", 0)
    ss.setdefault("display_mode", DISPLAY_MODES[0])
    ss.setdefault("swap_sel", None)


def rules_from_state() -> Rules:
    return Rules(**{k: ss[k] for k in RULE_DEFAULTS})


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
    ss["flash"] = (kind, msg)


# ------------------------------------------------------------------ 牌局歸檔
def archive_entry(g: Game) -> dict:
    return {"no": g.no, "created": g.created, "ended": today_str(),
            "players": list(g.players), "scores": list(g.scores),
            "hands": g.hands_played(), "game": g.to_json(indent=None)}


def next_game_no() -> int:
    nos = [int(e.get("no", 0)) for e in ss["archive"]]
    return max(nos, default=0) + 1


def adopt_rules(g: Game):
    for k, v in asdict(g.rules).items():
        ss[k] = v


# ------------------------------------------------------------------ callbacks
def set_preset(base, tai):
    ss["base"] = base
    ss["tai_value"] = tai


def reset_tai_table():
    ss["tai_base"] = pd.DataFrame(DEFAULT_TAI_TABLE)
    ss.pop("tai_editor", None)


def select_player(i: int):
    ss["pending_winner"] = i


def request_dialog(name: str):
    ss["open_dialog"] = name


def do_undo():
    g = ss["game"]
    if g is None or not g.history:
        return
    what = {"win": "胡牌", "draw": "流局", "adjust": "分數調整"}[g.history[-1]["type"]]
    g.undo()
    flash("success", f"已復原上一筆（{what}）。")


def do_draw():
    g = ss["game"]
    if g is not None:
        g.apply_draw()
        flash("success", "已登記流局。")


def rotate_view():
    ss["view_rot"] = (ss["view_rot"] + 1) % 4


def toggle_mode():
    ss["display_mode"] = DISPLAY_MODES[1] if ss["display_mode"] == DISPLAY_MODES[0] else DISPLAY_MODES[0]


def tap_seat(i: int):
    """調整位置：先點一位、再點另一位，兩人互換座位。"""
    g = ss["game"]
    sel = ss.get("swap_sel")
    if sel is None:
        ss["swap_sel"] = i
    elif sel == i:
        ss["swap_sel"] = None
    else:
        order = [0, 1, 2, 3]
        order[sel], order[i] = order[i], order[sel]
        g.reseat(order)
        ss["swap_sel"] = None
        ss["_swap_done"] = True       # 通知對話視窗：整頁重跑並重新開啟
        ss["open_dialog"] = "seat"
        flash("success", f"已互換 {g.players[sel]} 與 {g.players[i]} 的位置。")


def resume_archived(idx: int):
    if ss["game"] is not None:
        flash("error", "請先結束目前的牌局，才能繼續舊牌局。")
        return
    try:
        g = Game.from_json(ss["archive"][idx]["game"])
    except Exception:
        flash("error", "這局的資料損毀，無法繼續。")
        return
    ss["archive"].pop(idx)
    adopt_rules(g)
    ss["game"] = g
    ss["view_rot"] = 0
    flash("success", f"已繼續牌局 {g.no}。")


def delete_archived(idx: int):
    if 0 <= idx < len(ss["archive"]):
        ss["archive"].pop(idx)
        flash("success", "已刪除。")


def load_game():
    up = ss.get("upload")
    if up is None:
        return
    try:
        g = Game.from_json(up.getvalue().decode("utf-8"))
    except Exception:
        flash("error", "讀檔失敗，請確認是本程式匯出的 JSON。")
        return
    adopt_rules(g)
    ss["game"] = g
    flash("success", "已載入牌局。")


# ------------------------------------------------------------------ 全部資料備份
BACKUP_APP = "taiwan-mahjong-scorer"


def backup_bytes() -> bytes:
    data = collect_state()
    data.pop("views_sig", None)
    payload = {"app": BACKUP_APP, "version": 1, "saved": today_str(), **data}
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def load_backup():
    """還原全部備份。先完整驗證檔案，確定可用才覆蓋目前資料。"""
    up = ss.get("backup_upload")
    if up is None:
        flash("error", "請先選擇備份檔。")
        return
    try:
        data = json.loads(up.getvalue().decode("utf-8"))
        if not isinstance(data, dict) or data.get("app") != BACKUP_APP:
            raise ValueError("不是本程式的備份檔")
        data = {k: v for k, v in data.items() if k in ("game", "archive", "roster", "rules", "tai_table")}
        if data.get("game"):
            Game.from_json(data["game"])
        for k in ("archive", "rules", "tai_table"):
            if data.get(k):
                json.loads(data[k])
    except Exception:
        flash("error", "還原失敗：請確認是「下載全部資料備份」匯出的 JSON，目前資料沒有被改動。")
        return
    ss["game"] = None
    ss["archive"] = []
    ss.pop("tai_editor", None)
    restore_state(data)
    ss["_views_sig"] = "stale"          # 讓雲端的「過去牌局」報表重新寫入
    ss["view_rot"] = 0
    ss["swap_sel"] = None
    ss["backup_ok"] = False
    flash("success", "已還原全部備份。")


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
    g = ss["game"]
    return {
        "game": g.to_json(indent=None) if g is not None else "",
        "archive": json.dumps(ss["archive"], ensure_ascii=False),
        "roster": ss["roster_text"],
        "rules": json.dumps({k: ss[k] for k in RULE_DEFAULTS}),
        "tai_table": json.dumps(tai_records(ss["tai_current"]), ensure_ascii=False),
        "views_sig": ss.get("_views_sig", ""),   # 「過去牌局」報表上次寫入時對應的資料版本
    }


def state_signature(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def restore_state(data: dict) -> bool:
    """把雲端資料放回畫面狀態。任何一項損毀就丟出例外（呼叫端會停用自動存檔，避免蓋掉雲端）。

    回傳 True 表示有把舊版資料搬到新格式，需要立刻存回雲端。
    """
    migrated = False
    ss["_views_sig"] = data.get("views_sig", "")
    if data.get("roster"):
        ss["roster_text"] = data["roster"]
    if data.get("rules"):
        saved = json.loads(data["rules"])
        for k in RULE_DEFAULTS:
            if k in saved:
                ss[k] = saved[k]
    if data.get("tai_table"):
        df = pd.DataFrame(json.loads(data["tai_table"]), columns=TAI_COLUMNS)
        ss["tai_base"] = df
        ss["tai_current"] = df
    if data.get("archive"):
        ss["archive"] = json.loads(data["archive"])
    if data.get("last_game"):           # 舊版的「上一局」改放進牌局紀錄
        old = Game.from_json(data["last_game"])
        old.no = old.no if old.no > 1 else next_game_no()
        ss["archive"].append(archive_entry(old))
        migrated = True
    if data.get("game"):
        ss["game"] = Game.from_json(data["game"])
    return migrated


def retry_cloud():
    ss.pop("_cloud_ok", None)


def load_from_cloud(store):
    """每個新連線只在第一次執行時載入。失敗時 _cloud_ok=False，之後不會存檔、不會蓋掉雲端。"""
    if store is None or "_cloud_ok" in ss:
        return
    try:
        migrated = restore_state(store.load_all())
    except Exception as e:
        ss["_cloud_ok"] = False
        ss["_cloud_msg"] = f"讀取雲端資料失敗：{e}"
        return
    ss["_cloud_ok"] = True
    ss["_cloud_msg"] = ""
    ss["_saved_sig"] = "" if migrated else state_signature(collect_state())
    ss["_saved_game"] = collect_state()["game"]


def autosave(store, status, store_error=""):
    """每次執行結束時，若資料有變就存到雲端，並在畫面最上方顯示狀態。"""
    if store is None:
        if store_error:
            status.error(f"雲端存檔連線失敗（目前不會自動存檔）：{store_error}")
        else:
            status.caption("資料只存在這個網頁，重新整理會消失；請到「設定」分頁下載存檔，"
                           "或在 Secrets 設定 Google 試算表自動存檔。")
        return
    if not ss.get("_cloud_ok"):
        with status.container():
            st.error(ss.get("_cloud_msg") or "雲端存檔尚未連線。")
            st.button("重新連線雲端", on_click=retry_cloud)
        return

    notes = []
    # 已結束的牌局變動時，重寫「過去牌局」「過去明細」兩個給人看的分頁；失敗下次再試
    views_target = (hashlib.sha256(json.dumps(ss["archive"], sort_keys=True).encode("utf-8")).hexdigest()
                    if ss["archive"] else "")
    if views_target != ss.get("_views_sig", ""):
        try:
            store.save_archive_views(ss["archive"])
            ss["_views_sig"] = views_target
        except Exception as e:
            notes.append(f"（「過去牌局」分頁更新失敗：{e}）")

    data = collect_state()
    sig = state_signature(data)
    if sig != ss.get("_saved_sig"):
        try:
            store.save_all(data)
        except Exception as e:
            status.warning(f"☁️ 雲端存檔失敗，下次操作會再試一次：{e}")
            return
        ss["_saved_sig"] = sig
    # 「牌局紀錄」分頁（給人看的表）只在牌局內容變動時更新；失敗會在下次再試
    if data["game"] != ss.get("_saved_game"):
        try:
            store.save_log(ss["game"])
            ss["_saved_game"] = data["game"]
        except Exception as e:
            notes.append(f"（資料已存，但「牌局紀錄」分頁更新失敗：{e}）")
    status.caption("☁️ 已自動存到 Google 試算表" + "".join(notes))


# ------------------------------------------------------------------ 共用版面
def seat_cross(cell, center=None, key="seat_board", bottom_left=None):
    """十字座位：上 / 左 中 右 / 下。cell(pos) 畫畫面位置 pos（0 下 1 右 2 上 3 左）。"""
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
        corner, bottom, _ = st.columns(3)
        with corner:
            if bottom_left:
                bottom_left()
        with bottom:
            cell(0)


def stats_frame(g: Game, jiang) -> pd.DataFrame:
    s = g.stats(jiang)
    return pd.DataFrame({
        "玩家": g.players,
        "自摸": [r["zimo"] for r in s],
        "胡牌": [r["ron"] for r in s],
        "放槍": [r["discard"] for r in s],
        "淨額": g.scope_scores(jiang),
    })


# ------------------------------------------------------------------ 對話視窗
@st.dialog("開始新牌局")
def new_game_dialog(roster: list):
    if len(roster) < 4:
        st.warning("玩家名單不足 4 人，請先到「設定」分頁新增玩家名稱。")
        return
    st.caption("依玩家在桌上的位置選擇（輪莊順序：下 → 右 → 上 → 左）。")
    sig = abs(hash(tuple(roster)))  # 名單變動時重置選擇，避免殘留已刪除的名字
    names = [pick_choice(f"{POS_NAMES[i]}位", roster, key=f"ng_{i}_{sig}", default=roster[i])
             for i in range(4)]
    first_pos = pick_choice("起莊位置", [f"{POS_NAMES[i]}位" for i in range(4)],
                            key=f"ng_first_{sig}")
    first = [f"{POS_NAMES[i]}位" for i in range(4)].index(first_pos)

    def preview(pos):
        mark = "🔴 " if pos == first else ""
        st.markdown(f"<div style='text-align:center;font-weight:700'>{mark}{md_html(names[pos])}</div>",
                    unsafe_allow_html=True)

    seat_cross(preview, key="newgame_board")
    if st.button("開始", type="primary"):
        if len(set(names)) < 4:
            st.error("四個位置的玩家不能重複。")
        else:
            ss["game"] = Game(players=names, rules=rules_from_state(), dealer=first,
                              no=next_game_no(), created=today_str())
            ss["view_rot"] = 0
            ss["display_mode"] = DISPLAY_MODES[0]
            flash("success", "牌局開始。點選玩家即可記錄自摸或胡牌。")
            st.rerun()


def md_html(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


@st.dialog("記錄胡牌")
def win_dialog(winner: int, v: int, tai_table: dict):
    g: Game = ss["game"]
    st.markdown(f"#### {md_escape(g.players[winner])}（{g.seat_wind(winner)}家）")
    way = st.radio("方式", ["自摸", "胡牌（別人放槍）"], horizontal=True, key=f"w_kind_{v}")
    kind = "自摸" if way == "自摸" else "放槍"
    discarder = None
    if kind == "放槍":
        others = [g.players[i] for i in range(4) if i != winner]
        chosen = pick_choice("胡誰的（放槍者）", others, key=f"w_dis_{v}")
        discarder = g.players.index(chosen)

    choices = [n for n in tai_table if n != ZIMO]
    picked = pick_multi("牌型台數", choices, key=f"w_items_{v}")
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
        st.markdown(f"- **{md_escape(g.players[p['payer']])}** 付 **{p['amount']:,}** {note}")
    total = sum(p["amount"] for p in final["payments"])
    st.markdown(f"**{md_escape(g.players[winner])} 共贏 {total:,} 元**")

    if st.button("確認登記", type="primary", key=f"w_ok_{v}"):
        try:
            g.apply_win(winner, kind, hand_tai, discarder, [n for n, _ in breakdown], override)
        except ValueError as e:
            st.error(str(e))
        else:
            flash("success", f"已登記：{g.players[winner]} {way.split('（')[0]}。填錯可按「復原操作」。")
            st.rerun()


@st.dialog("調整分數")
def adjust_dialog(v: int):
    g: Game = ss["game"]
    st.caption("輸入每位玩家要增減的金額（可為負數）。調整不影響莊家、連莊與局數，"
               "也可以用「復原操作」取消。")
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
            flash("success", "已調整分數。")
            st.rerun()


@st.dialog("調整位置")
def seat_dialog(v: int):
    if ss.pop("_swap_done", False):
        st.rerun()  # 互換完成：整頁重跑（背景牌桌更新），並重新開啟本視窗
    g: Game = ss["game"]
    st.caption("先點一位玩家，再點要和他互換位置的另一位。座位順序就是輪莊順序，"
               "積分與紀錄會跟著玩家走。")
    sel = ss.get("swap_sel")
    rot = ss["view_rot"]

    def cell(pos):
        i = (pos + rot) % 4
        mark = "🔸 " if sel == i else ""
        st.button(f"{mark}{g.players[i]}", key=f"swap_{pos}", on_click=tap_seat, args=(i,))

    seat_cross(cell, key="seatswap_board")
    if sel is not None:
        st.caption(f"已選：{g.players[sel]}。再點另一位互換，或再點一次自己取消。")


@st.dialog("統計／結算")
def settle_dialog(v: int):
    g: Game = ss["game"]
    scope = st.radio("範圍", list(DISPLAY_MODES), horizontal=True, key=f"st_scope_{v}")
    jiang = None if scope == DISPLAY_MODES[0] else g.jiang
    if jiang is not None:
        st.caption(f"第 {g.jiang} 將")
    scores = g.scope_scores(jiang)
    stats = g.stats(jiang)
    for i in range(4):
        r = stats[i]
        st.markdown(f"**{md_escape(g.players[i])}**　{colored(scores[i])}　"
                    f"（摸 {r['zimo']}　胡 {r['ron']}　槍 {r['discard']}）")
    st.markdown("**結算（最少轉帳）**")
    transfers = settlement(scores)
    if not transfers:
        st.caption("目前沒有需要轉帳的款項。")
    for payer, payee, amt in transfers:
        st.markdown(f"- {md_escape(g.players[payer])} → {md_escape(g.players[payee])}：**{amt:,}**")
    if sum(scores) != 0:
        st.warning(f"各家積分加總為 {sum(scores):+,}，不為 0（可能手動調整過），差額無法轉帳。")
    st.divider()
    st.caption("結束牌局會把這局收進「牌局紀錄」，之後仍可從那裡繼續。")
    sure = st.checkbox("我確定要結束這局", key=f"end_ok_{v}")
    if st.button("結束牌局並歸檔", type="primary", disabled=not sure, key=f"end_btn_{v}"):
        ss["archive"].append(archive_entry(g))
        ss["game"] = None
        ss["swap_sel"] = None
        flash("success", f"牌局 {g.no} 已結束並收進「牌局紀錄」。")
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
tab_game, tab_hist, tab_stats, tab_settings = st.tabs(
    ["🀄 目前牌局", "📜 牌局紀錄", "📊 數據統計", "⚙️ 設定"])

# 先執行設定分頁，讓牌局分頁一定讀到最新設定
with tab_settings:
    st.subheader("玩家名單")
    st.text_area("每行一位玩家（也可用逗號分隔）", key="roster_text", height=140,
                 placeholder="小明\n小華\n阿美\n阿強")
    roster = parse_roster(ss["roster_text"])
    st.caption(f"目前共 {len(roster)} 位。開新牌局時可從折疊選單選擇。")

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
                disabled=not ss["draw_keep_dealer"])
    bonus_example = [rules.dealer_tai + n * rules.streak_tai for n in range(0, 4)]
    st.caption("目前莊家加成台數：莊家 0 連 / 1 連 / 2 連 / 3 連 → "
               + " / ".join(f"{t} 台" for t in bonus_example))

    st.subheader("台數表")
    st.caption("可直接修改台數、新增或刪除列（表格左下角的 + 可新增）。"
               "各地台數略有差異，請依你們的規則調整。")
    edited = st.data_editor(
        ss["tai_base"], num_rows="dynamic", hide_index=True, key="tai_editor",
        column_config={
            "名稱": st.column_config.TextColumn(required=True),
            "台數": st.column_config.NumberColumn(min_value=0, step=1, required=True),
            "說明": st.column_config.TextColumn(),
        },
    )
    ss["tai_current"] = edited
    st.button("還原預設台數表", on_click=reset_tai_table)

    st.subheader("備份與還原")
    st.caption("全部資料備份包含：玩家名單、規則、台數表、進行中牌局與過去牌局。"
               "換手機、重新部署或沒有設定雲端存檔時，用它就能把設定和各局數據帶走。")
    st.download_button("下載全部資料備份 (JSON)", backup_bytes(),
                       f"mahjong_backup_{today_str()}.json", "application/json")
    st.file_uploader("選擇全部資料備份檔", type="json", key="backup_upload")
    backup_ok = st.checkbox("我知道這會覆蓋目前所有資料", key="backup_ok")
    st.button("還原全部備份", on_click=load_backup, disabled=not backup_ok)

    st.subheader("單一牌局存檔")
    cur_game = ss["game"]
    if cur_game is not None:
        st.download_button("下載目前牌局存檔 (JSON)", cur_game.to_json().encode("utf-8"),
                           f"mahjong_game_{cur_game.no}.json", "application/json")
    st.file_uploader("載入先前下載的單一牌局 JSON", type="json", key="upload")
    st.button("載入", on_click=load_game)

tai_table = tai_table_from_df(ss["tai_current"])

# ------------------------------------------------------------------ 目前牌局
with tab_game:
    fl = ss.get("flash")
    if fl:
        getattr(st, fl[0])(fl[1])
        ss["flash"] = None

    g = ss["game"]

    if g is None:
        st.subheader("🀄 台灣麻將計台器")
        if len(roster) < 4:
            st.info("先到「設定」分頁新增至少 4 位玩家名稱，開局時就能用折疊選單選人。")
        if st.button("➕ 開始新牌局", type="primary"):
            new_game_dialog(roster)
        if ss["archive"]:
            st.caption("之前結束的牌局在「牌局紀錄」，可以從那裡繼續。")
    else:
        g.rules = rules  # 設定的修改會套用在之後的牌局
        rot = ss["view_rot"]
        scope = None if ss["display_mode"] == DISPLAY_MODES[0] else g.jiang
        scores = g.scope_scores(scope)
        stats = g.stats(scope)

        st.markdown(
            f"<div class='game-header'><div class='gh-title'>牌局 {g.no}</div>"
            f"<div class='gh-sub'>第 {g.jiang} 將　{g.round_label()}（第 {g.hand_no} 局）</div></div>",
            unsafe_allow_html=True)

        # ---- 工具列
        with st.container(key="toolbar"):
            tb = st.columns(5)
            with tb[0]:
                st.button("↩️\n復原操作", key="tb_undo", on_click=do_undo,
                          disabled=not g.history)
            with tb[1]:
                st.button("✏️\n調整分數", key="tb_adjust", on_click=request_dialog, args=("adjust",))
            with tb[2]:
                st.button("🧮\n統計/結算", key="tb_settle", on_click=request_dialog, args=("settle",))
            with tb[3]:
                st.button("🔄\n旋轉視角", key="tb_rotate", on_click=rotate_view)
            with tb[4]:
                st.button("🔀\n調整位置", key="tb_seat", on_click=request_dialog, args=("seat",))
        st.divider()

        # ---- 十字座位
        def board_cell(pos):
            i = (pos + rot) % 4
            is_dealer = i == g.dealer
            head = ("🔴莊 " if is_dealer else "") + md_escape(g.players[i])
            if is_dealer and g.streak:
                head += f" 連{g.streak}"
            s = scores[i]
            val = money(s)
            big = f"**:green[{val}]**" if s > 0 else (f"**:red[{val}]**" if s < 0 else f"**{val}**")
            r = stats[i]
            label = f"{head}\n{big}\n摸 {r['zimo']}　胡 {r['ron']}　槍 {r['discard']}"
            st.button(label, key=f"seat_{pos}_{'dealer' if is_dealer else 'p'}",
                      on_click=select_player, args=(i,))

        def board_center():
            st.markdown(f"<div class='wind-box'>{WINDS[g.wind_round]}</div>"
                        f"<div class='wind-sub'>加成 {g.dealer_bonus_tai()} 台</div>",
                        unsafe_allow_html=True)
            st.button("流局", key="btn_draw", on_click=do_draw)

        def board_corner():
            st.button(f"顯示模式\n{ss['display_mode']}", key="btn_mode", on_click=toggle_mode,
                      help="切換顯示「累計」或「本將」的積分與戰績")

        seat_cross(board_cell, board_center, key="seat_board", bottom_left=board_corner)
        if rules.draw_keep_dealer:
            draw_note = "莊家連莊 +1" if rules.draw_count_streak else "莊家續莊、連莊數不變"
        else:
            draw_note = "換下一位做莊"
        st.caption(f"👆 點選玩家記錄自摸／胡牌。流局：{draw_note}。"
                   f"顯示：{ss['display_mode']}（摸＝自摸、胡＝胡牌、槍＝放槍）")

        # ---- 對話視窗（在版面容器之外開啟）
        pw = ss.pop("pending_winner", None)
        if pw is not None:
            ss["dlg_v"] += 1
            win_dialog(pw, ss["dlg_v"], tai_table)
        which = ss.pop("open_dialog", None)
        if which in ("adjust", "settle", "seat"):
            ss["dlg_v"] += 1
            {"adjust": adjust_dialog, "settle": settle_dialog, "seat": seat_dialog}[which](ss["dlg_v"])

# ------------------------------------------------------------------ 牌局紀錄
with tab_hist:
    g = ss["game"]
    if g is not None:
        st.subheader(f"牌局 {g.no}（進行中）")
        rows = g.history_rows()
        if rows:
            with st.container(height=420, border=True):
                for r in reversed(rows):
                    streak = f"　連{r['連莊']}" if r["連莊"] else ""
                    deltas = "　".join(f"{md_escape(n)} {colored(r[n])}" for n in g.players)
                    st.markdown(f"**第 {r['把']} 局｜{r['局']}｜莊 {md_escape(r['莊家'])}{streak}**  \n"
                                f"{r['結果']}  \n{deltas}")
                    st.divider()
            hist_df = pd.DataFrame(rows)
            st.download_button("下載每把紀錄 CSV", hist_df.to_csv(index=False).encode("utf-8-sig"),
                               f"mahjong_history_{g.no}.csv", "text/csv")
        else:
            st.caption("還沒有任何紀錄。")

    st.subheader("過去牌局")
    archive = ss["archive"]
    if not archive:
        st.caption("還沒有結束的牌局。在「統計/結算」按「結束牌局並歸檔」後會出現在這裡。")
    for idx in reversed(range(len(archive))):
        e = archive[idx]
        with st.expander(f"牌局 {e.get('no', '?')}｜{e.get('created', '')}｜{e.get('hands', 0)} 局"):
            try:
                ag = Game.from_json(e["game"])
            except Exception:
                st.error("這局的資料損毀。")
                ag = None
            if ag is not None:
                st.dataframe(stats_frame(ag, None), hide_index=True)
                st.caption(f"結束於 {e.get('ended', '')}")
            c1, c2 = st.columns(2)
            with c1:
                st.button("繼續這局", key=f"arc_resume_{idx}", on_click=resume_archived,
                          args=(idx,), disabled=ss["game"] is not None or ag is None,
                          help="要先結束目前進行中的牌局")
            with c2:
                ok = st.checkbox("確認刪除", key=f"arc_del_ok_{idx}")
            st.button("刪除這局", key=f"arc_del_{idx}", on_click=delete_archived,
                      args=(idx,), disabled=not ok)

# ------------------------------------------------------------------ 數據統計
with tab_stats:
    g = ss["game"]
    if g is None:
        st.info("尚未開始牌局。開始後，這裡會顯示每位玩家的自摸、胡牌、放槍次數與金額。")
    else:
        scope_name = st.radio("範圍", list(DISPLAY_MODES), horizontal=True, key="stats_scope")
        jiang = None if scope_name == DISPLAY_MODES[0] else g.jiang
        stats = g.stats(jiang)
        scores = g.scope_scores(jiang)
        hands = g.hands_played(jiang)
        st.caption(f"牌局 {g.no}" + ("" if jiang is None else f"　第 {g.jiang} 將") + f"　共 {hands} 局")
        st.dataframe(stats_frame(g, jiang), hide_index=True)
        st.caption("自摸＝自己摸牌胡；胡牌＝別人放槍給你胡；放槍＝你放槍給別人胡。")

        for i in range(4):
            r = stats[i]
            with st.container(border=True):
                st.markdown(f"**{md_escape(g.players[i])}**　淨額 {colored(scores[i])}")
                lines = [
                    f"- 自摸 {r['zimo']} 次，共贏 {money(r['zimo_amt'])}",
                    f"- 胡牌 {r['ron']} 次，共贏 {money(r['ron_amt'])}",
                    f"- 放槍 {r['discard']} 次，共輸 {money(r['discard_amt'])}",
                    f"- 被自摸 {r['zimo_paid']} 次，共輸 {money(r['zimo_paid_amt'])}",
                ]
                if r["adjust"]:
                    lines.append(f"- 手動調整 {money(r['adjust'], True)}")
                if hands:
                    lines.append(f"- 胡牌率 {r['wins'] / hands:.0%}　放槍率 {r['discard'] / hands:.0%}")
                st.markdown("\n".join(lines))

        trend = g.trend(jiang)
        if len(trend) > 1:
            st.subheader("積分走勢")
            st.line_chart(pd.DataFrame(trend, columns=g.players))

# ------------------------------------------------------------------ 雲端自動存檔（放在最後，涵蓋本次所有變動）
autosave(store, status, store_error)
