# AI Image Studio

A self-hosted, GPU-accelerated image generation workstation that combines **text-to-image**, **image editing / multi-image fusion**, **upscaling**, and **outpainting** in a single web application — powered by a FastAPI backend and a Vue 3 + TypeScript single-page frontend.

Designed to run on a single consumer GPU (e.g. RTX 3080 20 GB), it serves multiple open-source diffusion models behind one unified task/queue system with live progress via SSE, persistent generation history, and a curated gallery of works.

---

## Screenshots

| Home / Gallery | Text-to-Image |
| --- | --- |
| ![Home](docs/images/screenshot-home.png) | ![Text-to-Image](docs/images/screenshot-text-to-image.png) |

| Image Editing | Upscaling |
| --- | --- |
| ![Image Editing](docs/images/screenshot-edit.png) | ![Upscaling](docs/images/screenshot-upscale.png) |

---

## Features

### 🎨 Text-to-Image
- **7 generation models** selectable at runtime: Qwen-Image-2.1, ERNIE-Image Turbo (INT8), Lumina-Image 2.0, MOSS-Image SFT, FLUX.2 [klein] 4B, Z-Image Turbo, SANA-Sprint 1.6B.
- Canvas presets (1:1, 2:3, 3:4, 16:9, 9:16) **plus custom resolution** with 32-multiple validation and a 2048 px cap.
- Negative prompt, sampling steps, seed, and work **category** tags.
- **AI prompt optimization** (local LLM) and **random prompt** generator.

### 🖌️ Image Editing
- **Single-image editing** by natural-language instruction.
- **Multi-image fusion** — up to 9 reference images arranged in a 9-grid uploader, merged by prompt.
- Model selector restricted to models that support editing; before/after comparison display.

### 🔍 Image Upscaling
- **Engine**: Real-ESRGAN (fast ncnn-vulkan super-resolution, seconds, no CUDA VRAM) with 2x / 3x / 4x.
- Interactive **before/after slider** comparison (original left, upscaled right).


### 🖼️ Outpainting
- Instruction-based image expansion beyond the original canvas.

### 🗂️ Works Gallery & History
- Curated home gallery with category filtering, pin/unpin, and per-image category editing.
- Per-tool generation history with parameters, elapsed time, model, and size; click to restore preview and parameters; left/right keyboard navigation.

### ⚙️ Task System
- Single-worker task queue with **SSE live progress**, queued/running/succeeded/failed states, model hot-loading/unloading to keep VRAM within limits, and persistence across restarts.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12 · FastAPI · uvicorn · Pydantic v2 |
| Inference | PyTorch 2.11 (CUDA 12.8) · Transformers · Diffusers · bitsandbytes (int4/int8) |
| Frontend | Vue 3 · TypeScript · Vite · Vue Router · Pinia |
| Storage | Local JSON stores (works/gallery/history) + filesystem outputs |
| Models | Hugging Face / ModelScope checkpoints (local, no external API) |

---

## Environment Setup (from scratch)

### 1. Prerequisites

- **GPU**: NVIDIA RTX 3080 / 3090 (20–24 GB VRAM) or better, with recent drivers.
- **OS**: Windows 10/11 (or Linux) — the verified setup below is for Windows + PowerShell.
- **Software**: Python **3.12+**, Node.js **18+** / npm, Git.

### 2. Backend environment

```powershell
# create virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install CUDA build of PyTorch first (Windows PyPI default is CPU-only)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

# then the rest of the dependencies
pip install -r requirements.txt
```

`requirements.txt` includes: transformers ≥5.17, diffusers ≥0.41, accelerate, pillow, huggingface_hub, einops, omegaconf, mediapy, opencv-python, rotary-embedding-torch, modelscope, pytest.

### 3. Download model weights

Place model checkpoints under the project `models/` directory. The backend resolves each model from `backend/app/config.py` (e.g. `models/Qwen-Image-2.1`). Models can be pulled with ModelScope CLI:

```powershell
pip install modelscope
modelscope download --model <model-id> --local_dir models\<Model-Name>
```

Required models:

| Directory (`models/`) | Model |
| --- | --- |
| `Qwen-Image-2.1` | Qwen-Image-2.1 (text-to-image, editing) |
| `ERNIE-Image-INT8` | ERNIE-Image Turbo (INT8) |
| `Lumina-Image-2.0` | Lumina-Image 2.0 |
| `MOSS-Image-SFT` | MOSS-Image SFT |
| `FLUX.2-klein-4B` | FLUX.2 [klein] 4B |
| `Z-Image-Turbo` | Z-Image Turbo |
| `Sana-Sprint-1.6B` | SANA-Sprint 1.6B |
| `Qwen3.5-4B-Instruct` | Local LLM for prompt optimization |


### 4. Frontend

```powershell
cd frontend
npm install
npm run build      # production build into frontend/dist
# or
npm run dev        # dev server with HMR (default http://localhost:5173)
```

### 5. Run the backend

```powershell
cd backend
$env:PYTHONPATH = "E:\path\to\project\.venv\Lib\site-packages;E:\path\to\project\backend"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Open **http://localhost:8001** — the frontend is served from `frontend/dist` by the same backend (single-port deployment).

> Note: `config.py` defaults to port 8000; the verified run command above uses 8001. Either works — just keep the port consistent.

### 6. Sanity check

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/health
# {"status":"ok","version":"0.1.0"}

Invoke-RestMethod http://127.0.0.1:8001/api/models
# -> model list with loaded state and GPU stats
```

---

## API Overview

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/models` | Model list, GPU/VRAM stats, load state |
| GET | `/api/models/stats` | Inference statistics |
| POST | `/api/tasks/text-to-image` | Submit text-to-image generation |
| POST | `/api/tasks/edit` | Submit image editing / multi-image fusion (multipart) |
| POST | `/api/tasks/outpaint` | Submit outpainting |
| POST | `/api/tasks/upscale` | Submit upscaling (Real-ESRGAN) |
| GET | `/api/tasks` | List tasks |
| GET | `/api/tasks/{task_id}` | Task detail (status, progress, outputs, elapsed) |
| GET | `/api/tasks/{task_id}/events` | SSE progress stream |
| GET | `/api/outputs` | List output batches |
| GET | `/api/outputs/{stamp}/{image}` | Serve generated images |
| POST | `/api/gallery/pin` / `/unpin` | Pin / unpin a work to the home gallery |
| POST | `/api/gallery/category` | Update a work's category |
| POST | `/api/prompt/optimize` | LLM prompt optimization |
| POST | `/api/prompt/random` | Random prompt suggestion |

---

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry (static frontend mount)
│   │   ├── config.py            # paths, ports, limits
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── task_manager.py      # task queue + SSE progress
│   │   ├── routers/             # models / tasks / outputs / gallery / prompt
│   │   └── services/            # per-model inference services
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/               # Home, TextToImage, EditImage, Upscale, Outpaint
│   │   ├── components/          # ModelSelector, HistoryGallery, BeforeAfterSlider, ...
│   │   ├── router/ · stores/ · api/ · utils/ · types/
│   └── package.json
├── models/                      # local model checkpoints (git-ignored)
├── outputs/                     # generated images, batched by timestamp
├── db/                          # JSON stores (works / gallery / history)
├── utils/                       # model utility wrappers (qwen_21_util, realesrgan_util, ...)
├── docs/                        # integration & operation notes
└── tests/
```

---

## Configuration

Key settings in `backend/app/config.py`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `OUTPUT_DIR` | `outputs/` | Generated image output root |
| `MAX_UPLOAD_MB` | 20 | Upload size limit per file |
| `MAX_TASK_PIXELS` | 4,000,000 | Max generation area to prevent OOM |
| `HOST` / `PORT` | 127.0.0.1 / 8000 | Server defaults (override via uvicorn args) |

---

## Notes & License

- The project is a local research/development workstation; all models are third-party open-weight checkpoints subject to their own licenses (Apache-2.0 / Community / model-specific). Verify commercial-use terms before production use.
- Generated images are stored under `outputs/<timestamp>/` with a sidecar `input_prompt.txt` recording the prompt, model, and parameters.
- Refer to `docs/` for integration history and troubleshooting notes of each model (e.g. Real-ESRGAN, Lumina-Image 2.0, HiDream).
