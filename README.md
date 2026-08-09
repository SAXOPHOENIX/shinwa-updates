# 診和アップデート配信

安全確認済みの診和辞書アップデートと、一般利用者向け更新履歴をGitHub Pagesで公開します。

- 公開サイト: https://saxophoenix.github.io/shinwa-updates/
- manifest: https://saxophoenix.github.io/shinwa-updates/v1/dictionaries/generated_ja_manifest.json
- 更新履歴: https://saxophoenix.github.io/shinwa-updates/updates/

公開処理は `Publish Shinwa dictionary update` ワークフローだけが行います。教育リポジトリの完全な40文字コミットSHAを入力し、そのコミットに固定して検査・署名します。

必要なRepository Secrets:

- `SHINWA_DICTIONARY_SIGNING_KEY`: Ed25519秘密鍵PEM
- `SHINWA_DICTIONARY_SOURCE_TOKEN`: 非公開の教育リポジトリを読み取れるGitHub token

秘密鍵、患者情報、音声、書き起こし、SOAP、カルテ本文、legacy補正候補は公開しません。

