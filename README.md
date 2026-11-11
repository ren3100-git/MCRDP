# MCRDP

RheoPlus／RheoCompassから出力した測定ファイルを読み込み、必要な変数をExcelへ整理するGUIアプリケーションです。複数の測定ファイルの整理、列名の調整、IGOR用コマンドの生成を行えます。

## ダウンロードと起動

[ダウンロードページ](https://github.com/ren3100-git/MCRDP/releases/latest)のAssetsからmacOS用ZIPをダウンロードし、展開したアプリを開いてください。配布アプリの実行にPythonのインストールは不要です。

配布アプリはApple Silicon（arm64）用です。Intel Macおよび別端末での動作は未確認です。Appleによる公証は未確認で、macOSのセキュリティ機能により起動が制限される場合があります。

## 基本的な使い方

1. 「フォルダ選択」で測定ファイルを保存したフォルダを選択します。下位のフォルダも対象にする場合は「サブフォルダも検索」を有効にします。
2. 「Preset」を選択するか、「Variable Selection」で出力する変数を指定します。log10とlinearの指定を確認してください。
3. 「Output xlsx」に出力ファイル名を設定します。
4. 「Run」で処理を実行します。
5. 処理結果を確認し、必要に応じて「Column Names」で出力名や出力対象を調整して「Export Excel」で保存します。自動出力の設定はSettingsで変更できます。

元の測定ファイルは保管し、出力内容を確認してから解析に使用してください。

## 設定と出力

「Settings > Settings…」で変数定義、処理プリセット、列名の規則、Excel出力、IGOR用の既定値を設定できます。設定はユーザー領域に保存されます。

Excelのvariablesシートは、1行目がmean、2行目がvariable key、3行目がoutput_nameです。「Mean header」で見出しに使用する変数を指定できます。

IGOR用コマンドは、対象の変数を指定して「Generate」で生成し、「Copy」でコピーします。

## ソースコードから起動する場合

Python 3.12以上を使用してください。リポジトリをダウンロードし、そのフォルダ内で以下を実行します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m mcrdp
```

## 開発・配布および免責事項

本ソフトウェアは個人が開発・配布しています。開発者はApple Developer Programに登録していません。本ソフトウェアは現状のまま提供され、動作、正確性、特定の目的への適合性を保証しません。利用は利用者自身の責任で行ってください。法令上認められる範囲において、開発者は本ソフトウェアの利用または利用不能により生じた損害、データの損失その他の不利益について責任を負いません。

This software is developed and distributed by an individual developer who is not enrolled in the Apple Developer Program. It is provided as is, without warranties regarding its operation, accuracy, or fitness for a particular purpose. Use of the software is at the user’s own risk. To the extent permitted by applicable law, the developer accepts no liability for damages, data loss, or other adverse consequences arising from the use of, or inability to use, the software.
