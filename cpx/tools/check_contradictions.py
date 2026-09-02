# -*- coding: utf-8 -*-
"""카드 내부 모순 검사기

한 시나리오 안에서 서로 어긋나는 진술을 찾는다. 린터는 형식을, 샘플러는 조합 규칙을 보지만
"음성 소견에는 발열이 없다고 써두고 체온 밴드는 38.5도"처럼 내용끼리 부딪히는 것은 못 잡는다.

    python check_contradictions.py            전체
    python check_contradictions.py 18         파일명 접두사로 좁히기
"""
from __future__ import unicode_literals
import io, json, os, re, sys, glob

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.normpath(os.path.join(HERE, "..", "skills", "start", "refs", "cases"))


def load(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def texts_of(node, out):
    """시나리오 안의 모든 문자열을 모은다. 확률 소견은 양쪽 다 본다."""
    if isinstance(node, dict):
        for v in node.values():
            texts_of(v, out)
    elif isinstance(node, list):
        for v in node:
            texts_of(v, out)
    elif isinstance(node, str):
        out.append(node)
    return out


def has(patterns, blob):
    return any(re.search(p, blob) for p in patterns)


def check(s):
    """모순을 문자열 리스트로 돌려준다."""
    problems = []
    pe = s.get("pe") or {}
    vit = pe.get("vitals") or {}
    assoc = s.get("assoc") or {}
    neg = " / ".join(assoc.get("negative") or [])
    pos = " / ".join(assoc.get("positive") or [])
    findings = " / ".join(texts_of(pe.get("findings") or {}, []))
    body = " / ".join(texts_of({k: v for k, v in s.items()
                                if k not in ("pe", "assoc", "variations")}, []))

    # 1) 음성 소견의 '발열 없음' 과 체온 밴드
    # '고열 없음'·'미열 없음'은 다른 말이므로 제외하고, 상한이 아니라 하한으로 본다.
    # 상한만 보면 미열까지 허용하는 정상적인 밴드가 전부 걸린다.
    if re.search(r"(?<![고미])발열\s*(은|이)?\s*없|(?<![고미])열이\s*없", neg):
        t = vit.get("temp")
        if isinstance(t, list) and t[0] >= 37.5:
            problems.append("음성 소견에 발열 없음인데 체온 밴드 하한이 %s" % t[0])

    # 2) 음성 소견의 '빈맥/두근거림 없음' 과 맥박 밴드
    if re.search(r"빈맥\s*없|두근거림\s*(이)?\s*없", neg):
        h = vit.get("hr")
        if isinstance(h, list) and h[0] >= 100:
            problems.append("음성 소견에 두근거림/빈맥 없음인데 맥박 밴드 하한이 %s" % h[0])

    # 3) 음성 소견의 '다리 부종 없음' 과 진찰 소견의 부종
    # '함요부종 없음'처럼 부정된 문장을 부종 있음으로 읽지 않도록 항목 단위로 본다.
    if re.search(r"(다리|하지|발등)\s*부종\s*(은|이)?\s*없", neg):
        for k, v in (pe.get("findings") or {}).items():
            vals = [v] if isinstance(v, str) else (
                [v.get("detected", ""), v.get("notDetected", "")] if isinstance(v, dict) else [])
            for t in vals:
                neg_words = ("없", "않", "아니")
                if re.search(r"(함요부종|부종|부어)", t or "") and not any(w in (t or "") for w in neg_words):
                    problems.append("음성 소견에 하지 부종 없음인데 진찰 '%s' 에 부종이 있음" % k)

    # 4) 음성 소견의 '체중감소 없음' 과 본문의 체중 감소 서술
    if re.search(r"체중\s*감소\s*(는)?\s*없|살\s*빠지지", neg):
        if re.search(r"체중이\s*\d|kg\s*빠|살이\s*빠", body + findings):
            problems.append("음성 소견에 체중감소 없음인데 본문에 체중 감소 서술이 있음")

    # 5) 음성 소견의 '황달 없음' 과 진찰 소견의 황달
    if re.search(r"황달\s*(은)?\s*없", neg):
        if re.search(r"황달이 있|공막에 (경한 )?황달", findings):
            problems.append("음성 소견에 황달 없음인데 진찰에 황달이 있음")

    # 6) 음성 소견의 '객혈 없음' 과 본문의 객혈
    if re.search(r"(객혈|피 섞인 가래)\s*(은|는)?\s*없", neg):
        if re.search(r"가래에 피가 (비|섞)|객혈이 있", body):
            problems.append("음성 소견에 객혈 없음인데 본문에 객혈 서술이 있음")

    # 7) 저산소혈증 음성인데 산소포화도 밴드가 낮음
    if re.search(r"숨참\s*없|호흡곤란\s*(은)?\s*없", neg):
        sp = vit.get("spo2")
        if isinstance(sp, list) and sp[0] < 94:
            problems.append("음성 소견에 호흡곤란 없음인데 SpO2 밴드 하한이 %s" % sp[0])

    # 8) 먼저 말하는 것과 물어야 나오는 것이 겹침
    disc = s.get("disclosure") or {}
    spont = set(disc.get("spontaneous") or [])
    only = set(disc.get("onlyIfAsked") or [])
    dup = spont & only
    if dup:
        problems.append("먼저 말함과 물어야 나옴이 겹침: %s" % ", ".join(sorted(dup)))

    # 9) 활력징후 밴드가 서로 뒤집힘 (수축기 하한이 이완기 상한보다 낮음)
    sbp, dbp = vit.get("sbp"), vit.get("dbp")
    if isinstance(sbp, list) and isinstance(dbp, list) and sbp[0] <= dbp[1]:
        problems.append("수축기 하한(%s)이 이완기 상한(%s) 이하" % (sbp[0], dbp[1]))

    # 10) 확률 소견인데 양쪽 문장이 사실상 같음
    for k, v in (pe.get("findings") or {}).items():
        if isinstance(v, dict) and v.get("detected") == v.get("notDetected"):
            problems.append("확률 소견의 두 문장이 동일: %s" % k)

    return problems


def main(argv):
    prefix = argv[0] if argv else ""
    files = [p for p in sorted(glob.glob(os.path.join(CASES, "*.json")))
             if os.path.basename(p) not in ("personas.json", "index.json")
             and os.path.basename(p).startswith(prefix)]
    total = 0
    for p in files:
        d = load(p)
        name = os.path.basename(p)
        for s in d.get("scenarios", []):
            probs = check(s)
            if probs:
                total += len(probs)
                print("\n%s / %s  [%s]" % (name, s.get("id"), (s.get("dx") or "")[:34]))
                for x in probs:
                    print("   - %s" % x)
    print("\n파일 %d개 · 모순 %d건" % (len(files), total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
