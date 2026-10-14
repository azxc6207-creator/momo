"""台灣麻將（16 張）計台、連莊、金額結算核心邏輯。

與介面（Streamlit）完全分離，方便測試與日後改成其他介面。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

WINDS = ["東", "南", "西", "北"]

# 台型名稱中有特殊處理邏輯的幾項
ZIMO = "自摸"
MENQING = "門清"
BUQIUREN = "不求人"
QUANQIU = "全求人"

# 預設台數表（各地規則略有差異，可在介面中自行修改、新增）
DEFAULT_TAI_TABLE = [
    {"名稱": "門清", "台數": 1, "說明": "無吃碰明槓（暗槓可），放槍胡"},
    {"名稱": "自摸", "台數": 1, "說明": "自摸時自動加入，不需勾選"},
    {"名稱": "不求人", "台數": 3, "說明": "門清且自摸，已含門清與自摸，勿重複勾選"},
    {"名稱": "全求人", "台數": 2, "說明": "吃碰槓全靠別人打出，單吊放槍"},
    {"名稱": "平胡", "台數": 2, "說明": "全順子、無字無花（對自摸是否可算各地不同）"},
    {"名稱": "獨聽", "台數": 1, "說明": "邊張、嵌張或單吊"},
    {"名稱": "搶槓胡", "台數": 1, "說明": ""},
    {"名稱": "槓上開花", "台數": 1, "說明": ""},
    {"名稱": "海底撈月", "台數": 1, "說明": "最後一張自摸"},
    {"名稱": "河底撈魚", "台數": 1, "說明": "最後一張放槍"},
    {"名稱": "紅中刻", "台數": 1, "說明": ""},
    {"名稱": "青發刻", "台數": 1, "說明": ""},
    {"名稱": "白板刻", "台數": 1, "說明": ""},
    {"名稱": "圈風", "台數": 1, "說明": "圈風刻子"},
    {"名稱": "門風", "台數": 1, "說明": "自己門風刻子"},
    {"名稱": "碰碰胡", "台數": 4, "說明": ""},
    {"名稱": "混一色", "台數": 4, "說明": ""},
    {"名稱": "清一色", "台數": 8, "說明": ""},
    {"名稱": "三暗刻", "台數": 2, "說明": ""},
    {"名稱": "四暗刻", "台數": 5, "說明": ""},
    {"名稱": "五暗刻", "台數": 8, "說明": ""},
    {"名稱": "小三元", "台數": 4, "說明": ""},
    {"名稱": "大三元", "台數": 8, "說明": ""},
    {"名稱": "小四喜", "台數": 8, "說明": ""},
    {"名稱": "大四喜", "台數": 16, "說明": ""},
    {"名稱": "字一色", "台數": 16, "說明": ""},
    {"名稱": "花槓", "台數": 2, "說明": "春夏秋冬或梅蘭竹菊湊齊"},
    {"名稱": "八仙過海", "台數": 8, "說明": ""},
    {"名稱": "七搶一", "台數": 8, "說明": ""},
    {"名稱": "人胡", "台數": 8, "說明": ""},
    {"名稱": "地胡", "台數": 16, "說明": ""},
    {"名稱": "天胡", "台數": 24, "說明": ""},
]


@dataclass
class Rules:
    base: int = 100               # 底（元）
    tai_value: int = 20           # 每一台（元）
    dealer_tai: int = 1           # 莊家身分台數
    streak_tai: int = 2           # 每一次連莊加的台數（2 = 連 n 拉 n，即 n + n）
    streak_cap: int = 0           # 連莊最多計到幾次，0 = 不設上限
    draw_keep_dealer: bool = True   # 流局是否由原莊家繼續做莊
    draw_count_streak: bool = True  # 流局是否累計連莊數


def compute_hand_tai(table: dict[str, int], selected: list[str], kind: str,
                     extra: int = 0) -> tuple[int, list[tuple[str, int]]]:
    """計算牌型台數（不含莊家與連莊）。回傳 (總台數, 明細)。"""
    sel = [s for s in selected if s in table]
    if kind == "自摸":
        if BUQIUREN in sel:
            # 不求人已含門清與自摸
            sel = [s for s in sel if s not in (MENQING, ZIMO)]
        elif ZIMO in table and ZIMO not in sel:
            sel = [ZIMO] + sel
    else:
        sel = [s for s in sel if s not in (ZIMO, BUQIUREN)]
    breakdown = [(s, int(table[s])) for s in sel]
    if extra:
        breakdown.append(("額外台數", int(extra)))
    return sum(t for _, t in breakdown), breakdown


def check_conflicts(selected: list[str], kind: str) -> list[str]:
    """回傳提示訊息（不阻擋登記，僅提醒）。"""
    msgs = []
    if kind == "放槍" and BUQIUREN in selected:
        msgs.append("不求人必須自摸，放槍時此項不計。")
    if kind == "自摸" and QUANQIU in selected:
        msgs.append("全求人通常為放槍胡，自摸時請確認是否要計。")
    if BUQIUREN in selected and MENQING in selected:
        msgs.append("不求人已含門清與自摸，門清不重複計算。")
    return msgs


@dataclass
class Game:
    players: list
    rules: Rules = field(default_factory=Rules)
    dealer: int = 0
    streak: int = 0
    wind_round: int = 0     # 圈風：0 東 … 3 北
    dealer_turns: int = 0   # 本圈已輪過幾位莊家：0~3（亦即第幾局）
    hand_no: int = 1
    scores: list = None
    history: list = field(default_factory=list)

    def __post_init__(self):
        if len(self.players) != 4:
            raise ValueError("需要 4 位玩家")
        if self.scores is None:
            self.scores = [0, 0, 0, 0]

    # ---------- 狀態 ----------
    def seat_wind(self, i: int) -> str:
        """門風：莊家為東，依序往下家排。"""
        return WINDS[(i - self.dealer) % 4]

    def round_label(self) -> str:
        return f"{WINDS[self.wind_round]}風{WINDS[self.dealer_turns]}局"

    def effective_streak(self) -> int:
        cap = self.rules.streak_cap
        return min(self.streak, cap) if cap and cap > 0 else self.streak

    def dealer_bonus_tai(self) -> int:
        return self.rules.dealer_tai + self.effective_streak() * self.rules.streak_tai

    # ---------- 結算 ----------
    def calc_win(self, winner: int, kind: str, hand_tai: int,
                 discarder: int | None = None) -> dict:
        if kind == "自摸":
            payers = [i for i in range(4) if i != winner]
        elif kind == "放槍":
            if discarder is None or discarder == winner:
                raise ValueError("放槍需指定放槍者，且不能是胡牌者")
            payers = [discarder]
        else:
            raise ValueError("kind 必須是 自摸 或 放槍")

        payments = []
        for p in payers:
            involved = self.dealer in (winner, p)
            tai = hand_tai + (self.dealer_bonus_tai() if involved else 0)
            amount = self.rules.base + tai * self.rules.tai_value
            payments.append({"payer": p, "tai": tai, "amount": amount,
                             "dealer_involved": involved})
        deltas = [0, 0, 0, 0]
        for pay in payments:
            deltas[pay["payer"]] -= pay["amount"]
            deltas[winner] += pay["amount"]
        return {"payments": payments, "deltas": deltas}

    # ---------- 換莊 ----------
    def _rotate(self):
        self.dealer = (self.dealer + 1) % 4
        self.streak = 0
        self.dealer_turns += 1
        if self.dealer_turns >= 4:
            self.dealer_turns = 0
            self.wind_round = (self.wind_round + 1) % 4

    def _snapshot(self) -> dict:
        return {"dealer": self.dealer, "streak": self.streak,
                "wind_round": self.wind_round,
                "dealer_turns": self.dealer_turns, "hand_no": self.hand_no}

    # ---------- 登記 ----------
    def apply_win(self, winner: int, kind: str, hand_tai: int,
                  discarder: int | None = None, items: list | None = None) -> dict:
        result = self.calc_win(winner, kind, hand_tai, discarder)
        entry = {
            "type": "win", "hand_no": self.hand_no, "label": self.round_label(),
            "dealer": self.dealer, "streak": self.streak,
            "winner": winner, "kind": kind, "discarder": discarder,
            "hand_tai": hand_tai, "items": items or [],
            "payments": result["payments"], "deltas": result["deltas"],
            "before": self._snapshot(),
        }
        for i in range(4):
            self.scores[i] += result["deltas"][i]
        if winner == self.dealer:
            self.streak += 1
        else:
            self._rotate()
        self.hand_no += 1
        self.history.append(entry)
        return entry

    def apply_draw(self) -> dict:
        entry = {
            "type": "draw", "hand_no": self.hand_no, "label": self.round_label(),
            "dealer": self.dealer, "streak": self.streak,
            "deltas": [0, 0, 0, 0], "before": self._snapshot(),
        }
        if self.rules.draw_keep_dealer:
            if self.rules.draw_count_streak:
                self.streak += 1
        else:
            self._rotate()
        self.hand_no += 1
        self.history.append(entry)
        return entry

    def undo(self) -> bool:
        if not self.history:
            return False
        entry = self.history.pop()
        for i in range(4):
            self.scores[i] -= entry["deltas"][i]
        b = entry["before"]
        self.dealer, self.streak = b["dealer"], b["streak"]
        self.wind_round, self.dealer_turns = b["wind_round"], b["dealer_turns"]
        self.hand_no = b["hand_no"]
        return True

    # ---------- 存讀檔 ----------
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Game":
        d = json.loads(text)
        rules = Rules(**d.pop("rules"))
        return cls(rules=rules, **d)
