"""Google 試算表雲端存檔（單人記帳用）。

- 「mahjong_state」分頁：app 自動讀寫的資料（牌局、玩家名單、規則、台數表）。
  Google 試算表單一儲存格上限約 5 萬字元，所以長資料會自動切成多列。
- 「牌局紀錄」分頁：給人看的每把輸贏表，每次存檔時重新寫入。
  這一頁只是輸出，在試算表裡修改不會回到 app。
"""
from __future__ import annotations

from mahjong_core import Game

CHUNK = 40000
STATE_SHEET = "mahjong_state"
LOG_SHEET = "牌局紀錄"
STATE_HEADER = ["key", "chunk", "data"]


class SheetsStore:
    """包裝一個 gspread Spreadsheet（也可傳入相同介面的假物件做測試）。"""

    def __init__(self, spreadsheet):
        self.sh = spreadsheet

    def _worksheet(self, title: str):
        try:
            return self.sh.worksheet(title)
        except Exception as e:  # gspread.WorksheetNotFound
            if type(e).__name__ != "WorksheetNotFound":
                raise
            return self.sh.add_worksheet(title=title, rows=200, cols=10)

    def load_all(self) -> dict:
        """讀回 {key: 文字}。分頁不存在或是空的 → 回傳 {}。"""
        values = self._worksheet(STATE_SHEET).get_all_values()
        parts: dict = {}
        for row in values[1:]:
            if len(row) < 2 or not row[0]:
                continue
            chunk = row[2] if len(row) > 2 else ""
            parts.setdefault(row[0], {})[int(row[1])] = chunk
        return {k: "".join(p[i] for i in sorted(p)) for k, p in parts.items()}

    def save_all(self, data: dict) -> None:
        rows = [STATE_HEADER]
        for key, text in data.items():
            text = text or ""
            chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]
            rows.extend([key, n, c] for n, c in enumerate(chunks))
        ws = self._worksheet(STATE_SHEET)
        ws.clear()
        ws.update(values=rows, range_name="A1", raw=True)

    def save_log(self, game: Game | None) -> None:
        """把每把紀錄與目前積分寫到「牌局紀錄」分頁。"""
        ws = self._worksheet(LOG_SHEET)
        ws.clear()
        if game is None:
            return
        header = ["把", "局", "莊家", "連莊", "結果"] + list(game.players)
        rows = [header] + [[r[h] for h in header] for r in game.history_rows()]
        rows.append([])
        rows.append(["", "", "", "", "累計"] + list(game.scores))
        ws.update(values=rows, range_name="A1", raw=True)


def connect(secrets):
    """依 Streamlit Secrets 連到試算表。

    沒有設定 secrets → 回傳 None（表示雲端存檔未啟用）。
    設定了卻連不上（金鑰錯誤、沒共用給服務帳號…）→ 直接丟出例外，讓畫面顯示原因。
    """
    try:
        creds = secrets["gcp_service_account"]
        ref = secrets["gsheet"]["spreadsheet"]
    except Exception:
        return None
    import gspread  # 延後載入：沒啟用雲端時不需要安裝

    client = gspread.service_account_from_dict(dict(creds))
    ref = str(ref).strip()
    sh = client.open_by_url(ref) if ref.startswith("http") else client.open_by_key(ref)
    return SheetsStore(sh)
