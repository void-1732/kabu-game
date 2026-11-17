# スマホ操作の回帰テスト

シンプル／詳細注文、通常指値の価格訂正、銘柄別の情報タブをブラウザで検証します。各テストは独立したブラウザの保存領域を使用します。

## 準備

Python と Playwright を用意してください。

```sh
python -m pip install playwright
python -m playwright install chromium
```

## 実行

リポジトリーのルートでサーバーを起動します。

```sh
python -m http.server 8765 --bind 127.0.0.1
```

別のターミナルから実行します。

```sh
python tests/mobile_ux_regression.py --url http://127.0.0.1:8765/
```

Chromium または Chrome が PATH にあれば使用し、なければ Playwright のブラウザを使用します。`--chromium /path/to/chromium` または `CHROMIUM_PATH` でも指定できます。スクリーンショットは一時ディレクトリーへ保存されます。保存先は `--artifacts /path/to/directory` で変更できます。

## 確認する内容

- シンプル／詳細表示の切り替えと設定の復元
- 選択中の逆指値・IFD・OCOを非表示にしないこと
- 現物・信用の指値訂正が確認前には実行されないこと
- 部分約定した注文の残数量・予約資金・約定履歴の整合性
- 不正な価格、資金不足、約定・取消後の古い状態での訂正を拒否し、元の状態を保持すること
- 通常指値以外の注文と、プレクロージング・大引けの制限
- 銘柄別注文一覧と取消確認、訂正履歴の保存・復元
- 銘柄タブ間での選択維持、ニュースからチャートへの移動
- 銘柄別の現物・信用保有表示と売却・返済の動線

固定シードで再現性を保ち、JavaScript の実行エラーも検出します。
