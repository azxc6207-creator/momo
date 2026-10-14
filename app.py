"""台灣麻將計台器（Streamlit）。執行：streamlit run app.py"""
from dataclasses import asdict

import pandas as pd
import streamlit as st

from mahjong_core import (BUQIUREN, DEFAULT_TAI_TABLE, WINDS, ZIMO, Game, Rules,
                          check_conflicts, compute_hand_tai)

st.set_page_config(page_title="台灣麻將計台器", page_icon="🀄", layout="centered")

RULE_DEFAULTS = asdict(Rules())


# ------------------------------------------------------------------ 狀態初始化
def init_state():
    for k, v in RULE_DEFAULTS.items():
        st.session_state.setdefault(k, v)
    st.session_state.setdefault("tai_base", pd.DataFrame(DEFAULT_TAI_TABLE))
    st.session_state.setdefault("tai_current", st.session_state["tai_base"])
    st.session_state.setdefault("game", None)
    st.session_state.setdefault("form_v", 0)
    st.session_state.setdefault("flash", None)


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


# ------------------------------------------------------------------ callbacks
def set_preset(base, tai):
    st.session_state["base"] = base
    st.session_state["tai_value"] = tai


def reset_tai_table():
    st.session_state["tai_base"] = pd.DataFrame(DEFAULT_TAI_TABLE)
    st.session_state.pop("tai_editor", None)


def start_game(names, first):
    g = Game(players=names, rules=rules_from_state(), dealer=first)
    st.session_state["game"] = g


def end_game():
    st.session_state["game"] = None
    st.session_state["form_v"] += 1


def load_game():
    up = st.session_state.get("upload")
    if up is None:
        return
    try:
        g = Game.from_json(up.getvalue().decode("utf-8"))
    except Exception:
        st.session_state["flash"] = ("error", "讀檔失敗，請確認是本程式匯出的 JSON。")
        return
    for k, v in asdict(g.rules).items():
        st.session_state[k] = v
    st.session_state["game"] = g
    st.session_state["flash"] = ("success", "已載入牌局。")


init_state()
rules = rules_from_state()
tab_game, tab_settings, tab_history = st.tabs(["🀄 牌局", "⚙️ 設定", "📜 紀錄"])

# ------------------------------------------------------------------ 設定分頁
# 先執行設定分頁，讓牌局分頁一定讀到最新設定
with tab_settings:
    st.subheader("底與台")
    c1, c2 = st.columns(2)
    c1.number_input("底（元）", min_value=0, step=10, key="base")
    c2.number_input("每台（元）", min_value=0, step=5, key="tai_value")
    p1, p2, p3 = st.columns(3)
    p1.button("100 / 20", on_click=set_preset, args=(100, 20), use_container_width=True)
    p2.button("300 / 100", on_click=set_preset, args=(300, 100), use_container_width=True)
    p3.button("50 / 10", on_click=set_preset, args=(50, 10), use_container_width=True)
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
        use_container_width=True, key="tai_editor",
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
    flash = st.session_state.get("flash")
    if flash:
        getattr(st, flash[0])(flash[1])
        st.session_state["flash"] = None

    g: Game = st.session_state["game"]

    if g is None:
        st.subheader("開始新牌局")
        st.caption("玩家請依「東 → 南 → 西 → 北」的輪莊順序輸入（下家即下一位莊家）。")
        with st.form("start_form"):
            defaults = ["玩家1", "玩家2", "玩家3", "玩家4"]
            names = [st.text_input(f"座位 {i + 1}", value=defaults[i]) for i in range(4)]
            first = st.selectbox("起莊", [0, 1, 2, 3], format_func=lambda i: f"座位 {i + 1}")
            ok = st.form_submit_button("開始", type="primary", use_container_width=True)
        if ok:
            clean = [n.strip() or f"玩家{i + 1}" for i, n in enumerate(names)]
            if len(set(clean)) < 4:
                st.error("四位玩家名稱不能重複。")
            else:
                start_game(clean, first)
                st.rerun()
    else:
        g.rules = rules  # 設定的修改會套用在之後的牌局

        # ---- 局況
        st.subheader(f"{g.round_label()}　第 {g.hand_no} 把")
        streak_txt = f"連莊 {g.streak}" if g.streak else "未連莊"
        st.caption(f"莊家：{g.players[g.dealer]}　｜　{streak_txt}　｜　"
                   f"莊家加成 {g.dealer_bonus_tai()} 台")

        for row in (0, 2):
            cols = st.columns(2)
            for j, i in enumerate((row, row + 1)):
                with cols[j]:
                    tag = "🀄莊 " if i == g.dealer else ""
                    st.metric(f"{tag}{g.players[i]}（{g.seat_wind(i)}）",
                              f"{g.scores[i]:+,}")

        st.divider()
        v = st.session_state["form_v"]
        mode = st.radio("本把結果", ["胡牌", "流局"], horizontal=True, key=f"mode_{v}")

        if mode == "胡牌":
            winner = st.selectbox("胡牌者", [0, 1, 2, 3],
                                  format_func=lambda i: g.players[i], key=f"winner_{v}")
            kind = st.radio("方式", ["自摸", "放槍"], horizontal=True, key=f"kind_{v}")
            discarder = None
            if kind == "放槍":
                others = [i for i in range(4) if i != winner]
                discarder = st.selectbox("放槍者", others,
                                         format_func=lambda i: g.players[i],
                                         key=f"discarder_{v}_{winner}")

            choices = [n for n in tai_table if n != ZIMO]
            picked = st.multiselect("牌型台數（可多選，自摸會自動加入）", choices,
                                    key=f"items_{v}")
            extra = st.number_input("額外台數（花牌、花槓、其他）", min_value=0, step=1,
                                    key=f"extra_{v}")

            for m in check_conflicts(picked, kind):
                st.warning(m)

            hand_tai, breakdown = compute_hand_tai(tai_table, picked, kind, extra)
            calc = g.calc_win(winner, kind, hand_tai, discarder)

            detail = "、".join(f"{n} {t}" for n, t in breakdown) or "無"
            st.caption(f"牌型台數 {hand_tai} 台（{detail}）")

            pay_df = pd.DataFrame([{
                "付款人": g.players[p["payer"]],
                "台數": f"{p['tai']}" + (f"（含莊 {g.dealer_bonus_tai()}）"
                                          if p["dealer_involved"] else ""),
                "金額": p["amount"],
            } for p in calc["payments"]])
            st.dataframe(pay_df, hide_index=True, use_container_width=True)
            st.markdown(f"**{g.players[winner]} 共贏 {sum(p['amount'] for p in calc['payments']):,} 元**")

            if st.button("確認登記", type="primary", use_container_width=True):
                items = [n for n, _ in breakdown]
                g.apply_win(winner, kind, hand_tai, discarder, items)
                st.session_state["form_v"] += 1
                st.session_state["flash"] = ("success", "已登記，請看最新局況。")
                st.rerun()
        else:
            if rules.draw_keep_dealer:
                note = ("莊家連莊，連莊數 +1" if rules.draw_count_streak
                        else "莊家繼續做莊，連莊數不變")
            else:
                note = "換下一位做莊"
            st.info(f"流局不計輸贏：{note}。（可在「設定」調整）")
            if st.button("確認流局", type="primary", use_container_width=True):
                g.apply_draw()
                st.session_state["form_v"] += 1
                st.session_state["flash"] = ("success", "已登記流局。")
                st.rerun()

        if st.button("↩︎ 復原上一把", disabled=not g.history, use_container_width=True):
            g.undo()
            st.session_state["form_v"] += 1
            st.rerun()

# ------------------------------------------------------------------ 紀錄分頁
with tab_history:
    g = st.session_state["game"]
    if g is None:
        st.info("尚未開始牌局。也可以在這裡載入之前存的牌局。")
    else:
        st.subheader("目前積分")
        st.dataframe(pd.DataFrame({
            "玩家": g.players,
            "門風": [g.seat_wind(i) for i in range(4)],
            "累計": g.scores,
        }), hide_index=True, use_container_width=True)

        rows = []
        for h in g.history:
            if h["type"] == "win":
                how = ("自摸" if h["kind"] == "自摸"
                       else f"{g.players[h['discarder']]} 放槍")
                result = f"{g.players[h['winner']]} {how}（牌型 {h['hand_tai']} 台）"
            else:
                result = "流局"
            row = {"把": h["hand_no"], "局": h["label"],
                   "莊家": g.players[h["dealer"]], "連莊": h["streak"],
                   "結果": result}
            for i, name in enumerate(g.players):
                row[name] = h["deltas"][i]
            rows.append(row)
        st.subheader("每把紀錄")
        if rows:
            hist_df = pd.DataFrame(rows)
            st.dataframe(hist_df, hide_index=True, use_container_width=True)
            st.download_button("下載紀錄 CSV", hist_df.to_csv(index=False).encode("utf-8-sig"),
                               "mahjong_history.csv", "text/csv", use_container_width=True)
        else:
            st.caption("還沒有任何紀錄。")

        st.subheader("存檔 / 結束")
        st.download_button("下載牌局存檔 (JSON)", g.to_json().encode("utf-8"),
                           "mahjong_game.json", "application/json",
                           use_container_width=True)
        st.button("結束牌局（清除目前資料）", on_click=end_game, use_container_width=True)

    st.subheader("載入存檔")
    st.file_uploader("選擇先前下載的 JSON", type="json", key="upload")
    st.button("載入", on_click=load_game, use_container_width=True)
