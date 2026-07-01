package com.lawassistant.lawservice.security;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableConfigurationProperties({AdminProperties.class, RuntimeSafetyProperties.class})
public class AdminWebConfig implements WebMvcConfigurer {
    private final AdminTokenInterceptor adminTokenInterceptor;

    public AdminWebConfig(AdminTokenInterceptor adminTokenInterceptor) {
        this.adminTokenInterceptor = adminTokenInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(adminTokenInterceptor)
                .addPathPatterns(
                        "/api/imports/provided-data",
                        "/api/documents/embedding-events",
                        "/api/documents/*/embedding-events");
    }
}
