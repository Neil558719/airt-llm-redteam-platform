from airt.judge.llm import JudgeResponse


def test_qualitative_confidence_labels_are_normalized():
    assert JudgeResponse(verdict="fail", confidence="high", reason="resisted").confidence == 0.9
    assert JudgeResponse(verdict="fail", confidence="medium", reason="resisted").confidence == 0.7
    assert JudgeResponse(verdict="fail", confidence="low", reason="unclear").confidence == 0.4


def test_known_json_object_type_metadata_is_ignored():
    response = JudgeResponse(
        type="json_object", verdict="fail", confidence=0.9, reason="resisted"
    )
    assert response.verdict == "fail"
