import os
import json
import argparse

def convert_to_burp(api_def, base_path, host_header, token):
    endpoints = api_def["paths"]
    requests = []
    for endpoint, methods in endpoints.items():
        for method, details in methods.items():
            request = {
                "url": base_path + endpoint,
                "method": method.upper(),
                "headers": [
                    "Host: " + host_header,
                    "Authorization: Bearer " + token ,
                    "Content-Type: application/json"
                ]
            }
            if "requestBody" in details and "content" in details["requestBody"] and "application/json" in details["requestBody"]["content"]:
                request["body"] = json.dumps(details["requestBody"]["content"]["application/json"]["schema"], indent=2)
            requests.append(request)
    return requests

def write_to_file(request, directory, filename):
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(os.path.join(directory, filename), "w") as f:
        f.write(f"{request['method']} {request['url']}\n")
        for header in request["headers"]:
            f.write(f"{header}\n")
        if "body" in request:
            f.write("\n")
            f.write(request["body"])
        f.write("\n\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", help="URL of the openapi.json file", required=True)
    parser.add_argument("-b", "--base-path", help="Base path for API endpoints", required=True)
    parser.add_argument("-ho", "--host-header", help="Value for Host header", required=True)
    parser.add_argument("-t", "--token", help="Value for JWT token", required=True)
    args = parser.parse_args()

    with open(args.file) as f:
        api_def = json.load(f)
    requests = convert_to_burp(api_def, args.base_path, args.host_header, args.token)
    for request in requests:
        endpoint = request["url"].replace(args.base_path, "")
        filename = f"{request['method']}_{endpoint.replace('/', '_')}.txt"
        write_to_file(request, "burp_requests", filename)
