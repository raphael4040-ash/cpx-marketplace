# -*- coding: utf-8 -*-
"""plugin.json 과 marketplace.json 의 version 이 같은지 확인한다.

두 파일에 버전이 따로 적혀 있어서, plugin.json 만 올리고 marketplace.json 을
깜빡하면 마켓플레이스 목록에는 예전 버전으로 남는다 — 실제로 1.3.60 배포
때 이 일이 있었다(marketplace.json 이 1.3.59 에 멈춰 있었다). Claude Code 가
업데이트 여부를 마켓플레이스 쪽 버전으로 판단한다면, 이 드리프트가 곧
"올려도 유저에게 업데이트로 안 잡히는" 원인이 된다.
"""
from __future__ import unicode_literals
import json, os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_JSON = os.path.normpath(os.path.join(HERE, "..", ".claude-plugin", "plugin.json"))
MARKETPLACE_JSON = os.path.normpath(os.path.join(HERE, "..", "..", ".claude-plugin", "marketplace.json"))


def main():
    with open(PLUGIN_JSON, "r", encoding="utf-8") as f:
        plugin_version = json.load(f)["version"]

    with open(MARKETPLACE_JSON, "r", encoding="utf-8") as f:
        marketplace = json.load(f)
    entries = [p for p in marketplace.get("plugins", []) if p.get("name") == "cpx"]
    if not entries:
        print("marketplace.json 에 'cpx' 플러그인 항목이 없습니다.")
        return 1
    marketplace_version = entries[0].get("version")

    if plugin_version != marketplace_version:
        print(
            "버전 불일치: plugin.json=%s marketplace.json=%s"
            % (plugin_version, marketplace_version)
        )
        print("marketplace.json 의 plugins[].version 을 plugin.json 과 맞추세요.")
        return 1

    print("버전 일치 (%s)" % plugin_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
