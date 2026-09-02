# -*- coding: utf-8 -*-
"""전 시나리오 실사용 점검

린터는 카드를 정적으로 보고, 이 스크립트는 실제로 뽑아서 나온 결과를 본다.
슬롯 치환 후에야 드러나는 문제 — 남은 {{슬롯}}, 기록용 칸에 섞인 환자 대사,
진찰 소견 칸에 들어간 환자 말투 — 를 잡는다.

    python smoke_all.py            시나리오당 5회
    python smoke_all.py 20         시나리오당 20회
"""
from __future__ import unicode_literals
import io, json, os, re, sys, glob

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample_case as sc

# 환자 구어체 종결어미. 이 칸들은 환자가 답하는 내용이라 구어체 자체는 정상이다.
SPEECH = re.compile(r"(요\.|요$|에요|예요|어요|아요|세요|네요|죠\.|죠$|드려요|같아요|대요|했어|있어|없어)")
# 카드 작성자가 모델에게 거는 지시문. 이게 환자 대사와 한 칸에 섞이면 잘못이다.
INSTRUCTION = re.compile(r"(인물 카드|카드를 따|redFlags|참고한다|그대로 쓴다|고정한다|따른다|덮어쓴다|해당 없으면|변주를 쓴다)")
NOTE_FIELDS = ["pmh", "meds", "allergy", "fh", "sh"]


def scan(case, path, problems):
    """스킬이 실제로 받는 출력(as_json)에서 문제를 찾는다.
    build() 가 돌려주는 scenario 는 아직 치환 전이라 그걸 보면 안 된다."""
    out = sc.as_json(case)
    s = out["scenario"]

    def walk(node, where):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, "%s.%s" % (where, k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (where, i))
        elif isinstance(node, str):
            if "{{" in node:
                problems.append("치환 안 된 슬롯 %s: %s" % (where, node[:50]))

    walk(s, "scenario")
    walk(out["pe"].get("findings") or {}, "findings")
    walk(out["person"], "person")

    # 한 칸에 지시문과 환자 대사가 섞였는지.
    # 지시문은 모델에게 거는 말이고 환자 대사는 학생에게 하는 말이라 섞이면 그대로 읽힌다.
    for f in NOTE_FIELDS:
        val = s.get(f)
        if isinstance(val, str) and INSTRUCTION.search(val) and SPEECH.search(val):
            problems.append("지시문과 환자 대사가 섞임 %s: %s" % (f, val[:52]))

    # 진찰 소견 칸에 환자 말투가 섞였는지 (서술자 톤이어야 한다)
    if not (case.get("_procedure") or case.get("_noPe")):
        for k, v in (out["pe"].get("findings") or {}).items():
            if not isinstance(v, str):
                continue
            if INSTRUCTION.search(v):
                problems.append("진찰 소견에 지시문 '%s': %s" % (k, v[:46]))
            # 정신상태평가 항목은 환자의 말을 그대로 인용하는 것이 정상이다
            MSE = ("사고", "병식", "정동", "기분", "지각", "말투", "판단", "인지", "외모·행동")
            if any(m in k for m in MSE):
                continue
            # 그 외 진찰 소견은 서술자의 말이므로 환자 1인칭 대사가 들어가면 안 된다
            if re.search(r"(제가|저는|아파요|없어요|있어요|같아요)", v):
                problems.append("진찰 소견에 환자 1인칭 대사 '%s': %s" % (k, v[:46]))

    # 첫 대사가 비어 있는지
    if not s.get("opening"):
        problems.append("opening 이 비어 있음")


def main(argv):
    reps = int(argv[0]) if argv else 5
    files = sc.topic_files()
    found = {}
    total = 0

    for topic, data in files:
        procedure = bool(data.get("_procedureCase"))
        no_pe = bool(data.get("_noPhysicalExam"))
        for scen in data["scenarios"]:
            for _ in range(reps):
                case = sc.build(topic, data, scen["id"])
                case["_procedure"] = procedure
                case["_noPe"] = no_pe
                total += 1
                probs = list(case["problems"])
                scan(case, topic, probs)
                for x in probs:
                    key = x.split(":")[0]
                    found.setdefault(key, set()).add("%s/%s · %s" % (topic, scen["id"], x))

    print("시나리오 %d개 · 추첨 %d회" % (sum(len(d["scenarios"]) for _, d in files), total))
    if not found:
        print("문제 0건")
        return 0
    n = sum(len(v) for v in found.values())
    print("문제 %d종" % n)
    for key in sorted(found, key=lambda k: -len(found[k])):
        rows = sorted(found[key])
        print("\n[%s] %d종" % (key, len(rows)))
        for r in rows[:10]:
            print("   %s" % r)
        if len(rows) > 10:
            print("   ... 그 외 %d종" % (len(rows) - 10))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
