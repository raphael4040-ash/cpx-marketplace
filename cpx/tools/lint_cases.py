# -*- coding: utf-8 -*-
"""케이스 카드 스키마 린터

카드가 채점표(checklist.md)를 채울 수 있는 형태인지 기계적으로 검사한다.
임상적 타당성은 사람이 봐야 하지만, 필드 누락과 형식 어긋남은 여기서 잡는다.

    python lint_cases.py            전체 검사
    python lint_cases.py 21         파일명이 21 로 시작하는 것만
"""
from __future__ import unicode_literals
import io, json, os, re, sys, glob

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.normpath(os.path.join(HERE, "..", "skills", "start", "refs", "cases"))

TOP_REQUIRED = ["topicId", "topic", "scenarios"]
SC_REQUIRED = ["id", "dx", "constraints", "opening", "hpi", "assoc",
               "redFlags", "pmh", "meds", "allergy", "fh", "sh",
               "variations", "disclosure"]
HPI_REQUIRED = ["onset", "character", "aggravating", "relieving", "severity", "course"]
VITAL_KEYS = ["sbp", "dbp", "hr", "rr", "temp", "spo2"]

# 상담·술기 카드는 신체진찰이 없거나 구조가 다르다. 이 표식이 있으면 pe 검사를 건너뛴다.
EXEMPT_FLAGS = ["_noPhysicalExam", "_procedureCase"]


def load(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def slots_used(node, out):
    if isinstance(node, dict):
        for v in node.values():
            slots_used(v, out)
    elif isinstance(node, list):
        for v in node:
            slots_used(v, out)
    elif isinstance(node, str):
        out.update(re.findall(r"\{\{(\w+)\}\}", node))
    return out


def check_file(path):
    name = os.path.basename(path)
    errs, warns = [], []
    try:
        d = load(path)
    except Exception as e:
        return name, ["JSON 파싱 실패: %s" % e], []

    for k in TOP_REQUIRED:
        if k not in d:
            errs.append("최상위 필드 누락: %s" % k)
    if not d.get("scenarios"):
        return name, errs + ["시나리오가 없음"], warns

    exempt = any(d.get(f) for f in EXEMPT_FLAGS)
    if not exempt and "_peRules" not in d:
        warns.append("_peRules 없음")

    ids = set()
    for i, s in enumerate(d["scenarios"]):
        tag = "%s#%d" % (s.get("id", "?"), i)

        if s.get("id") in ids:
            errs.append("%s: id 중복" % tag)
        ids.add(s.get("id"))

        for k in SC_REQUIRED:
            if k not in s:
                # 술기 카드는 dx 대신 situation 을 쓴다
                if k == "dx" and "situation" in s:
                    continue
                # 상담·술기 카드는 병력청취 구조 자체가 없다
                if exempt and k in ("hpi", "assoc", "redFlags", "pmh", "meds", "allergy", "fh", "sh"):
                    continue
                errs.append("%s: 필드 누락 %s" % (tag, k))

        c = s.get("constraints") or {}
        if "ageRange" not in c or len(c.get("ageRange", [])) != 2:
            errs.append("%s: constraints.ageRange 형식 오류" % tag)
        else:
            lo, hi = c["ageRange"]
            if lo > hi:
                errs.append("%s: ageRange 상하한 뒤바뀜" % tag)
            if lo < 0 or hi > 100:
                warns.append("%s: ageRange 가 이상함 (%s~%s)" % (tag, lo, hi))
        if c.get("sex") not in ("any", "male", "female", None):
            errs.append("%s: constraints.sex 값 오류 (%s)" % (tag, c.get("sex")))
        if c.get("requiredRisk") and not c.get("requiredRiskMin"):
            warns.append("%s: requiredRisk 는 있는데 requiredRiskMin 이 0" % tag)

        # 상담·술기 카드는 병력청취 구조가 없으므로 아래 검사를 건너뛴다
        if not exempt:
            hpi = s.get("hpi") or {}
            for k in HPI_REQUIRED:
                if not hpi.get(k):
                    warns.append("%s: hpi.%s 비어 있음" % (tag, k))

            assoc = s.get("assoc") or {}
            if not assoc.get("positive"):
                warns.append("%s: assoc.positive 없음" % tag)
            if not assoc.get("negative"):
                warns.append("%s: assoc.negative 없음 — 음성 소견이 없으면 감별 문진이 채점되지 않는다" % tag)

            if len(s.get("redFlags") or {}) < 4:
                warns.append("%s: redFlags 가 4개 미만" % tag)

        # informant 가 문자열이면 보호자 관계 자리에 설명문이 통째로 찍힌다
        info = s.get("informant")
        if info is not None and not isinstance(info, dict):
            errs.append("%s: informant 는 relation 을 가진 객체여야 한다" % tag)
        elif isinstance(info, dict) and not info.get("relation"):
            errs.append("%s: informant.relation 없음" % tag)

        disc = s.get("disclosure") or {}
        if not disc.get("onlyIfAsked"):
            warns.append("%s: disclosure.onlyIfAsked 없음 — 물어야 나오는 정보가 없으면 문진 난이도가 사라진다" % tag)

        pe = s.get("pe") or {}
        if not exempt:
            if not pe:
                errs.append("%s: pe 없음" % tag)
            else:
                v = pe.get("vitals")
                if not isinstance(v, dict):
                    errs.append("%s: pe.vitals 가 밴드 형식이 아님" % tag)
                else:
                    for k in VITAL_KEYS:
                        band = v.get(k)
                        if not isinstance(band, list) or len(band) != 2:
                            errs.append("%s: vitals.%s 밴드 형식 오류" % (tag, k))
                        elif band[0] > band[1]:
                            errs.append("%s: vitals.%s 상하한 뒤바뀜" % (tag, k))
                    if not v.get("invariant"):
                        warns.append("%s: vitals.invariant 없음" % tag)
                for key, val in (pe.get("findings") or {}).items():
                    if isinstance(val, dict):
                        pv = val.get("p")
                        if not isinstance(pv, (int, float)) or not (0 < pv < 1):
                            errs.append("%s: 확률 소견 p 값 오류 (%s)" % (tag, key))
                        if not val.get("detected") or not val.get("notDetected"):
                            errs.append("%s: 확률 소견에 detected/notDetected 누락 (%s)" % (tag, key))
                # 확률 소견만으로 진단이 걸려 있으면 절반의 세션에서 진찰이 통째로 정상이 된다.
                # 항상 나오는 확정 단서를 반드시 명시하게 한다.
                if any(isinstance(v, dict) for v in (pe.get("findings") or {}).values()):
                    core = pe.get("_deterministicCore") or []
                    if not core:
                        errs.append("%s: 확률 소견이 있는데 _deterministicCore 가 없음" % tag)
                    else:
                        for c in core:
                            if c not in (pe.get("findings") or {}):
                                errs.append("%s: _deterministicCore 의 '%s' 가 findings 에 없음" % (tag, c))
                if len(pe.get("findings") or {}) < 5:
                    warns.append("%s: pe.findings 가 5개 미만 — 학생이 시도할 진찰을 덮지 못한다" % tag)

        # 변주 값 안에 또 슬롯이 들어 있으면 치환이 한 번에 끝나지 않아
        # 학생에게 {{side}} 같은 글자가 그대로 노출된다.
        for vkey, pool in (s.get("variations") or {}).items():
            if not isinstance(pool, list):
                continue
            for item in pool:
                text = str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for nested in re.findall(r"\{\{(\w+)\}\}", text):
                    errs.append("%s: variations.%s 값 안에 {{%s}} 가 중첩되어 있음"
                                % (tag, vkey, nested))

        # {{슬롯}} 이 variations 에 정의돼 있는지
        used = slots_used({k: v for k, v in s.items() if k != "variations"}, set())
        declared = set((s.get("variations") or {}).keys())
        for miss in sorted(used - declared):
            errs.append("%s: {{%s}} 이 variations 에 없음" % (tag, miss))
        for unused in sorted(declared - used):
            warns.append("%s: variations.%s 가 쓰이지 않음" % (tag, unused))

    return name, errs, warns


def main(argv):
    prefix = argv[0] if argv else ""
    files = [p for p in sorted(glob.glob(os.path.join(CASES, "*.json")))
             if os.path.basename(p) not in ("personas.json", "index.json")
             and os.path.basename(p).startswith(prefix)]
    if not files:
        print("검사할 파일이 없습니다.")
        return 1

    total_e = total_w = 0
    scen = 0
    for p in files:
        name, errs, warns = check_file(p)
        try:
            scen += len(load(p).get("scenarios", []))
        except Exception:
            pass
        total_e += len(errs)
        total_w += len(warns)
        if errs or warns:
            print("\n%s" % name)
            for e in errs:
                print("  [오류] %s" % e)
            for w in warns[:12]:
                print("  [경고] %s" % w)
            if len(warns) > 12:
                print("  [경고] ... 그 외 %d건" % (len(warns) - 12))

    print("\n파일 %d개 · 시나리오 %d개 · 오류 %d건 · 경고 %d건"
          % (len(files), scen, total_e, total_w))
    return 1 if total_e else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
