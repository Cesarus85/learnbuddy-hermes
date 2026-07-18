from learnbuddy_core.parent_messages import format_parent_answer_notification


def test_parent_answer_notification_uses_readable_sections_for_partial_batch():
    text = format_parent_answer_notification(
        agent_name="Vision",
        child_name="Learner",
        subject="english",
        prompt=(
            "Guten Morgen Learner 😊 Englisch-Vokabeltraining: Übersetze bitte ins Englische. "
            "Schreib deine Antworten nummeriert 1–5. 1. etwas sehr gerne tun 2. tun "
            "3. auch 4. also, daher 5. Spaß machen"
        ),
        answer="1. like to do something 2. do 3. have fun",
        result={
            "correct": False,
            "result": "incorrect",
            "attempts": 2,
            "max_attempts": 3,
            "metadata": {
                "score": 1,
                "total": 5,
                "item_results": [
                    {"index": 1, "correct": False},
                    {"index": 2, "correct": False},
                    {"index": 3, "correct": False},
                    {"index": 4, "correct": True},
                    {"index": 5, "correct": False},
                ],
            },
        },
    )

    assert text.startswith("📚 Vision · Englisch\nLearner hat geantwortet")
    assert "\n\nAufgabe\n" in text
    assert "\n\nAntwort von Learner\n" in text
    assert "\n\nAuswertung\n" in text
    assert "• Status: ❌ noch nicht richtig" in text
    assert "• Versuch: 2/3" in text
    assert "• Teilaufgaben: 1/5 richtig" in text
    assert "• Nochmal anschauen: Nr. 1, 2, 3, 5" in text
    assert "Aufgabe:" not in text.splitlines()[0]
