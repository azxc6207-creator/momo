"""統計圖表的 Vega-Lite 規格（不依賴 streamlit，方便測試）。"""
from theme import CHART_COLORS, CREAM_TEXT

PIE_KINDS = ["自摸", "胡牌", "放槍"]
POS_COLOR = "#8fd694"
NEG_COLOR = "#ff9d8a"


def _base(height: int) -> dict:
    return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "background": "transparent", "height": height,
            "config": {"view": {"stroke": None},
                       "axis": {"labelColor": CREAM_TEXT, "titleColor": CREAM_TEXT,
                                "gridColor": "rgba(244,237,220,0.18)",
                                "domainColor": "rgba(244,237,220,0.4)"},
                       "legend": {"labelColor": CREAM_TEXT, "titleColor": CREAM_TEXT}}}


def pie_spec(name: str, zimo: int, ron: int, discard: int) -> dict:
    """單一玩家的自摸／胡牌／放槍圓餅圖。三者皆 0 時回傳 None。"""
    values = [{"類型": k, "次數": v} for k, v in zip(PIE_KINDS, (zimo, ron, discard))]
    if sum(v["次數"] for v in values) == 0:
        return None
    spec = _base(150)
    spec["width"] = "container"
    spec["title"] = {"text": name, "color": CREAM_TEXT, "fontSize": 14}
    spec["data"] = {"values": values}
    spec["layer"] = [
        {"mark": {"type": "arc", "innerRadius": 28, "outerRadius": 55, "stroke": "#0a2a18"},
         "encoding": {
             "theta": {"field": "次數", "type": "quantitative", "stack": True},
             "color": {"field": "類型", "type": "nominal", "sort": PIE_KINDS,
                       "scale": {"domain": PIE_KINDS, "range": [CHART_COLORS[0], CHART_COLORS[2], CHART_COLORS[3]]},
                       "legend": {"orient": "bottom", "title": None}},
             "tooltip": [{"field": "類型"}, {"field": "次數"}]}},
    ]
    return spec


def bar_spec(names: list, nets: list) -> dict:
    """玩家總金額（淨額）長條圖，贏為綠、輸為紅。"""
    spec = _base(max(120, 56 * len(names)))
    spec["width"] = "container"
    spec["data"] = {"values": [{"玩家": n, "總金額": v} for n, v in zip(names, nets)]}
    spec["layer"] = [
        {"mark": {"type": "bar", "cornerRadius": 3},
         "encoding": {
             "y": {"field": "玩家", "type": "nominal", "sort": names, "title": None},
             "x": {"field": "總金額", "type": "quantitative", "title": "總金額（元）"},
             "color": {"condition": {"test": "datum['總金額'] >= 0", "value": POS_COLOR},
                       "value": NEG_COLOR},
             "tooltip": [{"field": "玩家"}, {"field": "總金額"}]}},
        *[{"transform": [{"filter": f"datum['總金額'] {op} 0"}],
           "mark": {"type": "text", "align": align, "dx": dx, "color": CREAM_TEXT},
           "encoding": {"y": {"field": "玩家", "type": "nominal", "sort": names},
                        "x": {"field": "總金額", "type": "quantitative"},
                        "text": {"field": "總金額", "type": "quantitative"}}}
          for op, align, dx in ((">=", "left", 4), ("<", "right", -4))],
    ]
    return spec
