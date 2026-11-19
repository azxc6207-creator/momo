import re

import theme


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _over(fg, alpha, bg):
    return tuple(round(alpha * f + (1 - alpha) * b) for f, b in zip(fg, bg))


# 背景圖內容區實際量到的顏色：一般 #0b5e31，最亮約 #367337（竹葉附近約 #6e6c3a）
BG_TYPICAL, BG_BRIGHT, BG_BAMBOO = _rgb("#0b5e31"), _rgb("#367337"), _rgb("#6e6c3a")


def test_css_builds_with_background_image():
    css = theme.build_css()
    assert css.strip().startswith("<style>") and css.strip().endswith("</style>")
    assert "$" not in css, "還有沒被替換掉的範本變數"
    assert "data:image/jpeg;base64," in css and "100lvh" in css
    # 背景圖不能太大，否則每次載入都拖慢手機
    assert theme.BG_FILE.stat().st_size < 300 * 1024


def test_css_without_image_falls_back_to_gradient():
    css = theme.build_css(with_image=False)
    assert "data:image" not in css and "linear-gradient" in css


def test_css_has_the_requested_look():
    css = theme.build_css(with_image=False)
    for must in (theme.CREAM, theme.GOLD, f"rgba({', '.join(map(str, theme.CARD_RGB))}",
                 ".st-key-seat_board", "stBaseButton-primary", "[class*=\"st-key-card_\"]",
                 "transform: scale(0.94)", "stExpander"):
        assert must in css, must


def test_card_text_is_readable_on_every_part_of_the_background():
    card = theme.CARD_RGB
    for bg in (BG_TYPICAL, BG_BRIGHT, BG_BAMBOO):
        c = _over(card, theme.CARD_ALPHA, bg)
        assert _ratio(_rgb(theme.CREAM_TEXT), c) >= 7, bg      # 一般文字
        assert _ratio(_rgb(theme.GOLD), c) >= 7, bg            # 金色數字


def test_bare_text_on_background_is_readable():
    for bg in (BG_TYPICAL, BG_BRIGHT, BG_BAMBOO):
        assert _ratio(_rgb(theme.CREAM_TEXT), bg) >= 4.5, bg
        assert _ratio(_rgb(theme.CAPTION_TEXT), bg) >= 4.5, bg


def test_buttons_are_readable():
    assert _ratio(_rgb(theme.INK), _rgb(theme.CREAM)) >= 7              # 米白按鈕上的深綠字
    for gold in (theme.GOLD_DEEP, "#f6dc87"):                            # 主要按鈕（金色漸層兩端）
        assert _ratio(_rgb(theme.ON_GOLD), _rgb(gold)) >= 4.5, gold
    pill = _over((4, 30, 16), 0.6, BG_BRIGHT)                            # 折疊選單的選項
    assert _ratio(_rgb(theme.CREAM_TEXT), pill) >= 7


def test_gold_number_helper_and_chart_colors():
    assert theme.num_html("+35") == "<span class='num'>+35</span>"
    assert len(theme.CHART_COLORS) == 4 and len(set(theme.CHART_COLORS)) == 4
    assert all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in theme.CHART_COLORS)
