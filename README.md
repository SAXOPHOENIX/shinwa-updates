# 診和アップデート配信

安全確認済みの診和辞書アップデートと、一般利用者向け更新履歴をGitHub Pagesで公開します。

- 公開サイト: https://saxophoenix.github.io/shinwa-updates/
- manifest: https://saxophoenix.github.io/shinwa-updates/v1/dictionaries/generated_ja_manifest.json
- 更新履歴: https://saxophoenix.github.io/shinwa-updates/updates/

公開処理は `Publish Shinwa dictionary update` ワークフローだけが行います。Windows側GitHub Releaseの固定タグと完全な40文字コミットSHAを受け取り、タグ、Release、コミットが一致することを確認してから公開します。

必要なRepository Secrets:

- `SHINWA_DICTIONARY_SIGNING_KEY`: Ed25519秘密鍵PEM
- `SHINWA_DICTIONARY_SOURCE_TOKEN`: 非公開の教育リポジトリを読み取れるGitHub token

秘密鍵、患者情報、音声、書き起こし、SOAP、カルテ本文、legacy補正候補は公開しません。

Windows側からは `dictionary_update_requested` の `repository_dispatch` を送り、`client_payload.source_tag` と `client_payload.source_commit` を指定します。Release assetsの `SHA256SUMS` とraw Ed25519署名を検証し、成功した場合だけPages用manifestを生成します。
