"""
One-off sanity test: runs the deterministic smallcap pipeline (no LLM) plus
narrate_candidate() (Groq, if configured) against 5 hand-picked symbols
instead of the full 250-stock universe. Not wired into scheduled_scan.py -
purely for a pre-market-open smoke test.
"""
import sys
import time
import traceback

SYMBOLS = ["AARTIIND", "AAVAS", "ACE", "CENTURYPLY", "TRIVENI"]

def main():
    t0 = time.time()
    print(f"[SANITY] Testing {len(SYMBOLS)} symbols: {SYMBOLS}")

    try:
        from agents.smallcap_pipeline.crew import run_deterministic_for_universe, narrate_candidate
    except Exception:
        print("[SANITY] \u274c Import failed:")
        traceback.print_exc()
        sys.exit(1)

    try:
        results = run_deterministic_for_universe(symbols=SYMBOLS, min_score=0)
    except Exception:
        print("[SANITY] \u274c run_deterministic_for_universe raised:")
        traceback.print_exc()
        sys.exit(1)

    print(f"[SANITY] \u2705 Deterministic pass completed in {time.time()-t0:.1f}s, {len(results)} scorecard(s) returned")

    for r in results:
        print(f"  - {r.get('symbol')}: score={r.get('composite_score')} rating={r.get('rating')}")

    if not results:
        print("[SANITY] \u26a0\ufe0f No scorecards returned at all - every symbol likely errored during fetch/analysis. Check output above the summary line.")
        sys.exit(1)

    # Try narration on whichever candidate scored highest, regardless of rating,
    # just to exercise the Groq call path end-to-end.
    best = max(results, key=lambda r: r.get("composite_score", 0))
    print(f"\n[SANITY] Testing narrate_candidate() on highest scorer: {best.get('symbol')}")
    try:
        thesis, status = narrate_candidate(best)
        print(f"[SANITY] narrate_candidate status={status}")
        if thesis:
            print(f"[SANITY] thesis preview: {thesis[:200]}")
    except Exception:
        print("[SANITY] \u274c narrate_candidate raised (should never happen - it catches its own errors):")
        traceback.print_exc()
        sys.exit(1)

    print(f"\n[SANITY] Total time: {time.time()-t0:.1f}s")
    print("[SANITY] \u2705 ALL CHECKS PASSED")

if __name__ == "__main__":
    main()
