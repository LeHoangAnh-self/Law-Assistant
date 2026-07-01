package com.lawassistant.lawservice.security;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.lawassistant.lawservice.document.LegalDocumentService;
import com.lawassistant.lawservice.embedding.EmbeddingEventPublisher;
import com.lawassistant.lawservice.importer.ProvidedDataImportController;
import com.lawassistant.lawservice.importer.ProvidedDataImportResult;
import com.lawassistant.lawservice.importer.ProvidedDataImportService;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = {
        ProvidedDataImportController.class,
        com.lawassistant.lawservice.document.LegalDocumentController.class
})
@Import({AdminWebConfig.class, AdminTokenInterceptor.class})
@TestPropertySource(properties = "law-service.admin.token=test-admin-token")
class AdminBoundaryControllerTests {
    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private ProvidedDataImportService importService;

    @MockitoBean
    private LegalDocumentService documentService;

    @MockitoBean
    private EmbeddingEventPublisher embeddingEventPublisher;

    @Test
    void privilegedEndpointsRejectMissingAdminToken() throws Exception {
        mockMvc.perform(post("/api/imports/provided-data"))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(post("/api/documents/embedding-events"))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(post("/api/documents/42/embedding-events"))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(patch("/api/documents/42/embedding-status")
                        .param("status", "INDEXING"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void privilegedEndpointsRejectWrongAdminToken() throws Exception {
        mockMvc.perform(post("/api/documents/embedding-events")
                        .header("X-Admin-Token", "wrong"))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedImportRequestSucceeds() throws Exception {
        when(importService.importFrom(any(Path.class), eq(false)))
                .thenReturn(new ProvidedDataImportResult(1, 2, 3, false));

        mockMvc.perform(post("/api/imports/provided-data")
                        .header("X-Admin-Token", "test-admin-token")
                        .param("sourceDirectory", "../data_usable/current_new"))
                .andExpect(status().isOk());

        verify(importService).importFrom(Path.of("../data_usable/current_new"), false);
    }

    @Test
    void authenticatedEmbeddingRequestsSucceed() throws Exception {
        when(documentService.findAllDocumentIds()).thenReturn(List.of(10L, 11L));

        mockMvc.perform(post("/api/documents/42/embedding-events")
                        .header("X-Admin-Token", "test-admin-token"))
                .andExpect(status().isOk());

        mockMvc.perform(post("/api/documents/embedding-events")
                        .header("X-Admin-Token", "test-admin-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("2"));

        verify(embeddingEventPublisher).publishDocumentUpdated(42L);
        verify(embeddingEventPublisher).publishDocumentUpdated(10L);
        verify(embeddingEventPublisher).publishDocumentUpdated(11L);
    }

    @Test
    void authenticatedStatusUpdateSucceeds() throws Exception {
        mockMvc.perform(patch("/api/documents/42/embedding-status")
                        .header("X-Admin-Token", "test-admin-token")
                        .param("status", "INDEXED"))
                .andExpect(status().isOk());

        verify(documentService).updateEmbeddingStatus(42L, "INDEXED");
    }
}
