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


def settlement(scores: list) -> list:
    """最少轉帳次數的結算：回傳 [(付款人座位, 收款人座位, 金額), ...]。

    贏的人收錢、輸的人付錢，每次都讓目前欠最多的人付給贏最多的人。
    若各家積分加總不為 0（例如手動調整過），多出的差額無法對應，會被忽略。
    """
    creditors = sorted(([i, s] for i, s in enumerate(scores) if s > 0), key=lambda x: -x[1])
    debtors = sorted(([i, -s] for i, s in enumerate(scores) if s < 0), key=lambda x: -x[1])
    out = []
    ci = di = 0
    while ci < len(creditors) and di < len(debtors):
        pay = min(creditors[ci][1], debtors[di][1])
        out.append((debtors[di][0], creditors[ci][0], pay))
        creditors[ci][1] -= pay
        debtors[di][1] -= pay
        if creditors[ci][1] == 0:
            ci += 1
        if debtors[di][1] == 0:
            di += 1
    return out


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
    no: int = 1             # 牌局編號
    created: str = ""       # 建立日期（YYYY-MM-DD）
    jiang: int = 1          # 第幾將：北圈結束、回到東圈時進入下一將

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
        """例：西圈南風（圈風西，第二位莊家）。"""
        return f"{WINDS[self.wind_round]}圈{WINDS[self.dealer_turns]}風"

    def effective_streak(self) -> int:
        cap = self.rules.streak_cap
        return min(self.streak, cap) if cap and cap > 0 else self.streak

    def dealer_bonus_tai(self) -> int:
        return self.rules.dealer_tai + self.effective_streak() * self.rules.streak_tai

    # ---------- 結算 ----------
    def calc_win(self, winner: int, kind: str, hand_tai: int,
                 discarder: int | None = None,
                 amount_override: dict | None = None) -> dict:
        """計算一把的各家應付金額。

        amount_override: {付款人座位: 手動金額}，只會取代該付款人的金額，
        台數仍照規則計算（僅供紀錄參考）。
        """
        override = {int(k): int(v) for k, v in (amount_override or {}).items()}
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
            manual = p in override
            if manual:
                if override[p] < 0:
                    raise ValueError("手動金額不能是負數")
                amount = override[p]
            payments.append({"payer": p, "tai": tai, "amount": amount,
                             "dealer_involved": involved, "manual": manual})
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
            if self.wind_round == 0:
                self.jiang += 1

    def _snapshot(self) -> dict:
        return {"dealer": self.dealer, "streak": self.streak,
                "wind_round": self.wind_round,
                "dealer_turns": self.dealer_turns, "hand_no": self.hand_no,
                "jiang": self.jiang}

    # ---------- 登記 ----------
    def apply_win(self, winner: int, kind: str, hand_tai: int,
                  discarder: int | None = None, items: list | None = None,
                  amount_override: dict | None = None) -> dict:
        result = self.calc_win(winner, kind, hand_tai, discarder, amount_override)
        entry = {
            "type": "win", "hand_no": self.hand_no, "label": self.round_label(),
            "jiang": self.jiang, "dealer": self.dealer, "streak": self.streak,
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
            "jiang": self.jiang, "dealer": self.dealer, "streak": self.streak,
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

    def apply_adjust(self, deltas: list, note: str = "") -> dict:
        """手動調整積分（不影響莊家、連莊與局數，可用「復原」取消）。"""
        deltas = [int(x) for x in deltas]
        if len(deltas) != 4:
            raise ValueError("需要 4 位玩家的調整值")
        if not any(deltas):
            raise ValueError("調整值全為 0")
        entry = {
            "type": "adjust", "hand_no": self.hand_no, "label": self.round_label(),
            "jiang": self.jiang, "dealer": self.dealer, "streak": self.streak,
            "deltas": deltas, "note": note, "before": self._snapshot(),
        }
        for i in range(4):
            self.scores[i] += deltas[i]
        self.history.append(entry)
        return entry

    def reseat(self, order: list) -> None:
        """換座位。order[k] = 新的第 k 個座位原本是哪一位玩家（舊座位編號）。

        座位順序即輪莊順序，所以莊家、積分與所有歷史紀錄中的座位編號都會一併重新對應，
        因此換座位後仍可正確復原。
        """
        if sorted(order) != [0, 1, 2, 3]:
            raise ValueError("座位必須是 4 位不同的玩家")
        inv = {old: new for new, old in enumerate(order)}

        def permute(seq):
            return [seq[old] for old in order]

        self.players = permute(self.players)
        self.scores = permute(self.scores)
        self.dealer = inv[self.dealer]
        for h in self.history:
            h["dealer"] = inv[h["dealer"]]
            h["deltas"] = permute(h["deltas"])
            h["before"]["dealer"] = inv[h["before"]["dealer"]]
            if h.get("winner") is not None:
                h["winner"] = inv[h["winner"]]
            if h.get("discarder") is not None:
                h["discarder"] = inv[h["discarder"]]
            for pay in h.get("payments", []):
                pay["payer"] = inv[pay["payer"]]

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
        self.jiang = b.get("jiang", self.jiang)   # 舊存檔沒有這個欄位
        return True

    # ---------- 統計 ----------
    def _in_scope(self, h: dict, jiang: int | None) -> bool:
        return jiang is None or h.get("jiang", 1) == jiang

    def scope_scores(self, jiang: int | None = None) -> list:
        """累計積分（jiang=None）或指定那一將內的積分。"""
        if jiang is None:
            return list(self.scores)
        out = [0, 0, 0, 0]
        for h in self.history:
            if self._in_scope(h, jiang):
                for i in range(4):
                    out[i] += h["deltas"][i]
        return out

    def hands_played(self, jiang: int | None = None) -> int:
        """已完成的局數（胡牌＋流局，不含手動調整）。"""
        return sum(1 for h in self.history
                   if h["type"] in ("win", "draw") and self._in_scope(h, jiang))

    def stats(self, jiang: int | None = None) -> list:
        """每位玩家的戰績與金額（依座位順序）。

        zimo／ron／discard：自摸次數、放槍胡牌次數（別人放槍給你）、放槍次數。
        *_amt：對應的金額。zimo_paid：被別人自摸的次數與金額。adjust：手動調整。
        恆等式：net = zimo_amt + ron_amt - discard_amt - zimo_paid_amt + adjust。
        """
        keys = ("zimo", "zimo_amt", "ron", "ron_amt", "discard", "discard_amt",
                "zimo_paid", "zimo_paid_amt", "adjust", "net")
        res = [dict.fromkeys(keys, 0) for _ in range(4)]
        for h in self.history:
            if not self._in_scope(h, jiang):
                continue
            for i in range(4):
                res[i]["net"] += h["deltas"][i]
            if h["type"] == "adjust":
                for i in range(4):
                    res[i]["adjust"] += h["deltas"][i]
            elif h["type"] == "win":
                w = h["winner"]
                total = sum(p["amount"] for p in h["payments"])
                if h["kind"] == "自摸":
                    res[w]["zimo"] += 1
                    res[w]["zimo_amt"] += total
                    for p in h["payments"]:
                        res[p["payer"]]["zimo_paid"] += 1
                        res[p["payer"]]["zimo_paid_amt"] += p["amount"]
                else:
                    res[w]["ron"] += 1
                    res[w]["ron_amt"] += total
                    d = h["discarder"]
                    res[d]["discard"] += 1
                    res[d]["discard_amt"] += total
        hands = self.hands_played(jiang)
        for r in res:
            r["hands"] = hands
            r["wins"] = r["zimo"] + r["ron"]
        return res

    def trend(self, jiang: int | None = None) -> list:
        """每一筆紀錄之後的累計積分（第一列為起點 0），用來畫走勢圖。"""
        cur = [0, 0, 0, 0]
        rows = [list(cur)]
        for h in self.history:
            if self._in_scope(h, jiang):
                cur = [cur[i] + h["deltas"][i] for i in range(4)]
                rows.append(list(cur))
        return rows

    # ---------- 存讀檔 ----------
    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=indent)

    def history_rows(self) -> list:
        """每把紀錄，一把一個 dict（欄位：把、局、莊家、連莊、結果、各玩家輸贏）。"""
        rows = []
        for h in self.history:
            if h["type"] == "win":
                how = ("自摸" if h["kind"] == "自摸"
                       else f"{self.players[h['discarder']]} 放槍")
                manual = "，手動金額" if any(p.get("manual") for p in h["payments"]) else ""
                result = f"{self.players[h['winner']]} {how}（牌型 {h['hand_tai']} 台{manual}）"
            elif h["type"] == "adjust":
                result = "手動調整積分" + (f"：{h['note']}" if h.get("note") else "")
            else:
                result = "流局"
            row = {"把": h["hand_no"], "局": h["label"],
                   "莊家": self.players[h["dealer"]], "連莊": h["streak"],
                   "結果": result}
            for i, name in enumerate(self.players):
                row[name] = h["deltas"][i]
            rows.append(row)
        return rows

    @classmethod
    def from_json(cls, text: str) -> "Game":
        d = json.loads(text)
        rules = Rules(**d.pop("rules"))
        return cls(rules=rules, **d)
