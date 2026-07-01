package com.lawassistant.lawservice.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "law-service.security")
public class RuntimeSafetyProperties {
    private boolean requireSafeConfig = false;

    public boolean isRequireSafeConfig() {
        return requireSafeConfig;
    }

    public void setRequireSafeConfig(boolean requireSafeConfig) {
        this.requireSafeConfig = requireSafeConfig;
    }
}
