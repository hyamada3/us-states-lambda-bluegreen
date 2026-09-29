"""CodeDeployのBeforeAllowTraffic(PreTraffic)フック。

エイリアス `live` をGreen(新バージョン)へ切り替える前に、Greenを直接呼び出して
正常に応答するかを検証し、結果をCodeDeployへ報告する。
Failedを報告するとCodeDeployはトラフィックを切り替えず、デプロイはロールバックされる。
"""
import json
import os

import boto3

TEST_EVENT = {"queryStringParameters": None, "rawPath": "/hello"}
EXPECTED_MESSAGE = "Hello, World!"


def _lambda_client():
    return boto3.client("lambda")


def _codedeploy_client():
    return boto3.client("codedeploy")


def _is_healthy(payload):
    if payload.get("statusCode") != 200:
        return False
    body = json.loads(payload.get("body") or "{}")
    return body.get("message") == EXPECTED_MESSAGE


def _validate_green(target_version):
    try:
        response = _lambda_client().invoke(FunctionName=target_version, Payload=json.dumps(TEST_EVENT))
        payload = json.loads(response["Payload"].read())
    except Exception as exc:  # 呼び出し自体の失敗もデプロイ失敗として扱う
        print(f"Greenの呼び出しに失敗: {exc}")
        return False
    print(f"Greenの応答: {payload}")
    return _is_healthy(payload)


def handler(event, context):
    target_version = os.environ["TARGET_FUNCTION_VERSION"]
    status = "Succeeded" if _validate_green(target_version) else "Failed"

    _codedeploy_client().put_lifecycle_event_hook_execution_status(
        deploymentId=event["DeploymentId"],
        lifecycleEventHookExecutionId=event["LifecycleEventHookExecutionId"],
        status=status,
    )
    return {"status": status}
