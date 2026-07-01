package com.lawassistant.lawservice.security;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
public class ProductionSafetyValidator implements ApplicationRunner {
    private static final Set<String> PRODUCTION_PROFILES =
            Set.of("prod", "production", "staging");
    private static final Set<String> UNSAFE_SECRET_VALUES =
            Set.of("law", "root", "admin", "password", "secret", "changeme", "change-me");

    private final Environment environment;
    private final AdminProperties adminProperties;
    private final RuntimeSafetyProperties runtimeSafetyProperties;

    public ProductionSafetyValidator(
            Environment environment,
            AdminProperties adminProperties,
            RuntimeSafetyProperties runtimeSafetyProperties) {
        this.environment = environment;
        this.adminProperties = adminProperties;
        this.runtimeSafetyProperties = runtimeSafetyProperties;
    }

    @Override
    public void run(ApplicationArguments args) {
        validate();
    }

    void validate() {
        if (!requiresSafeConfig()) {
            return;
        }

        List<String> failures = new ArrayList<>();
        if (isUnsafeSecret(adminProperties.getToken())) {
            failures.add("law-service.admin.token must be set to a non-default value");
        }
        rejectUnsafeValue(failures, "spring.datasource.username");
        rejectUnsafeValue(failures, "spring.datasource.password");
        rejectUnsafeValue(failures, "spring.rabbitmq.username");
        rejectUnsafeValue(failures, "spring.rabbitmq.password");

        if (!failures.isEmpty()) {
            throw new IllegalStateException(
                    "Unsafe production-like configuration: " + String.join("; ", failures));
        }
    }

    private boolean requiresSafeConfig() {
        if (runtimeSafetyProperties.isRequireSafeConfig()) {
            return true;
        }
        for (String profile : environment.getActiveProfiles()) {
            if (PRODUCTION_PROFILES.contains(profile.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }

    private void rejectUnsafeValue(List<String> failures, String propertyName) {
        if (isUnsafeSecret(environment.getProperty(propertyName))) {
            failures.add(propertyName + " must be set to a non-default value");
        }
    }

    static boolean isUnsafeSecret(String value) {
        if (!StringUtils.hasText(value)) {
            return true;
        }
        return UNSAFE_SECRET_VALUES.contains(value.trim().toLowerCase(Locale.ROOT));
    }
}
