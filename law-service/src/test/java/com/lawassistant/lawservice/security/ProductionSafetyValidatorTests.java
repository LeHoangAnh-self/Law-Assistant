package com.lawassistant.lawservice.security;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class ProductionSafetyValidatorTests {
    @Test
    void productionProfileRejectsDefaultCredentialsAndMissingAdminToken() {
        AdminProperties adminProperties = new AdminProperties();
        RuntimeSafetyProperties safetyProperties = new RuntimeSafetyProperties();
        MockEnvironment environment = new MockEnvironment()
                .withProperty("spring.profiles.active", "prod")
                .withProperty("spring.datasource.username", "law")
                .withProperty("spring.datasource.password", "law")
                .withProperty("spring.rabbitmq.username", "law")
                .withProperty("spring.rabbitmq.password", "law");
        environment.setActiveProfiles("prod");

        ProductionSafetyValidator validator =
                new ProductionSafetyValidator(environment, adminProperties, safetyProperties);

        assertThatThrownBy(validator::validate)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("law-service.admin.token")
                .hasMessageContaining("spring.datasource.username")
                .hasMessageContaining("spring.rabbitmq.password");
    }

    @Test
    void productionProfileAllowsNonDefaultCredentials() {
        AdminProperties adminProperties = new AdminProperties();
        adminProperties.setToken("prod-token-from-secret-store");
        RuntimeSafetyProperties safetyProperties = new RuntimeSafetyProperties();
        MockEnvironment environment = new MockEnvironment()
                .withProperty("spring.datasource.username", "law_app")
                .withProperty("spring.datasource.password", "unique-db-password")
                .withProperty("spring.rabbitmq.username", "law_events")
                .withProperty("spring.rabbitmq.password", "unique-rabbit-password");
        environment.setActiveProfiles("prod");

        ProductionSafetyValidator validator =
                new ProductionSafetyValidator(environment, adminProperties, safetyProperties);

        assertThatCode(validator::validate).doesNotThrowAnyException();
    }
}
