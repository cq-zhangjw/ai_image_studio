"""AI 图像工作站 · 后端配置。"""

from pathlib import Path

# 项目根：backend/app/config.py -> parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_DIR = PROJECT_ROOT / "outputs"
UPLOAD_DIR = OUTPUT_DIR / "_uploads"
DB_DIR = PROJECT_ROOT / "db"
MODEL_ROOT = PROJECT_ROOT / "models"
QWEN_MODEL_DIR = MODEL_ROOT / "Qwen-Image-2.1"
ERNIE_MODEL_DIR = MODEL_ROOT / "ERNIE-Image-INT8"  # INT8 (quanto) 量化版，8B DiT + Mistral3 TE（docs/17、docs/21）
LUMINA_MODEL_DIR = MODEL_ROOT / "Lumina-Image-2.0"  # Alpha-VLLM Lumina 2.0，2.6B DiT + Gemma-2-2B TE（docs/21）
MOSS_MODEL_DIR = MODEL_ROOT / "MOSS-Image-SFT"  # OpenMOSS 5B DiT + Qwen3.5-9B TE（docs/18）
FLUX2_MODEL_DIR = MODEL_ROOT / "FLUX.2-klein-4B"
Z_IMAGE_MODEL_DIR = MODEL_ROOT / "Z-Image-Turbo"
SANA_SPRINT_MODEL_DIR = MODEL_ROOT / "Sana-Sprint-1.6B"
LLM_MODEL_DIR = MODEL_ROOT / "Qwen3.5-4B-Instruct"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

HOST = "127.0.0.1"
PORT = 8000

MAX_UPLOAD_MB = 20
MAX_TASK_PIXELS = 4_000_000  # 生成图面积上限，防 OOM
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

