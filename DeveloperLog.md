# 診和アップデート配信 Developer Log

## 2026-08-09 初回公開

- 公開リポジトリ `SAXOPHOENIX/shinwa-updates` を作成した。
- GitHub PagesをActions方式で有効化し、`https://saxophoenix.github.io/shinwa-updates/` を公開した。
- `Publish Shinwa dictionary update` ワークフローを追加した。
- `workflow_dispatch` と `repository_dispatch` の両方で、教育リポジトリの完全な40文字 `source_commit` を受け取るようにした。
- 非公開教育リポジトリを指定コミットへ固定してcheckoutし、取得後のHEADが入力SHAと一致することを確認する。
- hotwords、文脈条件付き補正、自動補正を別構造で保持し、無条件補正には `automatic_corrections` だけを使用する。
- legacy候補、患者情報、音声、書き起こし、SOAP、カルテ本文、秘密鍵を公開物へ含めない。
- JSON schema、`locale=ja-JP`、バージョン単調増加、空文字、同一変換、数値、左右、極性、一般文章負例、誤補正率を検査する。
- manifestの実ファイルバイト列をEd25519で署名し、raw 64-byte署名を保存する。署名直後に固定公開鍵で再検証する。
- 検査と署名が完了するまで既存 `docs/` を変更せず、失敗時に既存公開版を維持する。
- 初回は教育コミット `923dac33c02dbdb9b7d6d3f9224bef02fcce336d` からmanifest version 1を公開した。
- 公開辞書SHA-256は `4049f63fd41abd03d1c7e453b5ee6dbf629eb85f28a7393a9b7710da0b32efe7`。
- 公開URLから取得したmanifestについて、固定公開鍵で `Signature Verified Successfully` を確認した。

## 2026-08-09 Windows GitHub Release接続

- Windows側の `dictionary-update-v*` GitHub Releaseを固定タグと固定コミットで取得する方式へ変更した。
- Releaseの `SHA256SUMS` 実バイト列に対するraw 64-byte Ed25519署名を、診和固定公開鍵で検証する。
- 署名済みSHA-256と4つのRelease JSON実体が一致した場合だけ後続処理へ進む。
- Release JSONに含まれる学習検証用 `recognized_text`、文脈文、音声設定などはPagesへ転載せず、製品利用に必要な最小項目だけを3つの公開JSONへ変換する。
- manifestをschema 2へ更新し、Windows表示版 `2026.08.09.1253` を整数 `202608091253` へ変換する。既存公開version以下は拒否する。
- `hotwords.json`、`contextual_corrections.json`、`automatic_corrections.json` を固定URLで公開し、それぞれの公開実体SHA-256をmanifestへ記録する。
- 現行診和との互換性維持のため、3構造をまとめた版付き辞書も生成し、manifestの `download_url` と `sha256` で参照できるようにした。
- Pages用manifestの実バイト列を同じEd25519鍵で署名し、署名直後と公開後に固定公開鍵で検証する。
- Windows側Releaseの検証またはPages生成に失敗した場合は、既存 `docs/` と公開版を変更しない。
- 最新Release `dictionary-update-v2026.08.09.1253`、コミット `76953165cd2220486068873efd17e7a7ef46f2f7` を公開した。manifest整数versionは `202608091253`。
- 公開SHA-256はhotwords `db8da01dea1f94c4cbb6c054a5cea7c04023725016880ec2014f0b183ada850a`、文脈補正 `25720d9a79048c5e64a169b67802eb5700d7a37cc39e6ccc06b943650fe1f8ad`、自動補正 `d0538a8b6b8a3a6d60b509d4e3d922c94eab908952ae74c1633c12e183cc10bc`。
- GitHub Pagesから再取得したmanifest、3つのJSON、互換辞書についてSHA-256、HTTPS URL、禁止情報除外、raw 64-byte署名を再検証した。
- Windows側リポジトリのdefault branchへ `Notify Shinwa update site` を追加した。今後 `dictionary-update-v*` Releaseのpublishedイベントで、`dictionary_update_requested` を更新サイトへ自動送信する。
