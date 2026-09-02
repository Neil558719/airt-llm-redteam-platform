def test_result_errors_are_detected_as_command_failures():
    from airt.cli import _result_errors
    from airt.models import CaseResult, ResultStatus

    result = CaseResult(status=ResultStatus.ERROR, case_id="image", failure_kind="target")
    assert _result_errors([result]) == [result]
