package com.lawassistant.lawservice.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class AdminTokenInterceptor implements HandlerInterceptor {
    private final AdminProperties adminProperties;

    public AdminTokenInterceptor(AdminProperties adminProperties) {
        this.adminProperties = adminProperties;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {
        if (!HttpMethod.POST.matches(request.getMethod())) {
            return true;
        }
        if (!adminProperties.hasToken()) {
            response.sendError(
                    HttpServletResponse.SC_FORBIDDEN,
                    "Admin token is not configured for privileged endpoints.");
            return false;
        }

        String providedToken = request.getHeader(adminProperties.getHeaderName());
        if (providedToken == null || providedToken.isBlank()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Missing admin token.");
            return false;
        }
        if (!adminProperties.matches(providedToken)) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "Invalid admin token.");
            return false;
        }
        return true;
    }
}
