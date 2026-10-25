import subprocess
import os

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LLAMA_CLI_PATH = rf"{SCRIPT_DIR}/llama-cpp/llama-cpp-cu124/llama-cli.exe"


MODEL_PATH = rf"{SCRIPT_DIR}/models/gguf/Qwen3.8-9B-Q6_K.gguf"


def extract_llama_answer(stdout: str) -> str:
    lines = stdout.splitlines()
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        if line.strip().startswith("> "):
            start_idx = i + 1
        if "Exiting..." in line:
            end_idx = i
            break

    if start_idx is not None and end_idx is not None and start_idx < end_idx:
        answer_lines = lines[start_idx:end_idx]
        return "\n".join(answer_lines).strip()
    else:
        return stdout.strip()


def run_llama_cpp(
    max_token: int = 2048, 
    prompt: str = "hello", 
    reasoning: bool = False
) -> str:
    cmd = [
        LLAMA_CLI_PATH,
        "-m", MODEL_PATH,
        "-ngl", "99",
        "-c", "4096",
        "-n", str(max_token),
        "-st",
        "--simple-io",
        "--no-display-prompt",
        "--no-show-timings",
        "--log-disable",
        "--reasoning", "on" if reasoning else "off",
        "-p", prompt
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )
    stdout, stderr = proc.communicate()

    return extract_llama_answer(stdout)

if __name__ == "__main__":
    answer = run_llama_cpp()
    print(answer)
