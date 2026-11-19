from dataclasses import replace

from lattice.quantization.capabilities import QualityEvidence, WeightFormat, capability


def test_no_bitwidth_aliasing_or_gpu_claim():
    assert capability("llama.cpp", "cpu", WeightFormat.GGUF_Q4).executable_candidate
    assert not capability("llama.cpp", "cpu", WeightFormat.GGUF_Q4).verified
    assert not capability("llama.cpp", "cpu", WeightFormat.BNB_NF4).executable_candidate
    assert not capability("llama.cpp", "cuda", WeightFormat.GGUF_Q4).verified
    assert capability(
        "llama.cpp", "cpu", WeightFormat.GGUF_Q4, frozenset({WeightFormat.GGUF_Q4})
    ).verified


def test_quality_confidence_is_required():
    evidence = QualityEvidence(
        "source", "baseline", "candidate", "dataset", 0.001, None, False
    )
    assert not evidence.qualifies()
    approved = replace(
        evidence, task_score_loss_upper_bound=0.005, representative_held_out=True
    )
    assert approved.qualifies()
    assert not replace(approved, relative_perplexity_change=0.021).qualifies()
    assert not replace(approved, task_score_loss_upper_bound=0.011).qualifies()
