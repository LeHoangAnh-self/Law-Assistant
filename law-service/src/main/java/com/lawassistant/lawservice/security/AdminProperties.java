package com.lawassistant.lawservice.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.StringUtils;

@ConfigurationProperties(prefix = "law-service.admin")
public class AdminProperties {
    private String token = "";
    private String headerName = "X-Admin-Token";

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }

    public String getHeaderName() {
        return headerName;
    }

    public void setHeaderName(String headerName) {
        this.headerName = headerName;
    }

    public boolean hasToken() {
        return StringUtils.hasText(token);
    }

    public boolean matches(String candidate) {
        if (!hasToken() || !StringUtils.hasText(candidate)) {
            return false;
        }
        byte[] expected = token.getBytes(StandardCharsets.UTF_8);
        byte[] actual = candidate.getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(expected, actual);
    }
}
