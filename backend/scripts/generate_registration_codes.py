"""生成内测码与服务器摘要配置，仅输出结果，不连接或修改数据库。"""

import argparse
import hashlib
import json
import secrets


def main() -> None:
    """按指定数量和单码上限生成随机码，不把明文放进服务器配置。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.count <= 100 or args.limit < 1:
        parser.error("码数量应为 1–100，单码上限应大于零。")
    codes = [secrets.token_urlsafe(18) for _ in range(args.count)]
    print("请私密保存并分发以下内测码：")
    for code in codes:
        print(code)
    limits = {hashlib.sha256(code.encode()).hexdigest(): args.limit for code in codes}
    print("服务器环境变量（只含摘要）：")
    print("REGISTRATION_CODE_REQUIRED=true")
    print("REGISTRATION_CODE_LIMITS=" + json.dumps(limits, separators=(",", ":")))


if __name__ == "__main__":
    main()
