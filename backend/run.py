"""启动脚本：python backend/run.py [--host 127.0.0.1] [--port 8000]"""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="AI 图像工作站后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
