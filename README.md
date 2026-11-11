# MCRDP v6

## macOS版のダウンロード

[GitHub Releases](https://github.com/ren3100-git/MCRDP/releases/latest)からZIPをダウンロードして展開してください。配布アプリはApple Silicon（arm64）用です。Intel Macでの動作は確認していません。別端末での起動、Appleによる公証は未確認です。

ソースコードから実行する場合は、以下の環境構築手順に従ってください。


RheoPlus／RheoCompassの測定ファイルを自動判別し、選択した変数をExcelへ整理するGUIアプリです。

## v6の構成

`application/`、`domain/`、`infrastructure/`、`presentation/`を廃止し、処理モジュールを`src/mcrdp/`直下へ集約しました。GUIだけは`src/mcrdp/gui/`へ分離しています。

```text
MCRDP/
├── config/
│   └── variables.json
├── src/mcrdp/
│   ├── app.py
│   ├── models.py
│   ├── processor.py
│   ├── variables.py
│   ├── profiles.py
│   ├── naming.py
│   ├── excel.py
│   ├── igor.py
│   ├── gui/main_window.py
│   └── gui/settings_dialog.py
├── tests/
├── launcher.py
├── pyproject.toml
├── requirements.txt
└── build_macos_v6.sh
```

## v6の主な機能

- 複数ファイル横結合時に列Indexを一意化し、`InvalidIndexError`を防止
- Column Names画面へ読み取り専用の`mean_header`列を追加
- `NAME_TABLE_COLUMNS`を`models.py`で管理
- Excelのvariablesシートは、1行目mean、2行目variable key、3行目output_name
- Settingsから変数定義、処理プリセット、列名規則、Excel出力、IGOR既定値を編集
- プリセットにlog10／linear、Mean header、recursiveをまとめて保存
- 出力ファイルの競合時動作、自動出力、出力シートを設定可能

## 環境構築

```bash
cd MCRDP
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

## 起動

```bash
python -m mcrdp
```

または、editable install後に次を使用できます。

```bash
mcrdp
```

## テスト

```bash
python -m pip install pytest
pytest -q
```

## macOSアプリのビルド

プロジェクトルートに`MCRDP_icon.icns`または`MCRDP_v4_icns.icns`がある場合は自動的に使用します。

```bash
./build_macos_v6.sh
```

`config/variables.json`はPyInstaller成果物へ同梱されます。

## 設定

メニューバーの `Settings > Settings…` から、列名の並び順・区切り文字・連番、
試料名の置換規則、変数定義、入力名の別名、IGORラベル、単位、GUIへの表示、
処理条件つきプリセット、Excel出力、IGORの既定値を編集できます。
設定はユーザー領域の `MCRDP/variables.json` に保存され、次回起動時にも使用されます。
Settings画面ではJSONの読み込み・書き出しと、同梱設定への復元もできます。

## 開発・配布および免責事項

本ソフトウェアは個人が開発・配布しています。開発者はApple Developer Programに登録していません。本ソフトウェアは現状のまま提供され、動作、正確性、特定の目的への適合性を保証しません。利用は利用者自身の責任で行ってください。法令上認められる範囲において、開発者は本ソフトウェアの利用または利用不能により生じた損害、データの損失その他の不利益について責任を負いません。

This software is developed and distributed by an individual developer who is not enrolled in the Apple Developer Program. It is provided as is, without warranties regarding its operation, accuracy, or fitness for a particular purpose. Use of the software is at the user’s own risk. To the extent permitted by applicable law, the developer accepts no liability for damages, data loss, or other adverse consequences arising from the use of, or inability to use, the software.
