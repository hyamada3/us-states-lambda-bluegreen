import json

# Blue/Greenの切替を確認しやすいよう、レスポンスにアプリのバージョンを含める
APP_VERSION = "v1"


def handler(event, context):
    """API Gateway (HTTP API) 経由で呼び出されるサンプルLambda関数。

    クエリパラメータ `name` があれば挨拶に含める。
    """
    query_params = event.get("queryStringParameters") or {}
    name = query_params.get("name", "World")

    body = {
        "message": f"Hello, {name}!",
        "path": event.get("rawPath", event.get("path", "")),
        "version": APP_VERSION,
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }
