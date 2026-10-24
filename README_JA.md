# AI Image Studio（AI 画像ワークステーション）

セルフホスト型・GPU アクセラレーションの画像生成ワークステーションです。**テキストから画像生成**、**画像編集 / 複数画像の融合**、**画像アップスケーリング**、**画像拡張（Outpainting）**を 1 つの Web アプリケーションに統合。FastAPI バックエンドと Vue 3 + TypeScript のシングルページフロントエンドで構成されています。

単一のコンシューマー向け GPU（例: RTX 3080 20GB）向けに設計されており、複数のオープンソース拡散モデルを 1 つのタスク/キューメカニズムの下で運用。SSE によるリアルタイム進捗、永続化された生成履歴、キュレーション可能な作品ギャラリーを備えています。

---

## スクリーンショット

| ホーム / ギャラリー | テキストから画像生成 |
| --- | --- |
| ![ホーム](docs/images/screenshot-home.png) | ![テキストから画像生成](docs/images/screenshot-text-to-image.png) |

| 画像編集 | 画像アップスケーリング |
| --- | --- |
| ![画像編集](docs/images/screenshot-edit.png) | ![画像アップスケーリング](docs/images/screenshot-upscale.png) |

---

## 機能

### 🎨 テキストから画像生成
- 実行時に切り替え可能な **7 つの生成モデル**: Qwen-Image-2.1、ERNIE-Image Turbo（INT8）、Lumina-Image 2.0、MOSS-Image SFT、FLUX.2 [klein] 4B、Z-Image Turbo、SANA-Sprint 1.6B。
- キャンバスプリセット（1:1、2:3、3:4、16:9、9:16）**およびカスタム解像度**（32 の倍数で検証、上限 2048px）。
- ネガティブプロンプト、サンプリングステップ、シード、作品**カテゴリ**タグ。
- **AI プロンプト最適化**（ローカル LLM）と**ランダムプロンプト**生成。

### 🖌️ 画像編集
- 自然言語の指示による**単一画像編集**。
- **複数画像の融合**——9 マスグリッドで最大 9 枚の参照画像をアップロードし、プロンプトで合成。
- モデルセレクターは編集対応モデルのみを表示。編集前後の比較表示。

### 🔍 画像アップスケーリング
- **エンジン**: Real-ESRGAN（ncnn-vulkan による高速超解像、数秒、CUDA VRAM 不使用）。2x / 3x / 4x に対応。
- インタラクティブな**前後比較スライダー**（左: 元画像、右: 拡大画像）。

### 🖼️ 画像拡張（Outpainting）
- 指示に基づき、元キャンバスの外側へ画像を拡張。

### 🗂️ 作品ギャラリーと履歴
- キュレーション可能なホームギャラリー: カテゴリフィルタ、ピン留め/解除、画像ごとのカテゴリ編集。
- ツールごとの生成履歴: パラメータ、所要時間、モデル、サイズ。クリックでプレビューとパラメータを復元、左右キーで高速切り替え。

### ⚙️ タスクシステム
- シングルワーカーのタスクキュー、**SSE リアルタイム進捗**、待機中/実行中/成功/失敗の状態。モデルは必要に応じてロード/アンロードされ VRAM を制御。再起動後もタスク状態を保持。

---

## 技術スタック

| レイヤー | 技術 |
| --- | --- |
| バックエンド | Python 3.12 · FastAPI · uvicorn · Pydantic v2 |
| 推論 | PyTorch 2.11（CUDA 12.8）· Transformers · Diffusers · bitsandbytes（int4/int8） |
| フロントエンド | Vue 3 · TypeScript · Vite · Vue Router · Pinia |
| ストレージ | ローカル JSON ストア（作品/ギャラリー/履歴）+ ファイルシステム出力 |
| モデル | Hugging Face / ModelScope のチェックポイント（ローカル実行、外部 API なし） |

---

## 環境構築手順（ゼロから）

### 1. 前提条件

- **GPU**: NVIDIA RTX 3080 / 3090（20–24GB VRAM）以上、新しいドライバ。
- **OS**: Windows 10/11（または Linux）——以下は Windows + PowerShell での実証済み手順。
- **ソフトウェア**: Python **3.12+**、Node.js **18+** / npm、Git。

### 2. バックエンド環境

```powershell
# 仮想環境の作成
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 最初に PyTorch の CUDA 版をインストール（Windows の PyPI はデフォルトで CPU 版）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

# 残りの依存関係
pip install -r requirements.txt
```

`requirements.txt` の内容: transformers ≥5.17、diffusers ≥0.41、accelerate、pillow、huggingface_hub、einops、omegaconf、mediapy、opencv-python、rotary-embedding-torch、modelscope、pytest。

### 3. モデル重みのダウンロード

モデルのチェックポイントはプロジェクトの `models/` ディレクトリに配置します。バックエンドは `backend/app/config.py` から各モデルのパスを解決します（例: `models/Qwen-Image-2.1`）。ModelScope CLI でダウンロード可能:

```powershell
pip install modelscope
modelscope download --model <model-id> --local_dir models\<モデルディレクトリ名>
```

必要なモデル:

| ディレクトリ（`models/`） | モデル |
| --- | --- |
| `Qwen-Image-2.1` | Qwen-Image-2.1（テキスト→画像、編集） |
| `ERNIE-Image-INT8` | ERNIE-Image Turbo（INT8） |
| `Lumina-Image-2.0` | Lumina-Image 2.0 |
| `MOSS-Image-SFT` | MOSS-Image SFT |
| `FLUX.2-klein-4B` | FLUX.2 [klein] 4B |
| `Z-Image-Turbo` | Z-Image Turbo |
| `Sana-Sprint-1.6B` | SANA-Sprint 1.6B |
| `Qwen3.5-4B-Instruct` | ローカル LLM（プロンプト最適化） |


### 4. フロントエンド

```powershell
cd frontend
npm install
npm run build      # 本番ビルド → frontend/dist
# または
npm run dev        # 開発サーバー（デフォルト http://localhost:5173）
```

### 5. バックエンドの起動

```powershell
cd backend
$env:PYTHONPATH = "E:\プロジェクト\への\パス\.venv\Lib\site-packages;E:\プロジェクト\への\パス\backend"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

**http://localhost:8001** を開きます——フロントエンドは同じバックエンドが `frontend/dist` から配信します（単一ポートデプロイ）。

> 注: `config.py` のデフォルトポートは 8000。上記の実証済みコマンドでは 8001 を使用していますが、どちらでも構いません——一貫させてください。

### 6. 動作確認

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/health
# {"status":"ok","version":"0.1.0"}

Invoke-RestMethod http://127.0.0.1:8001/api/models
# -> モデル一覧（ロード状態と GPU/VRAM 統計）
```

---

## API 概要

| メソッド | パス | 説明 |
| --- | --- | --- |
| GET | `/api/health` | ヘルスチェック |
| GET | `/api/models` | モデル一覧、GPU/VRAM 統計、ロード状態 |
| GET | `/api/models/stats` | 推論統計 |
| POST | `/api/tasks/text-to-image` | テキスト→画像生成タスクを送信 |
| POST | `/api/tasks/edit` | 画像編集 / 複数画像融合を送信（multipart） |
| POST | `/api/tasks/outpaint` | 画像拡張タスクを送信 |
| POST | `/api/tasks/upscale` | アップスケーリングを送信（Real-ESRGAN） |
| GET | `/api/tasks` | タスク一覧 |
| GET | `/api/tasks/{task_id}` | タスク詳細（状態、進捗、出力、所要時間） |
| GET | `/api/tasks/{task_id}/events` | SSE 進捗ストリーム |
| GET | `/api/outputs` | 出力バッチ一覧 |
| GET | `/api/outputs/{stamp}/{image}` | 生成画像の配信 |
| POST | `/api/gallery/pin` / `/unpin` | 作品のピン留め / 解除 |
| POST | `/api/gallery/category` | 作品カテゴリの更新 |
| POST | `/api/prompt/optimize` | LLM プロンプト最適化 |
| POST | `/api/prompt/random` | ランダムプロンプト |

---

## プロジェクト構造

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI エントリポイント（静的フロントエンドをマウント）
│   │   ├── config.py            # パス、ポート、制限
│   │   ├── schemas.py           # Pydantic リクエスト/レスポンスモデル
│   │   ├── task_manager.py      # タスクキュー + SSE 進捗
│   │   ├── routers/             # models / tasks / outputs / gallery / prompt
│   │   └── services/            # モデルごとの推論サービス
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/               # Home、TextToImage、EditImage、Upscale、Outpaint
│   │   ├── components/          # ModelSelector、HistoryGallery、BeforeAfterSlider など
│   │   ├── router/ · stores/ · api/ · utils/ · types/
│   └── package.json
├── models/                      # ローカルモデル重み（バージョン管理外）
├── outputs/                     # 生成画像（タイムスタンプごとにバッチ化）
├── db/                          # JSON ストア（作品 / ギャラリー / 履歴）
├── utils/                       # モデルユーティリティ（qwen_21_util、realesrgan_util など）
├── docs/                        # 導入・運用メモ
└── tests/
```

---

## 設定

`backend/app/config.py` の主要設定:

| 設定 | デフォルト | 意味 |
| --- | --- | --- |
| `OUTPUT_DIR` | `outputs/` | 生成画像の出力ルート |
| `MAX_UPLOAD_MB` | 20 | 1 ファイルあたりのアップロード上限 |
| `MAX_TASK_PIXELS` | 4,000,000 | 生成面積の上限（OOM 防止） |
| `HOST` / `PORT` | 127.0.0.1 / 8000 | サーバーのデフォルト（uvicorn 引数で上書き可能） |

---

## 備考とライセンス

- 本プロジェクトはローカル研究・開発用ワークステーションです。使用するモデルはすべてサードパーティのオープンウェイトであり、それぞれのライセンス（Apache-2.0 / Community / モデル固有の条項）が適用されます。本番利用前に商用利用条件を確認してください。
- 生成画像は `outputs/<タイムスタンプ>/` に保存され、プロンプト・モデル・パラメータを記録した `input_prompt.txt` が同梱されます。
- 各モデルの導入経緯とトラブルシューティングは `docs/` ディレクトリを参照（Real-ESRGAN、Lumina-Image 2.0、HiDream など）。
