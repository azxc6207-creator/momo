from mahjong_core import Game, Rules, compute_hand_tai, DEFAULT_TAI_TABLE

TABLE = {r["名稱"]: r["台數"] for r in DEFAULT_TAI_TABLE}
NAMES = ["A", "B", "C", "D"]


def new(**kw):
    return Game(players=NAMES, rules=Rules(**kw))


def test_dealer_zimo_no_streak():
    g = new()  # 100/20, 莊1, 連2
    # 莊家 A 自摸，牌型 3 台（自摸+門清+獨聽）
    tai, _ = compute_hand_tai(TABLE, ["門清", "獨聽"], "自摸")
    assert tai == 3
    r = g.apply_win(0, "自摸", tai)
    # 每家付 100 + (3+1)*20 = 180
    assert r["deltas"] == [540, -180, -180, -180]
    assert g.dealer == 0 and g.streak == 1


def test_dealer_streak_bonus():
    g = new()
    g.apply_win(0, "放槍", 1, discarder=2)   # 莊連1
    assert g.streak == 1
    # 連1：莊1 + 連1拉1(2) = 3 台加成；放槍者 C 付 100 + (2+3)*20 = 200
    r = g.apply_win(0, "放槍", 2, discarder=1)
    assert r["payments"][0]["tai"] == 5
    assert r["deltas"][0] == 200 and r["deltas"][1] == -200


def test_nondealer_zimo_only_dealer_pays_bonus():
    g = new()
    r = g.apply_win(1, "自摸", 2)
    amounts = {p["payer"]: p["amount"] for p in r["payments"]}
    assert amounts[0] == 100 + (2 + 1) * 20   # 莊家多付 1 台
    assert amounts[2] == amounts[3] == 100 + 2 * 20
    assert g.dealer == 1 and g.streak == 0 and g.dealer_turns == 1


def test_nondealer_discard_not_involving_dealer():
    g = new()
    r = g.apply_win(1, "放槍", 2, discarder=2)
    assert r["payments"][0]["tai"] == 2            # 莊家不在場，無加成
    r2 = g.apply_win(2, "放槍", 0, discarder=1)    # 現在莊家是 B(1)，B 放槍
    assert r2["payments"][0]["tai"] == g.rules.dealer_tai   # 放槍者是莊家，加莊 1 台


def test_draw_rules():
    g = new()
    g.apply_draw()
    assert g.dealer == 0 and g.streak == 1
    g = new(draw_count_streak=False)
    g.apply_draw()
    assert g.dealer == 0 and g.streak == 0
    g = new(draw_keep_dealer=False)
    g.apply_draw()
    assert g.dealer == 1


def test_wind_round_rollover_and_undo():
    g = new()
    for i in range(4):
        g.apply_win((g.dealer + 1) % 4, "自摸", 0)
    assert g.wind_round == 1 and g.dealer == 0 and g.dealer_turns == 0
    assert g.round_label() == "南風東局"
    for _ in range(4):
        assert g.undo()
    assert g.scores == [0, 0, 0, 0] and g.wind_round == 0 and g.hand_no == 1
    assert not g.undo()


def test_streak_cap():
    g = new(streak_cap=2)
    for _ in range(4):
        g.apply_draw()
    assert g.streak == 4 and g.effective_streak() == 2
    assert g.dealer_bonus_tai() == 1 + 2 * 2


def test_zero_sum_and_json_roundtrip():
    g = new()
    g.apply_win(2, "放槍", 4, discarder=0, items=["清一色"])
    g.apply_draw()
    assert sum(g.scores) == 0
    g2 = Game.from_json(g.to_json())
    assert g2.scores == g.scores and g2.history == g.history and g2.rules == g.rules


def test_buqiuren_replaces_menqing_zimo():
    tai, bd = compute_hand_tai(TABLE, ["不求人", "門清"], "自摸")
    assert tai == 3
    tai2, _ = compute_hand_tai(TABLE, ["不求人"], "放槍")
    assert tai2 == 0


def test_amount_override():
    g = new()
    # B 自摸 2 台：莊家 A 原本付 160，C、D 各付 140；手動把 C 改成 300
    r = g.apply_win(1, "自摸", 2, amount_override={2: 300})
    amounts = {p["payer"]: p["amount"] for p in r["payments"]}
    assert amounts == {0: 160, 2: 300, 3: 140}
    manual = {p["payer"]: p["manual"] for p in r["payments"]}
    assert manual == {0: False, 2: True, 3: False}
    assert g.scores == [-160, 600, -300, -140]
    assert sum(g.scores) == 0
    # 復原後完全回到原狀（含手動金額）
    assert g.undo()
    assert g.scores == [0, 0, 0, 0] and g.dealer == 0


def test_override_negative_rejected():
    g = new()
    try:
        g.apply_win(1, "自摸", 0, amount_override={2: -5})
    except ValueError:
        pass
    else:
        raise AssertionError("負數金額應被拒絕")
    assert g.history == [] and g.scores == [0, 0, 0, 0]


def test_adjust_and_undo():
    g = new()
    g.apply_win(0, "放槍", 1, discarder=1)
    snap = (g.dealer, g.streak, g.hand_no, list(g.scores))
    g.apply_adjust([-50, 50, 0, 0], "打錯")
    assert g.scores[0] == snap[3][0] - 50 and g.scores[1] == snap[3][1] + 50
    assert (g.dealer, g.streak, g.hand_no) == snap[:3]      # 不影響莊家與局數
    assert g.undo()
    assert (g.dealer, g.streak, g.hand_no, g.scores) == snap
    try:
        g.apply_adjust([0, 0, 0, 0])
    except ValueError:
        pass
    else:
        raise AssertionError("全 0 調整應被拒絕")


def test_reseat_keeps_everything_consistent():
    g = new()
    g.apply_win(1, "放槍", 2, discarder=2)   # B 胡 C 放槍，換莊到 B
    g.apply_win(1, "自摸", 1)                # B 莊家自摸
    before_scores = dict(zip(g.players, g.scores))
    dealer_name = g.players[g.dealer]
    order = [2, 0, 3, 1]                     # 新座位：C, A, D, B
    g.reseat(order)
    assert g.players == ["C", "A", "D", "B"]
    assert dict(zip(g.players, g.scores)) == before_scores
    assert g.players[g.dealer] == dealer_name
    # 歷史紀錄的人名對應不變
    h0 = g.history[0]
    assert g.players[h0["winner"]] == "B" and g.players[h0["discarder"]] == "C"
    assert g.players[h0["payments"][0]["payer"]] == "C"
    assert g.players[h0["before"]["dealer"]] == "A"
    # 換座位後復原兩把，應回到初始：A 當莊、零分
    assert g.undo() and g.undo()
    assert g.scores == [0, 0, 0, 0]
    assert g.players[g.dealer] == "A" and g.hand_no == 1


def test_reseat_rejects_bad_order():
    g = new()
    try:
        g.reseat([0, 0, 1, 2])
    except ValueError:
        pass
    else:
        raise AssertionError("重複座位應被拒絕")
    assert g.players == NAMES
