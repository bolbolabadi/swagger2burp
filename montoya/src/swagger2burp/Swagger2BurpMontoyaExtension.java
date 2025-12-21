package com.alireza.swagger2burp;

import burp.api.montoya.BurpExtension;
import burp.api.montoya.MontoyaApi;
import burp.api.montoya.http.message.requests.HttpRequest;
import burp.api.montoya.http.message.HttpRequestResponse;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.yaml.snakeyaml.Yaml;

import javax.swing.*;
import java.awt.*;
import java.net.URI;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.List;
import java.util.Set;
import java.util.LinkedHashSet;
import java.util.regex.Pattern;
import java.util.regex.Matcher;

import static burp.api.montoya.http.HttpService.httpService;
import static burp.api.montoya.http.message.requests.HttpRequest.httpRequest;
import static burp.api.montoya.http.message.requests.HttpRequest.httpRequestFromUrl;

public class Swagger2BurpMontoyaExtension implements BurpExtension {

    private MontoyaApi api;
    private JPanel panel;

    private JTextField jwtField;
    private JTextArea headersArea;
    private JTextField baseUrlField;
    private JComboBox<String> modeCombo;
    private JTextArea sourcesArea;

    private JCheckBox includeQuery;
    private JCheckBox fillPathParams;
    private JCheckBox useSpecServers;
    private JCheckBox useHttps;

    private JButton importBtn;
    private JButton clearLogBtn;
    private JCheckBox selectAllChk;
    private JButton sendSelectedBtn;

    private JPanel requestsListPanel;
    private JTextArea logArea;

    private final List<PreparedItem> requestItems = new ArrayList<PreparedItem>();
    private volatile Thread worker;

    private static class PreparedItem {
        JCheckBox checkbox;
        HttpRequest request;
        String caption;
        String host;
        int port;
        String method;
        String pathWithQuery;
        boolean wasHttps;
    }

    @Override
    public void initialize(MontoyaApi api) {
        this.api = api;
        api.extension().setName("Swagger2Burp");
        SwingUtilities.invokeLater(() -> {
            panel = buildUi();
            api.userInterface().registerSuiteTab("Swagger2Burp", panel);
        });
        api.extension().registerUnloadingHandler(() -> {
            Thread w = worker;
            if (w != null) {
                try {
                    w.interrupt();
                } catch (Exception ignored) {}
            }
        });
    }

    private JPanel buildUi() {
        JPanel p = new JPanel(new BorderLayout());

        JPanel form = new JPanel(new GridBagLayout());
        GridBagConstraints gbc = new GridBagConstraints();
        gbc.insets = new Insets(4, 4, 4, 4);
        gbc.fill = GridBagConstraints.HORIZONTAL;
        gbc.weightx = 1.0;

        int row = 0;

        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0;
        form.add(new JLabel("JWT (optional):"), gbc);
        jwtField = new JTextField();
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0;
        form.add(jwtField, gbc);
        row++;

        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0;
        form.add(new JLabel("Custom headers (one per line, k: v):"), gbc);
        headersArea = new JTextArea(5, 50);
        JScrollPane headersScroll = new JScrollPane(headersArea);
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0;
        form.add(headersScroll, gbc);
        row++;

        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0;
        form.add(new JLabel("Base URL override (optional):"), gbc);
        baseUrlField = new JTextField();
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0;
        form.add(baseUrlField, gbc);
        row++;

        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0;
        form.add(new JLabel("Input mode:"), gbc);
        modeCombo = new JComboBox<String>(new String[]{"Auto-detect", "URL(s)", "Raw JSON"});
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0;
        form.add(modeCombo, gbc);
        row++;

        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0;
        form.add(new JLabel("Swagger/OpenAPI sources (one per line or paste JSON):"), gbc);
        sourcesArea = new JTextArea(8, 50);
        JScrollPane sourcesScroll = new JScrollPane(sourcesArea);
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0;
        form.add(sourcesScroll, gbc);
        row++;

        includeQuery = new JCheckBox("Include query parameters", true);
        fillPathParams = new JCheckBox("Fill path parameters", true);
        useSpecServers = new JCheckBox("Use servers/basePath from spec (unless base override is set)", true);
        useHttps = new JCheckBox("Use HTTPS", true);

        JPanel optsPanel = new JPanel(new GridBagLayout());
        GridBagConstraints gbc2 = new GridBagConstraints();
        gbc2.insets = new Insets(2, 2, 2, 2);
        gbc2.anchor = GridBagConstraints.WEST;
        gbc2.gridx = 0; gbc2.gridy = 0;
        optsPanel.add(includeQuery, gbc2);
        gbc2.gridy += 1;
        optsPanel.add(fillPathParams, gbc2);
        gbc2.gridy += 1;
        optsPanel.add(useSpecServers, gbc2);
        gbc2.gridy += 1;
        optsPanel.add(useHttps, gbc2);

        gbc.gridx = 0; gbc.gridy = row; gbc.weightx = 0.0;
        form.add(new JLabel("Options:"), gbc);
        gbc.gridx = 1; gbc.gridy = row; gbc.weightx = 1.0;
        form.add(optsPanel, gbc);
        row++;

        importBtn = new JButton("Import");
        clearLogBtn = new JButton("Clear log");
        JPanel btnPanel = new JPanel();
        btnPanel.add(importBtn);
        btnPanel.add(clearLogBtn);

        requestsListPanel = new JPanel(new GridBagLayout());
        JScrollPane reqScroll = new JScrollPane(requestsListPanel);
        reqScroll.setBorder(BorderFactory.createTitledBorder("Requests"));
        selectAllChk = new JCheckBox("Select all");
        sendSelectedBtn = new JButton("Send selected to Repeater");
        JPanel controls = new JPanel();
        controls.add(selectAllChk);
        controls.add(sendSelectedBtn);

        JPanel mid = new JPanel(new BorderLayout());
        mid.add(btnPanel, BorderLayout.NORTH);
        mid.add(reqScroll, BorderLayout.CENTER);
        mid.add(controls, BorderLayout.SOUTH);

        logArea = new JTextArea(10, 80);
        logArea.setEditable(false);
        JScrollPane logScroll = new JScrollPane(logArea);
        logScroll.setBorder(BorderFactory.createTitledBorder("Log"));

        p.add(form, BorderLayout.NORTH);
        p.add(mid, BorderLayout.CENTER);
        p.add(logScroll, BorderLayout.SOUTH);

        importBtn.addActionListener(e -> onImport());
        clearLogBtn.addActionListener(e -> logArea.setText(""));
        selectAllChk.addActionListener(e -> onSelectAll());
        sendSelectedBtn.addActionListener(e -> sendSelected());

        return p;
    }

    private void onImport() {
        final String sourcesRaw = sourcesArea.getText() != null ? sourcesArea.getText() : "";
        final String mode = (String) modeCombo.getSelectedItem();
        importBtn.setEnabled(false);
        selectAllChk.setSelected(false);
        requestsListPanel.removeAll();
        requestsListPanel.revalidate();
        requestsListPanel.repaint();

        Thread t = new Thread(() -> {
            List<String> sources = new ArrayList<String>();
            String trimmed = sourcesRaw.trim();
            if ("Raw JSON".equals(mode)) {
                if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
                    sources = Collections.singletonList(trimmed);
                }
            } else if ("URL(s)".equals(mode)) {
                for (String l : sourcesRaw.split("\n")) {
                    String s = l.trim();
                    if (!s.isEmpty()) {
                        sources.add(s);
                    }
                }
            } else {
                if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
                    sources = Collections.singletonList(trimmed);
                } else {
                    for (String l : sourcesRaw.split("\n")) {
                        String s = l.trim();
                        if (!s.isEmpty()) {
                            sources.add(s);
                        }
                    }
                }
            }

            List<String[]> fetchHeaders = buildSpecFetchHeaders();
            List<PreparedItem> built = new ArrayList<PreparedItem>();
            for (String src : sources) {
                if (Thread.currentThread().isInterrupted()) {
                    return;
                }
                try {
                    Map spec = loadSpecFromSource(src, fetchHeaders);
                    List<PreparedItem> items = processSpec(spec, src);
                    built.addAll(items);
                } catch (Exception ex) {
                    log("Failed source: " + src + " (" + ex + ")");
                }
            }

            SwingUtilities.invokeLater(() -> {
                requestItems.clear();
                requestItems.addAll(built);
                GridBagConstraints gbc = new GridBagConstraints();
                gbc.insets = new Insets(2, 2, 2, 2);
                gbc.anchor = GridBagConstraints.WEST;
                gbc.fill = GridBagConstraints.HORIZONTAL;
                gbc.weightx = 1.0;
                gbc.gridx = 0;
                int row = 0;
                for (PreparedItem it2 : built) {
                    gbc.gridy = row++;
                    requestsListPanel.add(it2.checkbox, gbc);
                }
                requestsListPanel.revalidate();
                requestsListPanel.repaint();
                importBtn.setEnabled(true);
                log("Prepared " + built.size() + " request(s). Review and send selected.");
            });
        }, "S2B-Import");
        try { t.setDaemon(true); } catch (Exception ignored) {}
        worker = t;
        t.start();
    }

    private PreparedItem buildItemFromUrl(String url) {
        try {
            URI u = URI.create(url);
            String host = u.getHost();
            if (host == null || host.isEmpty()) {
                return null;
            }
            boolean httpsSel = useHttps.isSelected();
            int port = u.getPort();
            if (port < 0) {
                port = httpsSel ? 443 : 80;
            }
            String path = u.getRawPath();
            if (path == null || path.isEmpty()) {
                path = "/";
            }
            String q = u.getRawQuery();
            String pathWithQuery = q != null && !q.isEmpty() ? path + "?" + q : path;

            String hostHeader = host;
            if ((httpsSel && port != 443) || (!httpsSel && port != 80)) {
                hostHeader = host + ":" + port;
            }

            List<String> headerLines = new ArrayList<String>();
            headerLines.add("Host: " + hostHeader);
            headerLines.add("Accept: application/json");
            String jwt = jwtField.getText() != null ? jwtField.getText().trim() : "";
            if (!jwt.isEmpty()) {
                headerLines.add("Authorization: Bearer " + jwt);
            }
            for (String[] kv : parseCustomHeaders(headersArea.getText() != null ? headersArea.getText() : "")) {
                String name = kv[0];
                String val = kv[1];
                if (name.equalsIgnoreCase("host")) {
                    continue;
                }
                if (name.equalsIgnoreCase("authorization") && !jwt.isEmpty()) {
                    continue;
                }
                headerLines.add(name + ": " + val);
            }

            StringBuilder sb = new StringBuilder();
            sb.append("GET ").append(pathWithQuery).append(" HTTP/1.1\r\n");
            for (String h : headerLines) {
                sb.append(h).append("\r\n");
            }
            sb.append("\r\n");

            HttpRequest req = httpRequest(httpService(host, port, httpsSel), sb.toString());

            PreparedItem it = new PreparedItem();
            String labelTarget = (httpsSel ? "https" : "http") + "://" + ((httpsSel && port == 443) || (!httpsSel && port == 80) ? host : host + ":" + port);
            String label = "GET " + pathWithQuery + "  ->  " + labelTarget;
            it.caption = "GET " + path;
            it.request = req;
            it.checkbox = new JCheckBox(label);
            it.host = host;
            it.port = port;
            it.method = "GET";
            it.pathWithQuery = pathWithQuery;
            it.wasHttps = httpsSel;
            return it;
        } catch (Exception ex) {
            return null;
        }
    }

    private void onSelectAll() {
        boolean sel = selectAllChk.isSelected();
        for (PreparedItem it : requestItems) {
            it.checkbox.setSelected(sel);
        }
    }

    private void sendSelected() {
        int cnt = 0;
        boolean httpsNow = useHttps.isSelected();
        for (PreparedItem it : requestItems) {
            if (!it.checkbox.isSelected()) continue;
            try {
                int port = it.port;
                if (it.wasHttps != httpsNow) {
                    if (it.port == 443 && !httpsNow) port = 80;
                    else if (it.port == 80 && httpsNow) port = 443;
                }

                String hostHeader = it.host;
                if ((httpsNow && port != 443) || (!httpsNow && port != 80)) hostHeader = it.host + ":" + port;

                List<String> headerLines = new ArrayList<String>();
                headerLines.add("Host: " + hostHeader);
                headerLines.add("Accept: application/json");
                String jwt = jwtField.getText() != null ? jwtField.getText().trim() : "";
                if (!jwt.isEmpty()) headerLines.add("Authorization: Bearer " + jwt);
                for (String[] kv : parseCustomHeaders(headersArea.getText() != null ? headersArea.getText() : "")) {
                    String name = kv[0];
                    String val = kv[1];
                    if (name.equalsIgnoreCase("host")) continue;
                    if (name.equalsIgnoreCase("authorization") && !jwt.isEmpty()) continue;
                    headerLines.add(name + ": " + val);
                }

                StringBuilder sb = new StringBuilder();
                sb.append(it.method).append(" ").append(it.pathWithQuery).append(" HTTP/1.1\r\n");
                for (String h : headerLines) sb.append(h).append("\r\n");
                sb.append("\r\n");

                HttpRequest req = httpRequest(httpService(it.host, port, httpsNow), sb.toString());
                api.repeater().sendToRepeater(req, it.caption);
                cnt += 1;
            } catch (Exception ex) {
                log("Failed to send to Repeater: " + ex);
            }
        }
        log("Sent " + cnt + " request(s) to Repeater.");
    }

    private List<String[]> parseCustomHeaders(String text) {
        List<String[]> list = new ArrayList<String[]>();
        if (text == null) {
            return list;
        }
        for (String line : text.split("\n")) {
            String l = line.trim();
            if (l.isEmpty()) {
                continue;
            }
            String name;
            String val;
            int i = l.indexOf(':');
            if (i >= 0) {
                name = l.substring(0, i).trim();
                val = l.substring(i + 1).trim();
            } else {
                int j = l.indexOf('=');
                if (j >= 0) {
                    name = l.substring(0, j).trim();
                    val = l.substring(j + 1).trim();
                } else {
                    continue;
                }
            }
            if (!name.isEmpty()) {
                list.add(new String[]{name, val});
            }
        }
        return list;
    }

    private void log(String msg) {
        try {
            logArea.append(String.valueOf(msg) + "\n");
            logArea.setCaretPosition(logArea.getDocument().getLength());
        } catch (Exception ignored) {
        }
    }

    private List<String[]> buildSpecFetchHeaders() {
        List<String[]> hs = new ArrayList<String[]>();
        String jwt = jwtField.getText() != null ? jwtField.getText().trim() : "";
        if (!jwt.isEmpty()) {
            hs.add(new String[]{"Authorization", "Bearer " + jwt});
        }
        for (String[] kv : parseCustomHeaders(headersArea.getText() != null ? headersArea.getText() : "")) {
            String name = kv[0];
            String val = kv[1];
            if (name.equalsIgnoreCase("authorization") && !jwt.isEmpty()) {
                continue;
            }
            hs.add(new String[]{name, val});
        }
        return hs;
    }

    private Map loadSpecFromSource(String src, List<String[]> fetchHeaders) throws Exception {
        String s = src != null ? src.trim() : "";
        if (s.isEmpty()) {
            throw new IllegalArgumentException("Empty source");
        }
        if (s.startsWith("{") || s.startsWith("[")) {
            return parseJson(s);
        }
        if (s.startsWith("http://") || s.startsWith("https://")) {
            String body = fetchText(s, fetchHeaders);
            try { return parseJson(body); } catch (Exception ignored) {}
            try { return parseYaml(body); } catch (Exception ignored) {}
            String alt = tryAltJsonUrl(s);
            if (alt != null) {
                String b2 = fetchText(alt, fetchHeaders);
                return parseJson(b2);
            }
            return parseYaml(body);
        }
        return parseYaml(s);
    }

    private String fetchText(String url, List<String[]> headers) throws Exception {
        HttpRequest req = httpRequestFromUrl(url);
        HttpRequest req2 = req
                .withUpdatedHeader("User-Agent", "Swagger2Burp-Montoya")
                .withUpdatedHeader("Accept", "application/json, application/yaml, text/yaml, application/x-yaml, */*");
        for (String[] kv : headers) {
            if (!kv[0].equalsIgnoreCase("host")) {
                req2 = req2.withUpdatedHeader(kv[0], kv[1]);
            }
        }
        HttpRequestResponse rr = api.http().sendRequest(req2);
        if (rr == null || rr.response() == null) {
            throw new IllegalStateException("No response");
        }
        return rr.response().body().toString();
    }

    private Map parseJson(String text) throws Exception {
        ObjectMapper om = new ObjectMapper();
        return om.readValue(text, Map.class);
    }

    private Map parseYaml(String text) throws Exception {
        Yaml y = new Yaml();
        Object o = y.load(text);
        if (o instanceof Map) {
            return (Map) o;
        }
        throw new IllegalArgumentException("YAML parse failed");
    }

    private String tryAltJsonUrl(String url) {
        if (url.endsWith(".yaml")) return url.substring(0, url.length()-5) + ".json";
        if (url.endsWith(".yml")) return url.substring(0, url.length()-4) + ".json";
        return null;
    }

    private List<PreparedItem> processSpec(Map spec, String source) {
        List<PreparedItem> out = new ArrayList<PreparedItem>();
        if (spec == null) return out;
        boolean isOas3 = spec.containsKey("openapi");
        boolean isSw2 = spec.containsKey("swagger");
        String baseOverride = baseUrlField.getText() != null ? baseUrlField.getText().trim() : "";
        List<String> bases = new ArrayList<String>();
        if (!baseOverride.isEmpty()) {
            bases.add(baseOverride);
        } else if (useSpecServers.isSelected()) {
            if (isOas3) {
                bases.addAll(chooseBasesFromOas3(spec, source));
            } else if (isSw2) {
                bases.addAll(chooseBasesFromSwagger2(spec, source));
            }
        } else {
            String b = finalizeBase(null, source);
            if (b != null) bases.add(b);
        }
        LinkedHashSet<String> dedup = new LinkedHashSet<String>(bases);
        bases = new ArrayList<String>(dedup);
        Object pathsObj = spec.get("paths");
        if (!(pathsObj instanceof Map)) return out;
        Map paths = (Map) pathsObj;
        for (Object pk : paths.keySet()) {
            String rawPath = String.valueOf(pk);
            Object methods = paths.get(pk);
            if (!(methods instanceof Map)) continue;
            Map m = (Map) methods;
            for (Object mk : m.keySet()) {
                String method = String.valueOf(mk).toLowerCase();
                if (!Arrays.asList("get","post","put","delete","patch","options","head","trace").contains(method)) {
                    continue;
                }
                for (String b : bases) {
                    PreparedItem it = buildItemFromSpec(b, method, rawPath);
                    if (it != null) out.add(it);
                }
            }
        }
        return out;
    }

    private PreparedItem buildItemFromSpec(String base, String method, String rawPath) {
        try {
            String full = base != null ? joinUrl(base, rawPath) : rawPath;
            if (!(full.startsWith("http://") || full.startsWith("https://"))) {
                log("Skipping " + method.toUpperCase() + " " + rawPath + " (no absolute base). Set Base URL override.");
                return null;
            }
            URI u = URI.create(full);
            String host = u.getHost();
            if (host == null || host.isEmpty()) return null;
            boolean httpsSel = useHttps.isSelected();
            int port = u.getPort();
            if (port < 0) port = httpsSel ? 443 : 80;
            String path = u.getRawPath();
            if (path == null || path.isEmpty()) path = "/";
            String q = u.getRawQuery();
            String pathWithQuery = q != null && !q.isEmpty() ? path + "?" + q : path;

            String hostHeader = host;
            if ((httpsSel && port != 443) || (!httpsSel && port != 80)) hostHeader = host + ":" + port;
            List<String> headerLines = new ArrayList<String>();
            headerLines.add("Host: " + hostHeader);
            headerLines.add("Accept: application/json");
            String jwt = jwtField.getText() != null ? jwtField.getText().trim() : "";
            if (!jwt.isEmpty()) headerLines.add("Authorization: Bearer " + jwt);
            for (String[] kv : parseCustomHeaders(headersArea.getText() != null ? headersArea.getText() : "")) {
                String name = kv[0];
                String val = kv[1];
                if (name.equalsIgnoreCase("host")) continue;
                if (name.equalsIgnoreCase("authorization") && !jwt.isEmpty()) continue;
                headerLines.add(name + ": " + val);
            }

            StringBuilder sb = new StringBuilder();
            sb.append(method.toUpperCase()).append(" ").append(pathWithQuery).append(" HTTP/1.1\r\n");
            for (String h : headerLines) sb.append(h).append("\r\n");
            sb.append("\r\n");
            HttpRequest req = httpRequest(httpService(host, port, httpsSel), sb.toString());

            PreparedItem it = new PreparedItem();
            String labelTarget = (httpsSel ? "https" : "http") + "://" + ((httpsSel && port == 443) || (!httpsSel && port == 80) ? host : host + ":" + port);
            String label = method.toUpperCase() + " " + pathWithQuery + "  ->  " + labelTarget;
            it.caption = method.toUpperCase() + " " + rawPath;
            it.request = req;
            it.checkbox = new JCheckBox(label);
            it.host = host;
            it.port = port;
            it.method = method.toUpperCase();
            it.pathWithQuery = pathWithQuery;
            it.wasHttps = httpsSel;
            return it;
        } catch (Exception ex) {
            return null;
        }
    }

    private String joinUrl(String base, String path) {
        try {
            URI b = URI.create(base);
            String bp = b.getPath();
            if (bp == null) bp = "";
            if (!bp.endsWith("/")) bp = bp + "/";
            String pp = path == null ? "" : path;
            if (pp.startsWith("/")) pp = pp.substring(1);
            String newPath = bp + pp;
            URI out = new URI(b.getScheme(), b.getAuthority(), newPath, null, null);
            return out.toString();
        } catch (Exception e) {
            if (base.endsWith("/") && path.startsWith("/")) return base.substring(0, base.length()-1) + path;
            if (!base.endsWith("/") && !path.startsWith("/")) return base + "/" + path;
            return base + path;
        }
    }

    private String chooseBaseFromOas3(Map spec) {
        Object serversObj = spec.get("servers");
        if (serversObj instanceof List) {
            List servers = (List) serversObj;
            if (!servers.isEmpty() && servers.get(0) instanceof Map) {
                Object url = ((Map) servers.get(0)).get("url");
                if (url != null) return String.valueOf(url);
            }
        }
        return null;
    }

    private List<String> chooseBasesFromOas3(Map spec, String source) {
        List<String> out = new ArrayList<String>();
        Object serversObj = spec.get("servers");
        if (serversObj instanceof List) {
            List servers = (List) serversObj;
            for (Object s : servers) {
                if (s instanceof Map) {
                    Object u = ((Map) s).get("url");
                    Object vars = ((Map) s).get("variables");
                    if (u != null) {
                        if (vars instanceof Map) {
                            out.addAll(expandServerBases(String.valueOf(u), (Map) vars, source));
                        } else {
                            String b = finalizeBase(String.valueOf(u), source);
                            if (b != null) out.add(b);
                        }
                    }
                }
            }
        }
        if (out.isEmpty()) {
            String f = finalizeBase(null, source);
            if (f != null) out.add(f);
        }
        return out;
    }

    private List<String> expandServerBases(String template, Map vars, String source) {
        List<String> seeds = new ArrayList<String>();
        seeds.add(template);
        if (vars != null && !vars.isEmpty()) {
            for (Object k : vars.keySet()) {
                String name = String.valueOf(k);
                Object vdef = vars.get(k);
                List<String> choices = new ArrayList<String>();
                if (vdef instanceof Map) {
                    Object en = ((Map) vdef).get("enum");
                    if (en instanceof List && !((List) en).isEmpty()) {
                        for (Object e : (List) en) choices.add(String.valueOf(e));
                    } else {
                        Object def = ((Map) vdef).get("default");
                        if (def != null) choices.add(String.valueOf(def));
                    }
                }
                if (choices.isEmpty()) continue;
                List<String> next = new ArrayList<String>();
                String token = "{" + name + "}";
                for (String s : seeds) {
                    for (String c : choices) {
                        next.add(s.replace(token, c));
                    }
                }
                seeds = next;
            }
        }
        List<String> out = new ArrayList<String>();
        for (String s : seeds) {
            String b = finalizeBase(s, source);
            if (b != null) out.add(b);
        }
        return out;
    }

    private List<String> chooseBasesFromSwagger2(Map spec, String source) {
        List<String> out = new ArrayList<String>();
        Object schemesObj = spec.get("schemes");
        List schemes = (schemesObj instanceof List) ? (List) schemesObj : Collections.emptyList();
        String host = String.valueOf(spec.get("host") != null ? spec.get("host") : "");
        String basePath = String.valueOf(spec.get("basePath") != null ? spec.get("basePath") : "/");
        if (!basePath.startsWith("/")) basePath = "/" + basePath;
        if (host == null || host.isEmpty()) {
            String fb = finalizeBase(null, source);
            if (fb != null) out.add(fb);
            return out;
        }
        if (schemes.isEmpty()) {
            schemes = Arrays.asList("https");
        }
        for (Object s : schemes) {
            String b = String.valueOf(s) + "://" + host + basePath;
            String f = finalizeBase(b, source);
            if (f != null) out.add(f);
        }
        return out;
    }

    private String originFromUrl(String src) {
        try {
            if (src == null) return null;
            String s = src.trim();
            if (!(s.startsWith("http://") || s.startsWith("https://"))) return null;
            URI u = URI.create(s);
            String host = u.getHost();
            if (host == null || host.isEmpty()) return null;
            int port = u.getPort();
            String scheme = u.getScheme();
            if (port > 0) return scheme + "://" + host + ":" + port;
            return scheme + "://" + host;
        } catch (Exception e) {
            return null;
        }
    }

    private String finalizeBase(String candidate, String source) {
        String origin = originFromUrl(source);
        if (candidate == null || candidate.isEmpty()) {
            return origin;
        }
        String c = candidate.trim();
        if (c.startsWith("http://") || c.startsWith("https://")) {
            return c;
        }
        if (c.startsWith("/")) {
            if (origin != null) return joinUrl(origin, c);
            return null;
        }
        if (origin != null) return joinUrl(origin, c);
        return null;
    }
}
