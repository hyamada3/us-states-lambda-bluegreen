import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import pre_traffic

TARGET = "arn:aws:lambda:ap-northeast-1:123456789012:function:us-states-lambda-bg-sample:7"
HOOK_EVENT = {"DeploymentId": "d-TEST", "LifecycleEventHookExecutionId": "hook-TEST"}


class FakeLambda:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.invoked = []

    def invoke(self, FunctionName, Payload):
        self.invoked.append(FunctionName)
        if self.error:
            raise self.error
        return {"Payload": io.BytesIO(json.dumps(self.payload).encode())}


class FakeCodeDeploy:
    def __init__(self):
        self.reported = []

    def put_lifecycle_event_hook_execution_status(self, **kwargs):
        self.reported.append(kwargs)


def healthy_payload():
    return {"statusCode": 200, "body": json.dumps({"message": "Hello, World!", "path": "/hello"})}


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setenv("TARGET_FUNCTION_VERSION", TARGET)
    codedeploy = FakeCodeDeploy()
    monkeypatch.setattr(pre_traffic, "_codedeploy_client", lambda: codedeploy)
    return codedeploy


def use_lambda(monkeypatch, fake):
    monkeypatch.setattr(pre_traffic, "_lambda_client", lambda: fake)


def test_reports_succeeded_when_green_version_is_healthy(monkeypatch, fakes):
    # Arrange
    fake_lambda = FakeLambda(payload=healthy_payload())
    use_lambda(monkeypatch, fake_lambda)

    # Act
    result = pre_traffic.handler(HOOK_EVENT, None)

    # Assert
    assert result == {"status": "Succeeded"}
    assert fake_lambda.invoked == [TARGET]
    assert fakes.reported == [
        {"deploymentId": "d-TEST", "lifecycleEventHookExecutionId": "hook-TEST", "status": "Succeeded"}
    ]


def test_reports_failed_when_green_version_returns_error_status(monkeypatch, fakes):
    # Arrange
    use_lambda(monkeypatch, FakeLambda(payload={"statusCode": 500, "body": "{}"}))

    # Act
    result = pre_traffic.handler(HOOK_EVENT, None)

    # Assert
    assert result == {"status": "Failed"}
    assert fakes.reported[0]["status"] == "Failed"


def test_reports_failed_when_green_version_returns_unexpected_message(monkeypatch, fakes):
    # Arrange
    payload = {"statusCode": 200, "body": json.dumps({"message": "broken"})}
    use_lambda(monkeypatch, FakeLambda(payload=payload))

    # Act
    result = pre_traffic.handler(HOOK_EVENT, None)

    # Assert
    assert result == {"status": "Failed"}


def test_reports_failed_when_invoking_green_version_raises(monkeypatch, fakes):
    # Arrange
    use_lambda(monkeypatch, FakeLambda(error=RuntimeError("invoke failed")))

    # Act
    result = pre_traffic.handler(HOOK_EVENT, None)

    # Assert
    assert result == {"status": "Failed"}
    assert fakes.reported[0]["status"] == "Failed"
