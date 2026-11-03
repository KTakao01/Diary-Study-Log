# push後の情報監査とマージ条件

作業ブランチへのpushとPRの作成・更新をきっかけに、`audit-log-privacy` の指示を使って変更内容を監査する。成功したコミットにだけ `privacy-audit` ステータスを付ける。**ワークフローを追加するだけではマージ制限にならない。初期設定が必要。**

## 初期設定

1. この変更のPRを内容確認のうえmainへマージする。`workflow_run` の監査本体はmainに存在してから起動するため、初回導入PRに本番監査の成功を求めると導入できない。初回はローカルテストと差分の確認で導入する。
2. リポジトリの **Settings → Secrets and variables → Actions** で、専用のOpenAIプロジェクトのAPIキーを **`OPENAI_API_KEY`** として登録する。キーを本文・コミット・PR・会話へ貼らない。API料金と利用上限はOpenAI側で確認する。ChatGPTの月額契約とは別のAPI利用になる。
3. テキストだけの小さいテストPRを作る。**Actions → Privacy audit → Run workflow** からmainを選び、`pull_request_number` にPR番号を入力して再実行もできる。`privacy-audit` が実際に成功したことを確認する。
4. **Settings → Rules → Rulesets** にmain対象のルールを追加する。既存の削除・強制push禁止は維持し、次を設定する。
   - Enforcement: **Active**
   - Target branches: **main / default branch**
   - **Require a pull request before merging**
   - **Require status checks to pass**: **`privacy-audit`**。利用可能なら発行元を **GitHub Actions** に限定する。
   - **Require branches to be up to date before merging**
   - **Bypass list: 空**。管理者による通常のマージにも適用する。
   - 既存のページ検証の **`build`** も必須にする。
5. 監査が失敗・未完了のテストPRでマージがブロックされることを確認する。追加pushで別コミットになったとき、前の合格が引き継がれないことも確認する。

手順4は [privacy-main-ruleset.json](privacy-main-ruleset.json) をRulesetsのImportから読み込んでも設定できる。対象はdefault branch、必須チェックは `privacy-audit` と `build`、発行元はGitHub Actions、バイパスなし。既存ルールは削除しない。**初回PRのマージと監査の動作確認より先に有効化すると、未導入の必須チェック待ちでマージできなくなる。** このファイルをcommitするだけではルールは有効にならない。

導入作業時点では、APIキーを利用した実環境の監査と、GitHubの保護ルール設定・マージ拒否の確認は未完了。これらが完了するまで「必須監査が有効」と扱わない。

## 実行の仕組み

- `Privacy audit request` は作業ブランチへのpush、PRの作成・追加push・本文編集などで動く。秘密情報を持たず、監査用テストもAPIを呼ばずに実行する。
- `Privacy audit` は、そのワークフローの開始要求・完了をmain側から受ける。開始要求で対象コミットをpendingにし、完了後に監査する。前段のテストが失敗しても監査は実行する。
- 実行するPython・スキル・`AGENTS.md` はmain側のもの。対象ブランチのファイルはGitのblobとして読み、checkout・ビルド・スクリプト実行・成果物のダウンロードはしない。
- 監査対象内の命令文はデータとして扱う。モデルにツールやネットワーク操作権限を与えず、結果をプログラムで検証する。
- リポジトリ所有者以外が起動した監査は、自動でAPI料金を使わず未合格にする。必要なPRは所有者がmainの手動実行から監査する。
- 合格直前にmain、PRのhead、タイトル・本文を取り直し、監査中の変更があれば失敗にする。

## 対象と合格条件

対象は、現在のmainから対象コミットまでに導入された変更の範囲。変更されたテキストの全文と途中版、変更・削除されたパス、新規コミットのメッセージ、ブランチ名、対応する開いているPRのタイトル・本文を調べる。**途中コミットで追加し、後から削除した情報も検査する。** 通常の変更監査では、未変更の過去ログ全部を毎回再監査しない。

検出・要確認・未確認がなく、対象全件への判定が揃った場合だけ成功する。APIキーなし、API障害、モデルの拒否・出力不正・回答不足、件数やサイズ上限、取得不足は失敗にする。画像・PDF・LFS・サブモジュール・シンボリックリンク等、現行CIで内容を確認できない追加・変更も合格にしない。

公開ログには固定の結果コードと、検証済みの中立ID・blob SHA・分類コード・行番号だけを出す。本文、秘密値、モデルの説明、HTTPエラー本文、機微情報を含み得るファイル名を公開しない。監査結果のファイルをActions artifact、PRコメント、リポジトリへ保存しない。失敗の調査は非公開の作業環境で対象差分を確認する。

## 限界と運用

- **公開リポジトリへのpush時点で、ブランチやコミットは公開される。** このCIはmainへの混入を止める仕組み。push前の確認を続ける。認証情報を誤ってpushした場合は、単に次のコミットで消すだけでは足りず、失効・再発行と履歴対応を別途判断する。
- 監査対象の文章はOpenAI APIへ送信される。`store: false` はResponsesの保存を無効にする指定であり、すべてのログの即時削除やZero Data Retentionを保証するものではない。
- モデルは `gpt-5.4-mini-2026-03-17` に固定し、1監査で1回だけAPIを呼ぶ。入力はスキル・本文等の合計250,000 UTF-8バイトまで、出力上限は推論分を含め16,000トークン。超過は省略せず停止する。pushとPRイベントの両方で同じコミットを監査する場合もあるため、APIプロジェクトの利用額を管理する。
- AI監査には見逃し・誤検知がある。合格は確認範囲での判定であり、完全な安全の保証ではない。
- 対象外は、変更されていない過去ログ・別ブランチ・到達不能な履歴・GitHubの作者情報・PR/Issueのコメント・外部リンク先。削除された既存ファイルの旧本文全体の再監査も行わない。
- PRタイトル・本文の編集はコミットSHAを変えない。再監査は動くが、既存の成功からpendingへの切替と編集をGitHubが原子的に行うわけではない。マージ直前の公開用メッセージの確認を続ける。
- 必須statusは、同じ権限を持つ別のGitHub Actionsから偽装することまで防ぐものではない。悪意ある書込権限者への強い対策には、専用GitHub Appや組織の必須ワークフロー等が必要。監査用コード・ワークフロー・スキルの変更は人が確認する。
- 未対応の添付や誤検知を、監査の成功を偽装する形で通さない。必要なら監査処理を拡張し、テストした変更を別PRで導入する。

## ローカルの検証

```sh
python3 -m unittest discover -s tests -p 'test_privacy*.py'
```

テストは架空のデータと一時Gitリポジトリを使用する。実際の個人情報やAPIキーをテスト用にcommitしない。

## 参照

- [監査スキル](../.agents/skills/audit-log-privacy/SKILL.md)
- [GitHub: workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- [GitHub: required status checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-status-checks-to-pass-before-merging)
- [OpenAI: structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI: API data controls](https://developers.openai.com/api/docs/guides/your-data)
