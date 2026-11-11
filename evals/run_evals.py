
"""Chạy và chấm eval. expected chỉ cung cấp cho judge, không gửi cho agent."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import run_agent
from providers import Provider
from scenarios import ScenarioTools
from grading import grade_case, summarize, bonus_points
from bonus.tools import BonusTools

load_dotenv(dotenv_path=ROOT / ".env")


def run_case(case, args):
    """Chạy một case và chấm kết quả."""

    try:
        tools = (
             BonusTools(
        "snapshot",
        scenario=case.get("scenario", "normal")
                )
                if getattr(args, "bonus", False)
                else ScenarioTools(
                    case.get("scenario", "normal"),
                    case.get("fail", False)
                )
        )

        result = run_agent(
            case["question"],
            Provider(args.provider, args.model),
            tools,
            max_steps=args.max_steps
        )

    except Exception as exc:
        result = {
            "status": "error",
            "answer": "",
            "trace": [],
            "usage": [],
            "error": f"{type(exc).__name__}: {str(exc)[:200]}"
        }

    if not isinstance(result, dict) or not isinstance(
        result.get("trace", []), list
    ):
        result = {
            "status": "error",
            "answer": "",
            "trace": [],
            "usage": [],
            "error": "run_agent trả kết quả không hợp lệ."
        }

    try:
        judge = Provider(
            args.judge_provider,
            args.judge_model
        )
        grade = grade_case(case, result, judge)

    except Exception as exc:
        grade = {
            "score": None,
            "status": "unscored",
            "reason": str(exc),
            "judge_usage": {}
        }

    return {
        "id": case["id"],
        "question": case["question"],
        "expected": case["expected"],
        "scenario": case.get("scenario", "normal"),
        "provider": args.provider,
        "model": args.model,
        "judge_provider": args.judge_provider,
        "judge_model": args.judge_model,
        "result": result,
        "grade": grade
    }


def main():
    parser = argparse.ArgumentParser(
        description="Chạy agent và chấm eval 0–100"
    )

    choices = [
        "openai",
        "gemini",
        "anthropic",
        "openrouter"
    ]

    parser.add_argument(
        "--provider",
        choices=choices,
        default=os.getenv("PROVIDER", "openai")
    )

    parser.add_argument(
        "--model",
        default=os.getenv("MODEL")
    )

    parser.add_argument(
        "--judge-provider",
        choices=choices,
        default=os.getenv("JUDGE_PROVIDER")
    )

    parser.add_argument(
        "--judge-model",
        default=os.getenv("JUDGE_MODEL")
    )

    parser.add_argument(
        "--bonus",
        action="store_true",
        help="Chạy bộ bonus riêng"
    )

    parser.add_argument(
        "--case",
        help="Chạy riêng một case, ví dụ H7"
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=None
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Số case chạy đồng thời, mặc định 1"
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0,
        help="Thời gian nghỉ giữa các case; mặc định 0 giây"
    )

    parser.add_argument(
        "--output",
        default="eval_results.json"
    )

    args = parser.parse_args()

    args.judge_provider = (
        args.judge_provider or args.provider
    )

    args.judge_model = (
        args.judge_model or args.model
    )

    if not args.model or not args.judge_model:
        parser.error("Thiếu --model hoặc MODEL")

    args.max_steps = (
        args.max_steps
        if args.max_steps is not None
        else (16 if args.bonus else 8)
    )

    if args.max_steps < 1:
        parser.error("--max-steps phải >= 1")

    if not 1 <= args.workers <= 8:
        parser.error("--workers phải từ 1 đến 8")

    if args.delay < 0:
        parser.error("--delay không được âm")

    if args.delay > 0 and args.workers != 1:
        parser.error(
            "Khi sử dụng --delay, hãy đặt --workers 1"
        )

    cases_path = (
        ROOT / "bonus" / "cases.json"
        if args.bonus
        else Path(__file__).parent / "cases.json"
    )

    cases = json.loads(
        cases_path.read_text(encoding="utf-8")
    )

    selected = [
        case for case in cases
        if not args.case
        or case["id"] == args.case.upper()
    ]

    if not selected:
        parser.error("Không tìm thấy case")

    def run_and_print(case):
        print(
            f"Đang chạy {case['id']}",
            flush=True
        )

        item = run_case(case, args)

        print(
            f"{case['id']}: "
            f"{item['grade'].get('score')} "
            f"({item['grade']['status']})",
            flush=True
        )

        return item

    # Chạy tuần tự khi có delay.
    if args.delay > 0:
        results = []

        for index, case in enumerate(selected):

            if index > 0:
                print(
                    f"Nghỉ {args.delay} giây...",
                    flush=True
                )
                time.sleep(args.delay)

            results.append(run_and_print(case))

    # Chạy không nghỉ giữa các case.
    else:
        with ThreadPoolExecutor(
            max_workers=args.workers
        ) as pool:
            results = list(
                pool.map(run_and_print, selected)
            )

    report = {
        "summary": summarize(results),
        "config": {
            "provider": args.provider,
            "model": args.model,
            "judge_provider": args.judge_provider,
            "judge_model": args.judge_model,
            "max_steps": args.max_steps,
            "dataset": (
                "bonus" if args.bonus else "core"
            )
        },
        "cases": results
    }

    summary = report["summary"]

    if args.bonus:
        full_run = (
            not args.case
            and len(selected) == len(cases)
        )

        report["summary"]["bonus_points_0_15"] = (
            bonus_points(
                summary["score_0_100"],
                full_run
            )
        )

        print(
            "Điểm bonus tham khảo: "
            f"{summary['bonus_points_0_15']}/15"
        )

    Path(args.output).write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )

    print(
        f"Điểm: {summary['score_0_100']}/100; "
        f"đã chấm "
        f"{summary['scored_cases']}/"
        f"{summary['total_cases']} case. "
        f"File: {args.output}"
    )

    if summary["score_0_100"] is None:
        print(
            "Chưa có điểm tổng do có case chưa "
            "được chấm; xem reason trong file.",
            file=sys.stderr
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
