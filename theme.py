"""介面主題：麻將綠底圖 + 米白色按鈕、金色數字、深綠色半透明資訊卡。

只負責產生 CSS 與配色常數，不依賴 streamlit，方便單獨測試。
背景圖放在 assets/bg_phone.jpg（手機比例，約 0.46），以 base64 內嵌在 CSS，
不需要開啟 Streamlit 的靜態檔案服務。
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from string import Template

BG_FILE = Path(__file__).parent / "assets" / "bg_phone.jpg"

# ---- 配色 ---------------------------------------------------------------
BASE_GREEN = "#0a4a27"      # 背景圖載入前、以及寬螢幕兩側的底色
CREAM = "#f6efdc"           # 按鈕（米白）
CREAM_TEXT = "#f4eddc"      # 深色底上的文字
CAPTION_TEXT = "#e6f2e6"    # 說明小字
INK = "#1c4a2c"             # 米白按鈕上的深綠文字
GOLD = "#f0cf6e"            # 數字
GOLD_DEEP = "#d9b24c"       # 邊框與強調
ON_GOLD = "#1b3d12"         # 金色底上的文字
CARD_RGB = (5, 38, 20)      # 深綠色資訊卡
CARD_ALPHA = 0.80
CHART_COLORS = [GOLD, "#f4eddc", "#8fd694", "#ff9d8a"]   # 走勢圖：四位玩家各一色

BG_FALLBACK = "linear-gradient(180deg, #06381d 0%, #0d6b38 55%, #06381d 100%)"


@lru_cache(maxsize=1)
def bg_data_uri() -> str:
    """背景圖的 data URI；檔案不存在時回傳空字串（改用純色漸層）。"""
    try:
        raw = BG_FILE.read_bytes()
    except OSError:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def num_html(text: str) -> str:
    """金色數字（要搭配 unsafe_allow_html=True 的 markdown 使用）。"""
    return f"<span class='num'>{text}</span>"


_CSS = Template("""
<style>
/* ===================== 背景 ===================== */
.stApp { background-color: $base !important; }
.stApp::before {
    content: ""; position: fixed; top: 0; left: 0; width: 100%;
    height: 100vh; height: 100lvh;
    z-index: 0; pointer-events: none;
    $bg_layer
}
/* 寬螢幕（平板橫放、電腦）：整張圖依高度縮放並置中，兩側用底色補滿 */
@media (min-aspect-ratio: 3/5) {
    .stApp::before { background-size: auto 100% !important; background-position: center top !important; }
}
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {
    background: transparent !important;
}
[data-testid="stAppViewContainer"] { position: relative; z-index: 1; }

/* 內容欄寬：窄一點，維持在背景圖的金色邊框之內 */
.block-container, [data-testid="stMainBlockContainer"] {
    max-width: 460px !important;
    padding: 3.2rem 1rem 6rem !important;
}
@media (min-aspect-ratio: 3/5) {
    .block-container, [data-testid="stMainBlockContainer"] {
        max-width: max(340px, min(460px, calc(45.85vh - 1.5rem))) !important;
    }
}

/* ===================== 文字 ===================== */
html, body, .stApp { color: $cream_text; }
h1, h2, h3, h4, .stMarkdown, [data-testid="stCaptionContainer"] { text-shadow: 0 1px 3px rgba(0, 0, 0, 0.45); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: $caption_text !important; opacity: 1 !important; }
.num { color: $gold; font-weight: 700; }
/* 沒有放進卡片的文字（說明、標題、單選）：加深色半透明底，避免壓在背景的米白色麻將牌上看不清楚 */
[data-testid="stCaptionContainer"]:not([data-testid="stExpander"] *):not(div[role="dialog"] *),
.stTabs h2:not([data-testid="stExpander"] *), .stTabs h3:not([data-testid="stExpander"] *),
[data-testid="stRadio"]:not([data-testid="stExpander"] *):not(div[role="dialog"] *) {
    background: rgba($card_rgb, 0.62); border-radius: 10px; padding: 0.3rem 0.6rem;
}
.app-title {
    text-align: center; font-size: 1.5rem; font-weight: 800; letter-spacing: 0.12em;
    color: $gold; margin: 0 0 0.5rem; text-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
}

/* ===================== 版面：手機也維持橫向並排 ===================== */
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

/* ===================== 米白色按鈕 ===================== */
.stButton button, .stDownloadButton button, .stLinkButton a {
    width: 100%; min-height: 2.75rem;
    background: $cream !important; color: $ink !important;
    border: 1.5px solid $gold_deep !important; border-radius: 12px !important;
    box-shadow: 0 2px 0 rgba(0, 0, 0, 0.25);
    transition: transform 0.14s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.14s ease !important;
    -webkit-tap-highlight-color: transparent;
    touch-action: manipulation;
    will-change: transform;
}
[data-testid="stFileUploader"] button {
    background: $cream !important; color: $ink !important;
    border: 1.5px solid $gold_deep !important; border-radius: 12px !important;
}
.stButton button *, .stDownloadButton button *, .stLinkButton a *,
[data-testid="stFileUploader"] button * { color: $ink !important; }
.stButton button:hover:not(:disabled), .stDownloadButton button:hover:not(:disabled),
.stLinkButton a:hover { background: #fffaf0 !important; border-color: $gold !important; }
.stButton button:disabled, .stDownloadButton button:disabled { opacity: 0.5 !important; }

/* 主要動作（確認登記、開始…）：金色底 */
.stButton button[kind="primary"], .stButton button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(180deg, #f6dc87, $gold_deep) !important;
    border-color: #fff3c4 !important; font-weight: 800;
}
.stButton button[kind="primary"] *, .stButton button[data-testid="stBaseButton-primary"] * {
    color: $on_gold !important;
}

/* 點擊縮放：按下去縮小一點，放開時回彈 */
.stButton button:active, .stDownloadButton button:active { transform: scale(0.94) !important; }
.st-key-seat_board .stButton button:active {
    transform: scale(0.95) !important; box-shadow: inset 0 0 0 2px rgba(240, 207, 110, 0.5) !important;
}
.st-key-toolbar .stButton button:active { transform: scale(0.9) !important; }
.st-key-seat_board .st-key-btn_mode .stButton button:active { transform: scale(0.9) !important; }
@media (prefers-reduced-motion: reduce) {
    .stButton button, .stDownloadButton button { transition: none !important; }
}

/* 折疊式選單的選項（pills） */
button[data-testid="stBaseButton-pills"] {
    background: rgba(4, 30, 16, 0.6) !important; border: 1px solid rgba(246, 239, 220, 0.55) !important;
    min-height: 2.5rem;
}
button[data-testid="stBaseButton-pills"] * { color: $cream_text !important; }
button[data-testid="stBaseButton-pillsActive"] { background: $gold !important; border-color: $gold !important; min-height: 2.5rem; }
button[data-testid="stBaseButton-pillsActive"] * { color: $on_gold !important; font-weight: 700; }

/* ===================== 深綠色半透明資訊卡 ===================== */
.game-header {
    background: rgba($card_rgb, $card_a); color: $cream_text;
    border: 1.5px solid rgba(217, 178, 76, 0.7); border-radius: 14px;
    padding: 0.65rem 0.8rem; text-align: center; margin-bottom: 0.6rem;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
}
.gh-title { font-size: 1.5rem; font-weight: 800; line-height: 1.25; color: $gold; }
.gh-sub { font-size: 0.92rem; }
[class*="st-key-card_"] {
    background: rgba($card_rgb, $card_a); border: 1px solid rgba(217, 178, 76, 0.45);
    border-radius: 12px; padding: 0.6rem 0.75rem; margin-bottom: 0.5rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}
[data-testid="stExpander"] details {
    background: rgba($card_rgb, $card_a2) !important; border: 1px solid rgba(217, 178, 76, 0.45) !important;
    border-radius: 12px !important;
}
[data-testid="stExpander"] summary { color: $cream_text; }
[data-testid="stExpander"] summary p { color: $cream_text !important; font-weight: 700; }
[data-testid="stExpander"] summary svg { color: $gold; }
[data-testid="stDataFrame"] { border: 1px solid rgba(217, 178, 76, 0.45); border-radius: 10px; overflow: hidden; }
div[role="dialog"] { border: 1px solid rgba(217, 178, 76, 0.6); border-radius: 14px; }

/* 分頁列：平均分配寬度 */
.stTabs [data-baseweb="tab-list"] {
    gap: 0; background: rgba($card_rgb, 0.72); border: 1px solid rgba(217, 178, 76, 0.35);
    border-radius: 12px; padding: 0 0.25rem;
}
.stTabs [data-baseweb="tab"] { flex: 1; justify-content: center; padding: 0.5rem 0.2rem; }
.stTabs [data-baseweb="tab"] p { color: $cream_text; font-weight: 700; }
.stTabs [aria-selected="true"] p { color: $gold; }
.stTabs [data-baseweb="tab-highlight"] { background-color: $gold !important; }
.stTabs [data-baseweb="tab-border"] { background-color: transparent !important; }

/* ===================== 工具列（米白按鈕） ===================== */
.st-key-toolbar button { min-height: 4rem; padding: 0.2rem 0.1rem; }
.st-key-toolbar button p { white-space: pre-line; font-size: 0.74rem; line-height: 1.35; font-weight: 700; }

/* ===================== 座位卡片：深綠半透明＋金色數字 ===================== */
.st-key-seat_board .stButton button {
    min-height: 5.4rem; padding: 0.3rem 0.2rem;
    background: rgba($card_rgb, $card_a) !important;
    border: 1.5px solid rgba(217, 178, 76, 0.5) !important; border-radius: 12px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
.st-key-seat_board .stButton button * { color: $cream_text !important; }
.st-key-seat_board .stButton button p {
    white-space: pre-line; line-height: 1.35; font-size: 0.78rem; overflow-wrap: anywhere;
}
.st-key-seat_board .stButton button strong { color: $gold !important; font-size: 1.5rem; }
.st-key-seat_board [class*="_dealer"] .stButton button {
    border: 2.5px solid $gold !important; background: rgba(34, 58, 12, 0.88) !important;
    box-shadow: 0 0 12px rgba(240, 207, 110, 0.45);
}
/* 中央的「流局」與左下角的「顯示模式」維持米白色按鈕 */
.st-key-seat_board .st-key-btn_draw .stButton button {
    background: $cream !important; border: 1.5px solid $gold_deep !important; min-height: 4.2rem;
}
.st-key-seat_board .st-key-btn_draw .stButton button * { color: $ink !important; font-weight: 700; }
.st-key-seat_board .st-key-btn_mode .stButton button {
    background: $cream !important; border: 3px solid $gold_deep !important;
    border-radius: 50% !important; aspect-ratio: 1 / 1; min-height: 0; padding: 0.1rem;
    width: 4.8rem; max-width: 100%; margin: 0 auto; display: block;
}
.st-key-seat_board .st-key-btn_mode .stButton button * { color: $ink !important; font-weight: 700; }
.st-key-seat_board .st-key-btn_mode button p { font-size: 0.7rem; }
.wind-box {
    background: rgba($card_rgb, 0.9); color: $gold; border: 2px solid $gold_deep;
    border-radius: 10px; font-size: 2rem; font-weight: 800; text-align: center;
    padding: 0.3rem 0; line-height: 1.3; margin-bottom: 0.3rem;
}
@media (max-width: 360px) {
    .st-key-seat_board .stButton button p { font-size: 0.68rem; }
    .st-key-seat_board .stButton button strong { font-size: 1.3rem; }
    .stTabs [data-baseweb="tab"] p { font-size: 0.7rem; }
    .st-key-toolbar button p { font-size: 0.66rem; }
}
.wind-sub { text-align: center; font-size: 0.72rem; color: $caption_text; margin-bottom: 0.3rem; }
</style>
""")


def build_css(with_image: bool = True) -> str:
    """回傳要放進 st.markdown(unsafe_allow_html=True) 的完整 <style>。"""
    uri = bg_data_uri() if with_image else ""
    if uri:
        bg_layer = f'background: url("{uri}") center top / cover no-repeat;'
    else:
        bg_layer = f"background: {BG_FALLBACK};"
    return _CSS.substitute(
        base=BASE_GREEN, bg_layer=bg_layer,
        cream=CREAM, cream_text=CREAM_TEXT, caption_text=CAPTION_TEXT, ink=INK,
        gold=GOLD, gold_deep=GOLD_DEEP, on_gold=ON_GOLD,
        card_rgb=", ".join(str(c) for c in CARD_RGB), card_a=CARD_ALPHA, card_a2=0.86)
