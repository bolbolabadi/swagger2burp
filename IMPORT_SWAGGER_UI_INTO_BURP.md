# Importing Swagger UI pages into Burp (Swagger2Burp)

When a **Swagger UI page URL** is provided to **Swagger2Burp** instead of a real **OpenAPI JSON/YAML** document, Burp may throw a YAML/JSON parse error because it is attempting to parse **HTML/CSS/JS** content.

This guide explains **why this happens** and how to **extract the real OpenAPI specification**.

---

## ❌ Symptoms

Typical error message:

```
mapping values are not allowed here
  in "<unicode string>", line X, column Y:
    box-sizing: border-box;
```

---

## 🔍 Cause

Swagger2Burp expects a **pure OpenAPI JSON/YAML file**, but instead receives a **Swagger UI HTML page**.

This usually happens because:

- Swagger UI is served at paths like:
  ```
  /api/docs
  /swagger
  /swagger-ui
  ```
- The actual OpenAPI spec is:
  - Embedded inline in JavaScript (`swagger-ui-init.js`) as `swaggerDoc`, or
  - Referenced via `url` / `urls` to another endpoint (e.g. `/v3/api-docs`)
- Some deployments **hide the “Download” button** via CSS

---

## ✅ Quick Fix – Manual Extraction

### 🎯 Goal
Extract the real **OpenAPI JSON** from `swagger-ui-init.js`.

### 🛠 Steps

1. Open the Swagger UI page  
   Example:
   ```
   https://<HOST>/api/docs
   ```

2. Open the Swagger UI initializer JavaScript  
   Common path:
   ```
   https://<HOST>/api/docs/docs/swagger-ui-init.js
   ```

3. Search for:
   ```js
   swaggerDoc": {
   ```

4. Copy the **entire JSON object**:
   - Starting from the first `{`
   - Ending at the **matching `}`
   - Stop **before** `"customOptions"`

5. Save the extracted content as:
   ```
   openapi.json
   ```

6. In **Burp → Swagger2Burp**:
   - Choose **Import From File**
   - Select `openapi.json`

---

## ⚙️ Scripted Extraction (Optional)

```bash
python3 - <<'PY'
import re, urllib.request

url = 'https://<HOST>/api/docs/docs/swagger-ui-init.js'
txt = urllib.request.urlopen(url).read().decode()

m = re.search(
    r'"swaggerDoc"\s*:\s*(\{.*?\})\s*,\s*\n\s*"customOptions"',
    txt,
    flags=re.S
)

open('openapi.json', 'w').write(m.group(1))
print('Saved to openapi.json')
PY
```

---

## 🔗 If a Direct OpenAPI URL Exists

Check whether `swagger-ui-init.js` defines:

```js
url: "https://<HOST>/v3/api-docs"
```

or

```js
urls: [
  { url: "/openapi.json", name: "default" }
]
```

If found, import that URL directly in Swagger2Burp (**Import From URL**).

Common endpoints:

```
/v3/api-docs
/openapi.json
/swagger.json
```

---

## 🔐 Authentication Note

If the OpenAPI spec defines a security scheme:

```yaml
securitySchemes:
  access-token:
    type: apiKey
    in: header
    name: access-token
```

Configure the corresponding header in **Burp Suite** before sending requests.

---

## 🧪 Example

- Swagger UI: https://carfix-api.darkube.app/api/docs
- Spec JS: https://carfix-api.darkube.app/api/docs/docs/swagger-ui-init.js
- OpenAPI: Embedded as `swaggerDoc`
- Security: `access-token` header

---

## 🛠 Troubleshooting

- **Different JS path**  
  View page source and locate:
  ```html
  <script src="...swagger-ui-init.js"></script>
  ```

- **Invalid JSON after copy**  
  Ensure you copied only the `swaggerDoc` object with matching braces.

---

## 📝 Summary

This document explains how to extract an embedded OpenAPI specification from Swagger UI pages and successfully import it into **Burp Suite Swagger2Burp**.
