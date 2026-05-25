from learnbuddy_core.evaluator import normalize_answer, answer_variants, evaluate_answer


def test_normalize_answer_trims_case_and_punctuation():
    assert normalize_answer("  Noodle! ") == "noodle"


def test_answer_variants_accept_aliases():
    variants = answer_variants("noodle", aliases=["noodles", " pasta "])
    assert variants == ["noodle", "noodles", "pasta"]


def test_correct_answer_finishes_without_exhaustion():
    result = evaluate_answer("Noodles", answer="noodle", aliases=["noodles"], previous_attempts=1, max_attempts=3)
    assert result.correct is True
    assert result.attempts == 2
    assert result.exhausted is False


def test_third_wrong_attempt_exhausts_and_mentions_solution():
    result = evaluate_answer("wrong", answer="noodle", previous_attempts=2, max_attempts=3)
    assert result.correct is False
    assert result.attempts == 3
    assert result.exhausted is True
    assert "Alle 3 Versuche" in result.feedback
    assert "noodle" in result.feedback
