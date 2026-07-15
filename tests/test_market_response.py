from data.market_response import (
    MarketDataErrorCode,
    RetryPolicy,
    SafeMarketResponse,
)


def test_empty_and_non_json_sdk_responses_are_typed_and_sanitized():
    empty = SafeMarketResponse.normalize(None, endpoint="quote_data")
    html = SafeMarketResponse.normalize(
        '<html>gateway error access_token="secret-value"</html>',
        endpoint="quote_data",
        correlation_id="scan-1",
    )

    assert empty.ok is False
    assert empty.error_code is MarketDataErrorCode.EMPTY_RESPONSE
    assert html.ok is False
    assert html.error_code is MarketDataErrorCode.NON_JSON_RESPONSE
    assert "secret-value" not in html.preview
    assert "[REDACTED]" in html.preview
    assert html.correlation_id == "scan-1"


def test_success_and_broker_failure_dicts_are_distinguished():
    success = SafeMarketResponse.normalize(
        {"status": "success", "data": {"value": 10}}, endpoint="quote_data"
    )
    failure = SafeMarketResponse.normalize(
        {"status": "failure", "remarks": {"error_message": "rate limited"}},
        endpoint="quote_data",
    )

    assert success.ok is True
    assert success.value["data"]["value"] == 10
    assert failure.ok is False
    assert failure.error_code is MarketDataErrorCode.BROKER_FAILURE


def test_retry_policy_is_bounded_and_uses_injected_sleep():
    attempts = []
    delays = []

    def operation():
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            return None
        return {"status": "success", "data": {"ok": True}}

    result = RetryPolicy(max_attempts=3, base_delay_seconds=0.1).run(
        operation,
        endpoint="quote_data",
        sleep=delays.append,
    )

    assert result.ok is True
    assert result.attempt_count == 3
    assert attempts == [1, 2, 3]
    assert delays == [0.1, 0.2]


def test_retry_exhaustion_returns_failure_instead_of_stale_value():
    result = RetryPolicy(max_attempts=2, base_delay_seconds=0.0).run(
        lambda: "",
        endpoint="quote_data",
        sleep=lambda _: None,
    )

    assert result.ok is False
    assert result.error_code is MarketDataErrorCode.EMPTY_RESPONSE
    assert result.attempt_count == 2
    assert result.value is None
