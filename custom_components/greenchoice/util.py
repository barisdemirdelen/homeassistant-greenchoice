import json

import requests


def curl_dump(req: requests.PreparedRequest) -> str:
    try:
        # Slightly modified curl dump borrowed from this
        #   Stack Overflow answer: https://stackoverflow.com/a/17936634/4925795
        command = "curl -X {method} -H {headers} -d '{data}' '{uri}'"
        method = req.method
        uri = req.url
        data = req.body
        if isinstance(data, bytes):
            data = json.dumps(json.loads(data))
        headers = ['"{0}: {1}"'.format(k, v) for k, v in req.headers.items()]
        headers = " -H ".join(headers)
        return command.format(method=method, headers=headers, data=data, uri=uri)

    except:  # NOSONAR Catch all exceptions here because
        #   execution should not stop in case of curl dump errors.
        return "Logging curl dump failed, gracefully ignoring."
