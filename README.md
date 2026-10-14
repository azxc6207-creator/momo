# 台灣麻將計台器

依台灣 16 張麻將規則的計台、連莊、金額結算工具（Streamlit，手機優先）。

## 功能
- 底／台金額可自訂（預設 100／20，內建 100/20、300/100、50/10 快速切換）
- 莊家身分台數、每次連莊加幾台（2 = 連 n 拉 n）、連莊上限、流局是否連莊／累計連莊數皆可自訂
- 台數表可直接在介面編輯、新增、刪除
- 自摸／放槍結算、換莊、圈風與門風自動推進
- 每把紀錄、復原上一把、CSV 匯出、JSON 存檔與載入

## 結算規則
- 每家應付 = 底 + 台數 × 每台
- 台數 = 牌型台數 + （莊家參與時）莊家身分台 + 連莊數 × 每次連莊台數
- 自摸：三家各付；放槍：放槍者一人付
- 非莊家自摸時，只有莊家多付莊家加成
- 莊家胡牌：連莊數 +1；他人胡牌：換莊、連莊歸零
- 尚未支援：一炮多響（目前一把一位胡牌者）

## 本機執行
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 測試
```bash
pip install pytest
pytest -q
```

## 部署到 Streamlit Cloud
1. 在 GitHub 建立新 repository，把本資料夾所有檔案上傳（`app.py`、`mahjong_core.py`、`requirements.txt`、`.gitignore`、`README.md`）。
2. 前往 https://share.streamlit.io 以 GitHub 帳號登入。
3. 點 **Create app** → 選擇該 repository 與分支，Main file path 填 `app.py`。
4. 點 **Deploy**，完成後用手機開啟網址即可。

本專案不使用 API 金鑰或 Secrets。注意：Streamlit Cloud 重新啟動後記憶體資料會消失，請在「紀錄」分頁下載 JSON 存檔，之後再載入。
