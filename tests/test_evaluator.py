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


def test_multi_part_math_answer_matches_numbered_or_multiline_replies():
    result = evaluate_answer(
        "2\n20\n66",
        answer="2, 20, 66",
        expected_answers=["2, 20, 66", "2 20 66", "1+1=2; 10+10=20; 33+33=66", "2; 20; 66"],
        prompt="1 + 1 = ?\n10 + 10 = ?\n33 + 33 = ?",
        subject="math",
    )

    assert result.correct is True
    assert result.metadata["score"] == 3
    assert result.metadata["total"] == 3
    assert "Alle Teilaufgaben" in result.feedback


def test_multi_part_math_answer_reports_partial_progress():
    result = evaluate_answer(
        "1. 2 2. 21 3. 66",
        expected_answers=["2", "20", "66"],
        exercise_type="calculation_batch",
        subject="math",
    )

    assert result.correct is False
    assert result.exhausted is False
    assert result.metadata["score"] == 2
    assert result.metadata["total"] == 3
    assert "2/3" in result.feedback
    assert "Nr. 2" in result.feedback
