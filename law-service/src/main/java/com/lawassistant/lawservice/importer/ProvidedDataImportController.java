package com.lawassistant.lawservice.importer;

import java.io.IOException;
import java.nio.file.Path;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/imports")
public class ProvidedDataImportController {

    private final ProvidedDataImportService importService;

    public ProvidedDataImportController(ProvidedDataImportService importService) {
        this.importService = importService;
    }

    @PostMapping("/provided-data")
    public ProvidedDataImportResult importProvidedData(
            @RequestParam(defaultValue = "../data") String sourceDirectory,
            @RequestParam(defaultValue = "false") boolean publishEmbeddingEvents) throws IOException {
        return importService.importFrom(Path.of(sourceDirectory), publishEmbeddingEvents);
    }
}
