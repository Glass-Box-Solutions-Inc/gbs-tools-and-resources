import json
import random
import sys

import reportlab
import data.content_pools as content_pools

from tests.render_baseline import render_digest
from tests.test_qme_apportionment_seam import _QME_VARIANTS, _baseline_case, _baseline_spec

MODULE_PATH = "pdf_templates.medical.qme_ame_report"
CLASS_NAME = "QmeAmeReport"


def _payload() -> dict:
    case = _baseline_case()
    digests: dict[str, dict[str, str]] = {}
    for variant_key in sorted(_QME_VARIANTS):
        variant_name = _QME_VARIANTS[variant_key]
        spec = _baseline_spec("QME_REPORT_INITIAL", variant_name, None)
        digests[variant_key] = render_digest(case, MODULE_PATH, CLASS_NAME, spec)

    original_sample = random.sample
    original_shuffle = random.shuffle
    mtus_ordered_trace: list[tuple[str, int, int]] = []

    def patched_sample(population: list[str], k: int) -> list[str]:
        mtus_ordered_trace.append(("sample", len(population), k))
        return original_sample(population, k)

    def patched_shuffle(population: list[str]) -> None:
        mtus_ordered_trace.append(("shuffle", len(population), -1))
        return original_shuffle(population)

    random.sample = patched_sample  # type: ignore[assignment]
    random.shuffle = patched_shuffle  # type: ignore[assignment]
    random.seed(0)
    try:
        content_pools.get_mtus_citations(body_parts=["lumbar", "shoulder", "depression"], count=8)
    finally:
        random.sample = original_sample
        random.shuffle = original_shuffle

    return {
        "python": [sys.version_info[0], sys.version_info[1]],
        "deps": {"reportlab": reportlab.__version__},
        "digests": digests,
        "mtus_ordered_trace": mtus_ordered_trace,
    }


def main() -> None:
    print(json.dumps(_payload(), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
