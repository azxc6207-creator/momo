from cloud_store import (ARCHIVE_HEADER, ARCHIVE_SHEET, CHUNK, DETAIL_HEADER, DETAIL_SHEET,
                         LOG_SHEET, STATE_SHEET, SheetsStore, archive_tables, connect)
from mahjong_core import Game, Rules


class WorksheetNotFound(Exception):
    pass


class FakeWorksheet:
    """模仿 gspread：寫入的數字讀回來都是字串。"""

    def __init__(self):
        self.rows = []

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def clear(self):
        self.rows = []

    def update(self, values, range_name, raw=True):
        assert range_name == "A1" and raw is True
        self.rows = [[str(c) for c in r] for r in values]


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    def worksheet(self, title):
        if title not in self.sheets:
            raise WorksheetNotFound(title)
        return self.sheets[title]

    def add_worksheet(self, title, rows, cols):
        self.sheets[title] = FakeWorksheet()
        return self.sheets[title]


def test_empty_sheet_loads_empty():
    assert SheetsStore(FakeSpreadsheet()).load_all() == {}


def test_roundtrip_with_long_text_is_chunked():
    store = SheetsStore(FakeSpreadsheet())
    long_text = "麻將" * (CHUNK + 5)          # 超過單格上限，必須分塊
    data = {"game": long_text, "roster": "小明\n小華", "last_game": ""}
    store.save_all(data)
    rows = store.sh.sheets[STATE_SHEET].rows
    assert all(len(r[2]) <= CHUNK for r in rows[1:])
    assert sum(1 for r in rows if r[0] == "game") == 3
    assert store.load_all() == {k: v for k, v in data.items()}


def test_save_replaces_old_keys():
    store = SheetsStore(FakeSpreadsheet())
    store.save_all({"a": "1", "b": "2"})
    store.save_all({"a": "3"})
    assert store.load_all() == {"a": "3"}


def test_log_sheet_has_history_and_totals():
    g = Game(players=["A", "B", "C", "D"], rules=Rules())
    g.apply_win(1, "自摸", 2)
    g.apply_draw()
    store = SheetsStore(FakeSpreadsheet())
    store.save_log(g)
    rows = store.sh.sheets[LOG_SHEET].rows
    assert rows[0] == ["把", "局", "莊家", "連莊", "結果", "A", "B", "C", "D"]
    assert len(rows) == 1 + 2 + 2                      # 表頭 + 2 把 + 空列 + 累計
    assert rows[-1][4] == "累計" and rows[-1][5:] == [str(s) for s in g.scores]
    store.save_log(None)                                # 結束牌局 → 清空
    assert store.sh.sheets[LOG_SHEET].rows == []


def test_game_json_compact_roundtrip():
    g = Game(players=["A", "B", "C", "D"], rules=Rules())
    g.apply_win(2, "放槍", 4, discarder=0, items=["清一色"])
    g2 = Game.from_json(g.to_json(indent=None))
    assert g2.scores == g.scores and g2.history == g.history


def test_connect_without_secrets_is_disabled():
    assert connect({}) is None
    assert connect({"gsheet": {"spreadsheet": "x"}}) is None   # 缺金鑰


def _archived(no, players):
    g = Game(players=players, rules=Rules(), no=no, created="2026-11-17")
    g.apply_win(1, "自摸", 2)
    g.apply_win(2, "放槍", 1, discarder=0)
    g.apply_draw()
    return {"no": no, "created": g.created, "hands": g.hands_played(),
            "players": g.players, "scores": g.scores, "game": g.to_json(indent=None)}, g


def test_archive_tables_shape_and_numbers():
    e1, g1 = _archived(1, ["A", "B", "C", "D"])
    e2, g2 = _archived(2, ["E", "F", "G", "H"])
    per_player, per_hand = archive_tables([e1, e2, {"no": 3, "game": "壞掉的資料"}])
    assert per_player[0] == ARCHIVE_HEADER and per_hand[0] == DETAIL_HEADER
    assert len(per_player) == 1 + 8                      # 損毀的牌局被略過
    assert len(per_hand) == 1 + 3 + 3
    row_b = per_player[2]                                # 牌局 1 的 B
    assert row_b[:4] == [1, "2026-11-17", 3, "B"] and row_b[4] == g1.scores[1]
    assert row_b[5] == 1                                 # B 自摸 1 次
    assert all(len(r) == len(ARCHIVE_HEADER) for r in per_player)
    assert all(len(r) == len(DETAIL_HEADER) for r in per_hand)
    first_hand = per_hand[1]
    assert first_hand[0] == 1 and first_hand[6] == "A" and first_hand[7] == g1.history[0]["deltas"][0]


def test_save_archive_views_writes_and_clears():
    store = SheetsStore(FakeSpreadsheet())
    e1, _ = _archived(1, ["A", "B", "C", "D"])
    store.save_archive_views([e1])
    assert len(store.sh.sheets[ARCHIVE_SHEET].rows) == 5
    assert len(store.sh.sheets[DETAIL_SHEET].rows) == 4
    store.save_archive_views([])                          # 全部刪除 → 兩頁清空
    assert store.sh.sheets[ARCHIVE_SHEET].rows == [] and store.sh.sheets[DETAIL_SHEET].rows == []


def test_sheet_url_from_url_or_id():
    from cloud_store import sheet_url
    url = "https://docs.google.com/spreadsheets/d/abc123/edit"
    assert sheet_url({"gsheet": {"spreadsheet": f"  {url}  "}}) == url
    assert sheet_url({"gsheet": {"spreadsheet": "abc123"}}) == "https://docs.google.com/spreadsheets/d/abc123"
    assert sheet_url({}) == "" and sheet_url({"gsheet": {"spreadsheet": ""}}) == ""

    class Boom(dict):
        def __getitem__(self, k):
            raise FileNotFoundError("no secrets")
    assert sheet_url(Boom()) == ""
