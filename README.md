# Swagger2Burp

Import Swagger/OpenAPI definitions (Swagger 2.0 and OpenAPI 3) into Burp Suite and generate one example HTTP request per operation, ready to send to Repeater.

## Features
- **Multiple input modes**: URL(s) to JSON/YAML specs, or paste Raw JSON directly. Auto-detects JSON and tries YAML when available.
- **Auth when fetching specs**: Optional JWT and custom headers used for retrieving remote specs.
- **Base URL handling**: Uses servers/basePath from the spec (if enabled) or a user-provided Base URL override.
- **Path and query params**: Optionally fills `{path}` params and includes query parameters with sample values.
- **Request bodies**: Generates example JSON body from schemas/examples where available.
- **Quick preview and send**: Preview all generated requests and send selected ones to Repeater.

  ## Screenshots
- UI overview: <img width="1793" height="1036" alt="swagger2burp-tab-ui" src="https://github.com/user-attachments/assets/289a4dad-a84d-484c-952a-c8360df5f765" />

- Import and send to Repeater: <img width="1916" height="1007" alt="swagger2burp-tab-repeater" src="https://github.com/user-attachments/assets/8cf31369-2182-4920-a797-5b0d01311759" />

## Why it’s helpful
Great for quickly bootstrapping testing coverage against large APIs. You’ll have a ready list of endpoints pre-populated with reasonable parameter/body samples.

## Requirements
- Burp Suite with Montoya API support (Community or Professional)
- Release JAR bundles dependencies (Jackson for JSON, SnakeYAML for YAML)
- Optional legacy: Python/Jython 2.7 if using the `.py` version

## Installation
### Java (recommended)
1. Download the release JAR from GitHub Releases.
2. In Burp: Extender -> Extensions -> Add -> Extension type: Java -> Select the JAR.

### Legacy Python (optional)
1. In Burp: Extender -> Extensions -> Add -> Extension type: Python -> Select `Swagger2BurpExtender.py`.
2. Requires Jython 2.7 (Burp -> Extender -> Options -> Python Environment).
3. (Optional) For YAML, add SnakeYAML to Burp’s classpath.

## Build (Java)
- With Gradle: `./gradlew shadowJar` (or `gradle shadowJar`)
- Output JAR: `montoya/build/libs/*-all.jar`

## Usage
1. Open the Swagger2Burp tab.
2. (Optional) Enter JWT and/or custom headers. These are used both for fetching the spec and for the generated requests.
3. If your Swagger 2.0 spec does not declare `host`/`basePath`, set **Base URL override** (for example: `https://api.example.com`).
4. Choose Input mode:
   - Auto-detect
   - URL(s)
   - Raw JSON
5. Paste the spec URL(s) or the Raw JSON, then click Import.
6. Review the generated requests, select desired ones, and click “Send selected to Repeater”.
7. If you have only Swagger without JSON file [READ THIS](https://github.com/bolbolabadi/swagger2burp/blob/main/IMPORT_SWAGGER_UI_INTO_BURP.md)

## Notes
- If the spec lacks a resolvable base URL and no Base URL override is provided, such operations will be skipped.
- For specs requiring Basic Auth to fetch: add a custom header like `Authorization: Basic <base64(user:pass)>`.

## Privacy & Safety
- Requests are built locally. Use on systems you have permission to test.

## License
MIT

## Author
- BolbolSec
- GitHub: https://github.com/bolbolabadi/
