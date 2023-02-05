# swagger2burp
Convert Swagger openapi.json file to burp suite request files

```
usage: swagger2burp.py [-h] -f FILE -b BASE_PATH -ho HOST_HEADER -t TOKEN

options:
  -h, --help            show this help message and exit
  -f FILE, --file FILE  URL of the openapi.json file
  -b BASE_PATH, --base-path BASE_PATH
                        Base path for API endpoints
  -ho HOST_HEADER, --host-header HOST_HEADER
                        Value for Host header
  -t TOKEN, --token TOKEN
                        Value for JWT token

```


Example:
```
python3 swagger2burp.py -f openapi.json -b https://swagger.domain.com -ho swagger.domain.com -t eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.
eyJpc3MiOiJ0b3B0YWwuY29tIiwiZXhwIjoxNDI2NDIwODAwLCJodHRwOi8vdG9wdGFsLmNvbS9qd3RfY2xhaW1zL2lzX2FkbWluIjp0cnVlLCJjb21wYW55IjoiVG9wdGFsIiwiYXdlc29tZSI6dHJ1ZX0.
yRQYnWzskCZUxPwaQupWkiUzKELZ49eM7oWxAQK_ZXw 
```
