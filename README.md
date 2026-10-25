# Diary-Study-Log

技術の学習を通じて得た知識や考察、試行錯誤を記録するリポジトリです。

## 記録する内容

- **技術書の読書ログ**
  - 読んだ内容の要点、疑問、自分なりの考察を記録します。
- **技術概念・仕組みの学習ログ**
  - 用語の定義や理論、仕組みを調べて理解する過程と、残った疑問を記録します。
- **技術課題・演習問題への取り組みログ**
  - 設計・実装の課題や演習問題について、解き方、試行錯誤、結果、振り返りを記録します。

結論だけでなく、疑問を持ったきっかけや、考え方が変わった経緯も残します。

## 記事一覧

公開後は [Diary Study Log](https://ktakao01.github.io/Diary-Study-Log/) から、日報・学習ログ、週報、月報を閲覧できます。タイトル・ファイル名・日付で絞り込みできます。

- [日報・学習ログ](https://ktakao01.github.io/Diary-Study-Log/#daily)
- [週報](https://ktakao01.github.io/Diary-Study-Log/#weekly)
- [月報](https://ktakao01.github.io/Diary-Study-Log/#monthly)

## 公開と更新

GitHub の **Settings → Pages** で、Source を **Deploy from a branch**、Branch を **main / (root)** に設定します。

`DailyReport/`、`WeeklyReport/`、`MonthlyReport/` に Markdown ファイルを追加して main に反映すると、記事と一覧が自動的に更新されます。日報・月報は日付で始まるファイル名、週報は年のフォルダと日付で始まるファイル名を使うと、新しい順に並びます。本文の先頭見出しがあれば一覧のタイトルに使い、`done`・`report` などの共通見出しはファイル名に置き換えます。

既存の記事本文・ファイル名は変更していません。年間計画、監査記録、エージェント向け設定などはサイトの公開対象から除外しています。

ファイル名に `:` がある既存の週報1件は、JekyllのURL生成エラーを避けるため `_config.yml` で公開URLを指定しています。

PR では GitHub Pages と同じ Jekyll ビルドを行い、記事一覧の網羅性・リンク先・公開対象外ファイルを検証します。
