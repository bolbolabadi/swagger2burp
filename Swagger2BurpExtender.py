# -*- coding: utf-8 -*-
# Jython 2.7 Burp Extension: Swagger2Burp Tab
# Provides a UI to input Swagger/OpenAPI sources (URLs or raw JSON), optional JWT and custom headers,
# parses endpoints, and sends one request per operation to Repeater.

from burp import IBurpExtender, ITab, IExtensionStateListener

from java.awt import BorderLayout, GridBagLayout, GridBagConstraints, Insets
from javax.swing import JPanel, JLabel, JTextField, JTextArea, JButton, JScrollPane, JCheckBox, JComboBox, BorderFactory, JTabbedPane, SwingUtilities

import json
import re
import threading

# Python 2 compatible imports
try:
    # Jython/Python2
    import urllib2 as urllib_request
    from urlparse import urlparse, urljoin
except Exception:
    # Fallback if running in different environment
    import urllib.request as urllib_request
    from urllib.parse import urlparse, urljoin


def _strip(s):
    if s is None:
        return ""
    return s.strip()


def _safe_get(dct, *keys):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _first_non_empty(*vals):
    for v in vals:
        if v is not None and v != "":
            return v
    return None


def _is_json_text(text):
    t = text.strip()
    return (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]"))


def _read_url(url, headers):
    req = urllib_request.Request(url)
    for k, v in headers.items():
        try:
            req.add_header(k, v)
        except Exception:
            pass
    resp = urllib_request.urlopen(req)
    return resp.read()


def _fetch_text(url, headers, timeout=20):
    req = urllib_request.Request(url)
    # helpful defaults for some gateways
    try:
        req.add_header('User-Agent', 'Swagger2Burp-Jython')
        req.add_header('Accept', 'application/json, application/yaml, text/yaml, application/x-yaml, */*')
    except Exception:
        pass
    for k, v in headers.items():
        try:
            req.add_header(k, v)
        except Exception:
            pass
    try:
        resp = urllib_request.urlopen(req, timeout=timeout)
    except Exception:
        # fallback no-timeout if Jython/urllib2 variant misbehaves
        resp = urllib_request.urlopen(req)
    # content type (best-effort)
    ctype = ''
    try:
        info = resp.info()
        ctype = info.get('Content-Type') or ''
    except Exception:
        try:
            ctype = resp.getContentType()
        except Exception:
            ctype = ''
    body = resp.read()
    try:
        body = str(body)
    except Exception:
        pass
    return body, ctype


try:
    from java.util import Map as _JavaMap, List as _JavaList
except Exception:
    _JavaMap = None
    _JavaList = None

try:
    from org.yaml.snakeyaml import Yaml as _SnakeYaml
except Exception:
    _SnakeYaml = None


def _to_py(obj):
    # Convert Java Map/List from SnakeYAML to Python types
    try:
        if _JavaMap is not None and isinstance(obj, _JavaMap):
            py = {}
            it = obj.entrySet().iterator()
            while it.hasNext():
                e = it.next()
                py[e.getKey()] = _to_py(e.getValue())
            return py
    except Exception:
        pass
    try:
        if _JavaList is not None and isinstance(obj, _JavaList):
            return [_to_py(x) for x in obj.toArray()]
    except Exception:
        pass
    if isinstance(obj, dict):
        return dict((k, _to_py(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return [_to_py(x) for x in obj]
    return obj


def _parse_yaml(text):
    if _SnakeYaml is None:
        raise Exception('YAML parsing not available (SnakeYAML jar not on classpath).')
    y = _SnakeYaml()
    data = y.load(text)
    return _to_py(data)


def _looks_like_url(s):
    s = _strip(s or '')
    return s.startswith('http://') or s.startswith('https://')


def _try_alt_json_url(url):
    if url.endswith('.yaml'):
        return url[:-5] + '.json'
    if url.endswith('.yml'):
        return url[:-4] + '.json'
    return None


def _load_spec_from_source(src, fetch_headers):
    s = _strip(src)
    if not s:
        raise Exception('Empty source')
    # direct JSON text
    if _is_json_text(s):
        return json.loads(s)
    # URL
    if _looks_like_url(s):
        body, ctype = _fetch_text(s, fetch_headers)
        # Try JSON first
        try:
            return json.loads(body)
        except Exception:
            pass
        # Try YAML if content-type or extension indicates YAML
        try:
            if 'yaml' in (ctype or '').lower() or s.endswith('.yaml') or s.endswith('.yml'):
                return _parse_yaml(body)
        except Exception:
            pass
        # Try alternative .json path
        alt = _try_alt_json_url(s)
        if alt is not None:
            try:
                body2, _ = _fetch_text(alt, fetch_headers)
                return json.loads(body2)
            except Exception:
                pass
        # Last attempt: parse YAML regardless
        try:
            return _parse_yaml(body)
        except Exception as e:
            raise Exception('Unable to parse as JSON or YAML (%s)' % e)
    # Raw pasted text but not JSON; attempt YAML
    return _parse_yaml(s)


def _parse_custom_headers(text):
    headers = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # support "Header: value" and "Header=value"
        if ":" in line:
            name, val = line.split(":", 1)
        elif "=" in line:
            name, val = line.split("=", 1)
        else:
            # ignore invalid
            continue
        headers.append((name.strip(), val.strip()))
    return headers


def _choose_base_from_oas3(spec):
    servers = spec.get('servers') or []
    if not servers:
        return None
    s = servers[0]
    url = s.get('url') or '/'
    # replace server variables if present
    def repl(m):
        var = m.group(1)
        vars_def = s.get('variables') or {}
        if var in vars_def:
            v = _first_non_empty(vars_def[var].get('default'), vars_def[var].get('example'))
            if v is not None:
                return str(v)
        return var
    url = re.sub(r"\{([^}]+)\}", repl, url)
    return url


def _choose_base_from_swagger2(spec):
    scheme = None
    schemes = spec.get('schemes') or []
    if schemes:
        scheme = schemes[0]
    host = spec.get('host') or ''
    base_path = spec.get('basePath') or '/'
    if not scheme:
        scheme = 'https'
    return scheme + '://' + host + base_path


def _join_url(base, path):
    if not base:
        base = '/'
    if not path:
        path = '/'
    # use urljoin for correctness
    try:
        return urljoin(base.rstrip('/') + '/', path.lstrip('/'))
    except Exception:
        # very defensive fallback
        if base.endswith('/') and path.startswith('/'):
            return base[:-1] + path
        elif not base.endswith('/') and not path.startswith('/'):
            return base + '/' + path
        return base + path


def _sample_value(schema):
    if not isinstance(schema, dict):
        return None
    # honor explicit example/default first
    if 'example' in schema:
        return schema['example']
    if 'default' in schema:
        return schema['default']
    t = schema.get('type')
    if t == 'string' or t is None:
        fmt = schema.get('format')
        if fmt == 'date-time':
            return '2025-01-01T00:00:00Z'
        if fmt == 'date':
            return '2025-01-01'
        if fmt == 'uuid':
            return '00000000-0000-0000-0000-000000000000'
        return 'string'
    if t == 'integer' or t == 'number':
        return 0
    if t == 'boolean':
        return False
    if t == 'array':
        item_schema = schema.get('items') or {}
        return [_sample_value(item_schema)]
    if t == 'object':
        props = schema.get('properties') or {}
        required = schema.get('required') or []
        obj = {}
        for name, sub in props.items():
            obj[name] = _sample_value(sub)
        # ensure required keys exist
        for r in required:
            if r not in obj:
                obj[r] = 'string'
        return obj
    return None


def _param_example(p):
    if not isinstance(p, dict):
        return 'string'
    if 'example' in p:
        v = p['example']
        return v
    if 'default' in p:
        v = p['default']
        return v
    t = p.get('type') or (p.get('schema') or {}).get('type')
    if t in ('integer', 'number'):
        return 123
    if t == 'boolean':
        return True
    return 'string'


def _build_query(params):
    # params: list of (name, value)
    if not params:
        return ''
    enc = []
    for k, v in params:
        try:
            from urllib import quote as _quote
        except Exception:
            from urllib.parse import quote as _quote
        enc.append('%s=%s' % (_quote(str(k)), _quote(str(v))))
    return '?' + '&'.join(enc)


def _build_http_request(method, path_with_query, host_header, headers_list, body, helpers):
    lines = []
    lines.append('%s %s HTTP/1.1' % (method.upper(), path_with_query or '/'))
    if host_header:
        lines.append('Host: %s' % host_header)
    # default Accept
    has_accept = any(h[0].lower() == 'accept' for h in headers_list)
    if not has_accept:
        headers_list = headers_list + [('Accept', 'application/json')]
    for name, val in headers_list:
        if name.lower() == 'host':
            continue
        lines.append('%s: %s' % (name, val))
    req = '\r\n'.join(lines) + '\r\n\r\n'
    if body is not None:
        if isinstance(body, (dict, list)):
            body_text = json.dumps(body)
        else:
            body_text = str(body)
        req += body_text
    return helpers.stringToBytes(req)


class BurpExtender(IBurpExtender, ITab, IExtensionStateListener):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        callbacks.setExtensionName('Swagger2Burp')
        callbacks.registerExtensionStateListener(self)

        self._panel = JPanel(BorderLayout())
        self._panel.add(self._build_ui(), BorderLayout.CENTER)
        callbacks.addSuiteTab(self)

    # ITab
    def getTabCaption(self):
        return 'Swagger2Burp'

    def getUiComponent(self):
        return self._panel

    # IExtensionStateListener
    def extensionUnloaded(self):
        # nothing to clean
        pass

    def _build_ui(self):
        panel = JPanel(BorderLayout())

        form = JPanel(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(4, 4, 4, 4)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0

        row = 0

        # JWT
        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0
        form.add(JLabel('JWT (optional):'), gbc)
        self._jwtField = JTextField()
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0
        form.add(self._jwtField, gbc)
        row += 1

        # Custom Headers
        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0
        form.add(JLabel('Custom headers (one per line, k: v):'), gbc)
        self._headersArea = JTextArea(5, 50)
        headersScroll = JScrollPane(self._headersArea)
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0
        form.add(headersScroll, gbc)
        row += 1

        # Base URL override
        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0
        form.add(JLabel('Base URL override (optional):'), gbc)
        self._baseUrlField = JTextField()
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0
        form.add(self._baseUrlField, gbc)
        row += 1

        # Mode
        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0
        form.add(JLabel('Input mode:'), gbc)
        self._modeCombo = JComboBox(['Auto-detect', 'URL(s)', 'Raw JSON'])
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0
        form.add(self._modeCombo, gbc)
        row += 1

        # Spec sources
        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0
        form.add(JLabel('Swagger/OpenAPI sources (one per line or paste JSON):'), gbc)
        self._sourcesArea = JTextArea(8, 50)
        sourcesScroll = JScrollPane(self._sourcesArea)
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0
        form.add(sourcesScroll, gbc)
        row += 1

        # Options
        self._includeQuery = JCheckBox('Include query parameters', True)
        self._fillPathParams = JCheckBox('Fill path parameters', True)
        self._useSpecServers = JCheckBox('Use servers/basePath from spec (unless base override is set)', True)
        self._useHttps = JCheckBox('Use HTTPS', True)

        optsPanel = JPanel(GridBagLayout())
        gbc2 = GridBagConstraints()
        gbc2.insets = Insets(2, 2, 2, 2)
        gbc2.anchor = GridBagConstraints.WEST
        gbc2.gridx = 0; gbc2.gridy = 0
        optsPanel.add(self._includeQuery, gbc2)
        gbc2.gridy += 1
        optsPanel.add(self._fillPathParams, gbc2)
        gbc2.gridy += 1
        optsPanel.add(self._useSpecServers, gbc2)
        gbc2.gridy += 1
        optsPanel.add(self._useHttps, gbc2)

        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0
        form.add(JLabel('Options:'), gbc)
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0
        form.add(optsPanel, gbc)
        row += 1

        # Buttons
        self._runBtn = JButton('Import', actionPerformed=self._on_import)
        self._clearLogBtn = JButton('Clear log', actionPerformed=self._on_clear_log)

        btnPanel = JPanel()
        btnPanel.add(self._runBtn)
        btnPanel.add(self._clearLogBtn)

        reqListPanel = JPanel(GridBagLayout())
        self._requestsListPanel = reqListPanel
        self._requestItems = []
        reqScroll = JScrollPane(self._requestsListPanel)
        reqScroll.setBorder(BorderFactory.createTitledBorder('Requests'))
        self._selectAllChk = JCheckBox('Select all', False, actionPerformed=self._on_select_all)
        self._sendSelectedBtn = JButton('Send selected to Repeater', actionPerformed=self._on_send_selected)
        midPanel = JPanel(BorderLayout())
        midPanel.add(btnPanel, BorderLayout.NORTH)
        controlsPanel = JPanel()
        controlsPanel.add(self._selectAllChk)
        controlsPanel.add(self._sendSelectedBtn)
        midPanel.add(reqScroll, BorderLayout.CENTER)
        midPanel.add(controlsPanel, BorderLayout.SOUTH)

        # Log area
        self._logArea = JTextArea(10, 80)
        self._logArea.setEditable(False)
        logScroll = JScrollPane(self._logArea)
        logScroll.setBorder(BorderFactory.createTitledBorder('Log'))

        panel.add(form, BorderLayout.NORTH)
        panel.add(midPanel, BorderLayout.CENTER)
        panel.add(logScroll, BorderLayout.SOUTH)
        return panel

    def _log(self, msg):
        try:
            self._logArea.append(str(msg) + '\n')
            self._logArea.setCaretPosition(self._logArea.getDocument().getLength())
        except Exception:
            pass

    def _on_clear_log(self, event):
        self._logArea.setText('')

    def _on_import(self, event):
        jwt = _strip(self._jwtField.getText())
        custom_headers = _parse_custom_headers(self._headersArea.getText() or '')
        base_override = _strip(self._baseUrlField.getText())

        sources_raw = self._sourcesArea.getText() or ''
        mode = self._modeCombo.getSelectedItem()

        # prepare fetch headers for spec retrieval
        spec_fetch_headers = {}
        if jwt:
            spec_fetch_headers['Authorization'] = 'Bearer ' + jwt
        for name, val in custom_headers:
            if name.lower() == 'authorization' and 'Authorization' in spec_fetch_headers:
                continue
            spec_fetch_headers[name] = val

        sources = []
        if mode == 'Raw JSON':
            # entire area is JSON
            if not _is_json_text(sources_raw):
                self._log('Input mode is Raw JSON but content is not JSON.')
                return
            sources = [sources_raw]
        else:
            # split by lines; if any line looks like JSON begin, join remainder
            lines = [l.strip() for l in sources_raw.splitlines() if l.strip()]
            if mode == 'URL(s)':
                sources = lines
            else:
                # Auto-detect per line; if first non-empty is JSON, treat entire as JSON
                if sources_raw.strip() and _is_json_text(sources_raw.strip()):
                    sources = [sources_raw.strip()]
                else:
                    sources = lines

        if not sources:
            self._log('No sources provided.')
            return

        # Run heavy work off the UI thread
        self._runBtn.setEnabled(False)
        try:
            self._selectAllChk.setSelected(False)
        except Exception:
            pass
        try:
            self._requestItems = []
            self._requestsListPanel.removeAll()
            self._requestsListPanel.revalidate()
            self._requestsListPanel.repaint()
        except Exception:
            pass
        def _worker():
            all_items = []
            for src in sources:
                try:
                    if _is_json_text(src):
                        self._log('Loading spec from pasted JSON')
                    elif _looks_like_url(src):
                        self._log('Fetching spec: %s' % src)
                    spec = self._load_spec_from_source_burp(src, spec_fetch_headers)
                except Exception as e:
                    self._log('Failed to load spec from source: %s (%s)' % (src, e))
                    continue

                try:
                    items = self._process_spec(spec, jwt, custom_headers, base_override, True)
                    if isinstance(items, list):
                        all_items.extend(items)
                except Exception as e:
                    self._log('Error processing spec: %s' % e)

            self._log('Prepared %d request(s). Review and send selected.' % len(all_items))
            def _ui_update():
                try:
                    self._populate_requests_list(all_items)
                except Exception:
                    pass
                try:
                    self._runBtn.setEnabled(True)
                except Exception:
                    pass
            try:
                SwingUtilities.invokeLater(_ui_update)
            except Exception:
                _ui_update()

        thr = threading.Thread(target=_worker)
        try:
            thr.setDaemon(True)
        except Exception:
            pass
        thr.start()

    def _format_hostport(self, host, port, use_https):
        try:
            if host is None:
                return ''
            if (use_https and int(port) == 443) or ((not use_https) and int(port) == 80):
                return host
            return '%s:%d' % (host, int(port))
        except Exception:
            return str(host)

    def _populate_requests_list(self, items):
        try:
            self._requestItems = []
            self._requestsListPanel.removeAll()
            gbc = GridBagConstraints()
            gbc.insets = Insets(2, 2, 2, 2)
            gbc.anchor = GridBagConstraints.WEST
            gbc.fill = GridBagConstraints.HORIZONTAL
            gbc.weightx = 1.0
            gbc.gridx = 0
            row = 0
            for info in items:
                label = info.get('label') or ''
                cb = JCheckBox(label)
                gbc.gridy = row
                self._requestsListPanel.add(cb, gbc)
                self._requestItems.append({'checkbox': cb, 'data': info})
                row += 1
            self._requestsListPanel.revalidate()
            self._requestsListPanel.repaint()
        except Exception as e:
            self._log('Failed to populate request list: %s' % e)

    def _on_select_all(self, event):
        try:
            sel = self._selectAllChk.isSelected()
            for it in (self._requestItems or []):
                try:
                    it['checkbox'].setSelected(sel)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_send_selected(self, event):
        callbacks = self._callbacks
        selected = []
        try:
            for it in (self._requestItems or []):
                try:
                    if it['checkbox'].isSelected():
                        selected.append(it['data'])
                except Exception:
                    continue
        except Exception:
            selected = []
        cnt = 0
        for info in selected:
            try:
                callbacks.sendToRepeater(info['host'], int(info['port']), info['use_https'], info['req_bytes'], info['caption'])
                cnt += 1
            except Exception as e:
                self._log('Failed to send to Repeater: %s' % e)
        self._log('Sent %d request(s) to Repeater.' % cnt)

    def _http_fetch(self, url, headers, max_redirects=3):
        u = urlparse(url)
        if not u.scheme or not u.netloc:
            raise Exception('Invalid URL')
        host = u.hostname
        port = u.port
        use_https = (u.scheme == 'https')
        if port is None:
            port = 443 if use_https else 80
        path = u.path or '/'
        if u.query:
            path = path + '?' + u.query
        # Build GET request
        lines = []
        lines.append('GET %s HTTP/1.1' % path)
        host_header = host
        if (use_https and port != 443) or ((not use_https) and port != 80):
            host_header = '%s:%d' % (host, port)
        lines.append('Host: %s' % host_header)
        lines.append('User-Agent: Swagger2Burp-Jython')
        lines.append('Accept: application/json, application/yaml, text/yaml, application/x-yaml, */*')
        for k, v in headers.items():
            try:
                if k.lower() == 'host':
                    continue
            except Exception:
                pass
            lines.append('%s: %s' % (k, v))
        req = '\r\n'.join(lines) + '\r\n\r\n'
        req_bytes = self._helpers.stringToBytes(req)
        # Prefer modern overload returning IHttpRequestResponse
        headers_list = None
        raw_head = None
        try:
            service = self._helpers.buildHttpService(host, int(port), use_https)
            rr = self._callbacks.makeHttpRequest(service, req_bytes)
            try:
                resp_bytes = rr.getResponse()
            except Exception:
                resp_bytes = rr
        except Exception:
            # Fallback to legacy overload returning raw bytes/array
            resp_bytes = self._callbacks.makeHttpRequest(host, int(port), use_https, req_bytes)

        if resp_bytes is None:
            raise Exception('No response received')

        # Try to use helpers.analyzeResponse; if that fails, do a manual parse
        status = 0
        ctype = ''
        body = ''
        try:
            an = self._helpers.analyzeResponse(resp_bytes)
            try:
                status = an.getStatusCode()
            except Exception:
                status = 0
            try:
                headers_list = list(an.getHeaders())
            except Exception:
                headers_list = None
            body_off = an.getBodyOffset()
            body_bytes = resp_bytes[body_off:]
            body = self._helpers.bytesToString(body_bytes)
            if headers_list:
                for h in headers_list:
                    try:
                        if h.lower().startswith('content-type:'):
                            ctype = h.split(':', 1)[1].strip()
                            break
                    except Exception:
                        continue
        except Exception:
            # Manual parse
            try:
                try:
                    raw_text = self._helpers.bytesToString(resp_bytes)
                except Exception:
                    try:
                        raw_text = resp_bytes.tostring()
                    except Exception:
                        raw_text = str(resp_bytes)
                parts = raw_text.split('\r\n\r\n', 1)
                raw_head = parts[0]
                body = parts[1] if len(parts) > 1 else ''
                first = raw_head.split('\r\n', 1)[0]
                if first.startswith('HTTP/'):
                    try:
                        status = int(first.split(' ')[1])
                    except Exception:
                        status = 0
                for line in raw_head.split('\r\n'):
                    if line.lower().startswith('content-type:'):
                        ctype = line.split(':', 1)[1].strip()
                        break
            except Exception:
                pass

        try:
            self._log('Fetch %s -> HTTP %s' % (url, status))
        except Exception:
            pass

        # Follow simple redirects
        if max_redirects > 0 and status in (301, 302, 303, 307, 308):
            loc = None
            try:
                if headers_list is not None:
                    for h in headers_list:
                        if h.lower().startswith('location:'):
                            loc = h.split(':', 1)[1].strip()
                            break
                elif raw_head is not None:
                    for line in raw_head.split('\r\n'):
                        if line.lower().startswith('location:'):
                            loc = line.split(':', 1)[1].strip()
                            break
            except Exception:
                loc = None
            if loc:
                if not (loc.startswith('http://') or loc.startswith('https://')):
                    # relative redirect
                    base = (u.scheme + '://' + u.netloc)
                    if loc.startswith('/'):
                        loc = base + loc
                    else:
                        from urlparse import urljoin as _uj
                        try:
                            loc = _uj(base + u.path, loc)
                        except Exception:
                            loc = base + '/' + loc
                return self._http_fetch(loc, headers, max_redirects - 1)

        return body, ctype

    def _load_spec_from_source_burp(self, src, fetch_headers):
        s = _strip(src)
        if not s:
            raise Exception('Empty source')
        # direct JSON text
        if _is_json_text(s):
            return json.loads(s)
        # URL
        if _looks_like_url(s):
            body, ctype = self._http_fetch(s, fetch_headers)
            # Try JSON first
            try:
                return json.loads(body)
            except Exception:
                pass
            # Try YAML if content-type or extension indicates YAML
            try:
                if 'yaml' in (ctype or '').lower() or s.endswith('.yaml') or s.endswith('.yml'):
                    return _parse_yaml(body)
            except Exception:
                # if YAML parsing not available, continue
                pass
            # Try alternative .json path
            alt = _try_alt_json_url(s)
            if alt is not None:
                try:
                    body2, _ = self._http_fetch(alt, fetch_headers)
                    return json.loads(body2)
                except Exception:
                    pass
            # Last attempt: parse YAML regardless
            try:
                return _parse_yaml(body)
            except Exception as e:
                raise Exception('Unable to parse as JSON or YAML (%s)' % e)
        # Raw pasted text but not JSON; attempt YAML
        return _parse_yaml(s)

    def _process_spec(self, spec, jwt, custom_headers, base_override, preview=False):
        helpers = self._helpers
        callbacks = self._callbacks

        is_oas3 = spec.get('openapi') is not None
        is_sw2 = spec.get('swagger') is not None

        base = None
        if _strip(base_override):
            base = base_override
        elif self._useSpecServers.isSelected():
            if is_oas3:
                base = _choose_base_from_oas3(spec)
            elif is_sw2:
                base = _choose_base_from_swagger2(spec)
        # base can be relative; we'll parse host from final URLs later

        paths = spec.get('paths') or {}
        total = 0
        prepared = []

        for raw_path, methods in paths.items():
            if not isinstance(methods, dict):
                continue

            # collect path-level parameters
            path_params_defs = []
            if 'parameters' in methods and isinstance(methods['parameters'], list):
                path_params_defs = methods['parameters']

            for method, op in methods.items():
                if method.lower() in ('get', 'post', 'put', 'delete', 'patch', 'options', 'head'):  # actual operations
                    op_obj = op
                else:
                    continue

                # merge parameters (path-level + op-level)
                params = []
                if isinstance(path_params_defs, list):
                    params.extend(path_params_defs)
                if isinstance(op_obj.get('parameters'), list):
                    params.extend(op_obj.get('parameters'))

                # Build path with replaced {param}
                final_path = raw_path
                if self._fillPathParams.isSelected():
                    # Extract {param} names and replace from params
                    names = re.findall(r"\{([^}]+)\}", raw_path)
                    for name in names:
                        replacement = None
                        for p in params:
                            if p.get('in') == 'path' and p.get('name') == name:
                                replacement = _param_example(p)
                                break
                        if replacement is None:
                            replacement = '123'
                        final_path = final_path.replace('{' + name + '}', str(replacement))

                # Query params
                query_pairs = []
                if self._includeQuery.isSelected():
                    for p in params:
                        if p.get('in') == 'query':
                            v = _param_example(p)
                            query_pairs.append((p.get('name'), v))
                query = _build_query(query_pairs)

                # Request body
                body = None
                content_type = None
                if is_oas3:
                    rb = op_obj.get('requestBody') or {}
                    content = rb.get('content') or {}
                    # prioritize application/json
                    mt = None
                    if 'application/json' in content:
                        mt = 'application/json'
                    elif len(content) > 0:
                        mt = list(content.keys())[0]
                    if mt:
                        content_type = mt
                        c = content.get(mt) or {}
                        body = _first_non_empty(c.get('example'), _safe_get(c, 'examples', 'default', 'value'))
                        if body is None:
                            body = _sample_value(c.get('schema') or {})
                elif is_sw2:
                    for p in params:
                        if p.get('in') == 'body':
                            schema = p.get('schema') or {}
                            body = _sample_value(schema)
                            content_type = 'application/json'
                            break

                # Headers
                headers = []
                if content_type:
                    headers.append(('Content-Type', content_type))
                # Authorization
                if jwt:
                    headers.append(('Authorization', 'Bearer ' + jwt))
                # Custom headers
                for (hn, hv) in custom_headers:
                    if hn.lower() == 'authorization' and jwt:
                        continue
                    headers.append((hn, hv))

                # Determine absolute URL to extract host/port/proto
                full_url = None
                if base:
                    full_url = _join_url(base, final_path)
                else:
                    # Try from servers (oas3) with relative base
                    if is_oas3:
                        cand = _choose_base_from_oas3(spec)
                        full_url = _join_url(cand or '/', final_path)
                    else:
                        full_url = final_path  # may be relative; we'll handle

                # parse host/port/https and path
                use_https = False
                host = None
                port = None
                path_with_query = final_path + (query or '')
                try:
                    if full_url and (full_url.startswith('http://') or full_url.startswith('https://')):
                        u = urlparse(full_url)
                        host = u.hostname
                        port = u.port
                        use_https = True if self._useHttps.isSelected() else False
                        if port is None:
                            port = 443 if use_https else 80
                        # path incl base + op path
                        # ensure we use path from URL (which already joined base+path)
                        base_path = u.path or '/'
                        url_q = u.query or ''
                        gen_q = query[1:] if (query and query.startswith('?')) else (query or '')
                        if url_q and gen_q:
                            combined_q = url_q + '&' + gen_q
                        else:
                            combined_q = url_q or gen_q
                        path_with_query = base_path + (('?' + combined_q) if combined_q else '')
                    else:
                        # No absolute base URL; cannot determine host
                        # Skip if base override is not provided
                        if not _strip(self._baseUrlField.getText()):
                            self._log('Skipping %s %s (no base URL / host). Set Base URL override.' % (method.upper(), final_path))
                            continue
                        # fallback handled earlier when base_override not empty
                except Exception as e:
                    self._log('URL parse error: %s' % e)
                    continue

                # Build Host header
                host_header = host
                if host and ((use_https and port != 443) or ((not use_https) and port != 80)):
                    host_header = '%s:%d' % (host, port)

                # Build HTTP request bytes
                req_bytes = _build_http_request(method, path_with_query, host_header, headers, body, helpers)

                caption = '%s %s' % (method.upper(), final_path)
                if preview:
                    label_target = ('https' if use_https else 'http') + '://' + self._format_hostport(host, port, use_https)
                    label = '%s %s  ->  %s' % (method.upper(), path_with_query or '/', label_target)
                    prepared.append({
                        'host': host,
                        'port': int(port),
                        'use_https': use_https,
                        'req_bytes': req_bytes,
                        'caption': caption,
                        'label': label
                    })
                else:
                    # Send to Repeater immediately
                    try:
                        callbacks.sendToRepeater(host, int(port), use_https, req_bytes, caption)
                        total += 1
                    except Exception as e:
                        self._log('Failed to send to Repeater: %s' % e)

        if preview:
            try:
                self._log('Prepared %d operations.' % len(prepared))
            except Exception:
                pass
            return prepared
        self._log('Processed %d operations.' % total)
        return total
