# us-states-lambda-bluegreen

コンテナイメージのLambda関数を、CodePipeline + CodeDeploy で **Blue/Green デプロイ**するサンプル。

既存の `us-states-lambda-pipeline`(同じLambdaをAll-at-onceでデプロイ)とは、リポジトリ・パイプライン・
ECR・スタック・関数・APIのすべてが独立しており、互いに影響しない。
AWS上のリソース名は `us-states-lambda-bg-*` のプレフィックスで統一。

## アーキテクチャ概要

```
[GitHub: hyamada3/us-states-lambda-bluegreen (main)]
        │  git push → Webhook(CodeStarConnections: github-connection1)
        ▼
┌──────────── CodePipeline: us-states-lambda-bg-pipeline (V2 / SUPERSEDED) ──────────┐
│                                                                                    │
│  Source          Build                  Approval        Deploy                     │
│  ┌──────────┐   ┌───────────────────┐   ┌──────────┐   ┌───────────────────────┐   │
│  │ GitHub   │──▶│ CodeBuild         │──▶│ Manual   │──▶│ CloudFormation        │   │
│  │ CODE_ZIP │   │ (イメージ2つ)     │   │ Approval │   │ + CodeDeploy (B/G)    │   │
│  └──────────┘   └───────────────────┘   └──────────┘   └───────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────┘
                          │                                          │
                          ▼                                          ▼
          ┌─────────────────────────────────┐    ┌────────────────────────────────────┐
          │ us-states-lambda-bg-build       │    │ us-states-lambda-bg-stack          │
          │ (buildspec.yml / 特権モード)    │    │ (cfn-deploy-roleで実行)            │
          │                                 │    │                                    │
          │ 1. pytest tests/ -v             │    │ 1. 新バージョン(Green)を発行       │
          │ 2. docker login (ECR)           │    │ 2. CodeDeploy がデプロイ開始       │
          │ 3. sam build                    │    │    (BLUE_GREEN / AllAtOnce)        │
          │    → src/Dockerfile   (本体)    │    │ 3. PreTrafficフックで              │
          │    → hooks/Dockerfile (フック)  │    │    Green を直接呼び出して検証      │
          │ 4. sam package                  │    │ 4. 合格 → エイリアス live を       │
          │    → 2イメージをECRへpush       │    │    Blue → Green へ一括切替         │
          │ 5. packaged.yaml を出力         │    │ 5. 不合格 / アラーム発報           │
          │                                 │    │    → Blue のまま自動ロールバック   │
          │                                 │    │                                    │
          └─────────────────────────────────┘    └────────────────────────────────────┘
                          │  docker push                       ▲  ImageUri参照
                          ▼                                    │
          ┌────────────────────────────────────────────────────────────────────────┐
          │ ECR: us-states-lambda-bg-pipeline                                      │
          │ (本体イメージ + フックイメージ / scan on push)                         │
          └────────────────────────────────────────────────────────────────────────┘

[利用者] ──HTTPS──▶ API Gateway (HTTP API) ──▶ us-states-lambda-bg-sample:live
                                                     │ (エイリアスが指すバージョン)
                                                     ├─▶ Blue : 現行バージョン vN
                                                     └─▶ Green: 新バージョン vN+1
```

## Blue/Green の切り替えの流れ

```
  切替前                         検証                           切替後

┌────────────────────────┐     ┌────────────────────────┐     ┌────────────────────────┐
│ live ─▶ vN (Blue)      │ ──▶ │ PreTrafficフックが     │ ──▶ │ live ─▶ vN+1 (Green)   │
│                        │     │ vN+1 を直接invoke      │     │                        │
│ vN+1 (Green) 発行      │     │ statusCode=200 かつ    │ 合格│ vN (Blue) は残る       │
│ トラフィック 0%        │     │ message を確認         │     │ (いつでも戻せる)       │
└────────────────────────┘     └────────────────────────┘     └────────────────────────┘
                                           │ 不合格 / アラーム発報
                                           ▼
                               ┌──────────────────────────┐
                               │ live は vN (Blue) のまま │
                               │ CodeDeploy: Failed       │
                               │ → スタックもロールバック │
                               └──────────────────────────┘

  ※ 検証に合格すると、CodeDeploy が live エイリアスを vN → vN+1 に一括で付け替える(AllAtOnce)。
  ※ デプロイ中に us-states-lambda-bg-live-errors アラームが発報した場合も自動ロールバックする。
```

## ディレクトリ構成

| パス | 内容 |
|---|---|
| `src/app.py` / `src/Dockerfile` | 本体のLambda関数(`GET /hello`)。レスポンスに `version` を含む |
| `hooks/pre_traffic.py` / `hooks/Dockerfile` | CodeDeployのPreTrafficフック。切替前にGreenを直接呼び出して検証する |
| `template.yaml` | SAMテンプレート(`AutoPublishAlias: live` + `DeploymentPreference`) |
| `buildspec.yml` | CodeBuild定義(pytest → `sam build` → `sam package` でECRへpush) |
| `tests/` | pytest(本体とフックのユニットテスト) |

## 主要リソース

| 種別 | 名前 |
|---|---|
| CodePipeline | `us-states-lambda-bg-pipeline` |
| CodeBuild | `us-states-lambda-bg-build`(特権モード) |
| ECR | `us-states-lambda-bg-pipeline` |
| S3(パイプラインartifact) | `us-states-lambda-bg-artifacts-<アカウントID>`(packaged.yamlの受け渡しのみ) |
| CloudFormationスタック | `us-states-lambda-bg-stack` |
| Lambda(本体) | `us-states-lambda-bg-sample`(エイリアス `live`) |
| Lambda(フック) | `CodeDeployHook_us-states-lambda-bg-pretraffic` |
| CodeDeploy | スタックが自動作成(`us-states-lambda-bg-stack-ServerlessDeploymentApplication-*`) |
| CloudWatchアラーム | `us-states-lambda-bg-live-errors` |
| IAMロール | `us-states-lambda-bg-codepipeline-role` / `-codebuild-role` / `-cfn-deploy-role` |

## デプロイ方法

1. `main` ブランチにpushする(Webhookで自動起動)。
2. Buildで pytest → イメージビルド → ECRへpush。
3. Approval で承認する。
4. Deployで CloudFormation がスタックを更新し、CodeDeploy が Blue/Green 切替を実行する。

動作確認:

```bash
curl https://<ApiId>.execute-api.ap-northeast-1.amazonaws.com/hello
# {"message": "Hello, World!", "path": "/hello", "version": "v1"}
```

## ローカルでのテスト

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## 注意点

- 初回デプロイ(スタック作成時)はCodeDeployを経由せず、エイリアス `live` が最初のバージョンを直接指す。
  Blue/Green切替・PreTrafficフックが動くのは2回目以降のデプロイから。
- フック関数名は `CodeDeployHook_` で始める必要がある。SAMが作るCodeDeployサービスロール
  (`AWSCodeDeployRoleForLambda`)が呼び出せるのはこの名前の関数だけのため。
- 切替後に旧バージョン(Blue)は削除されずに残る(Lambdaのバージョンとして保持)。
