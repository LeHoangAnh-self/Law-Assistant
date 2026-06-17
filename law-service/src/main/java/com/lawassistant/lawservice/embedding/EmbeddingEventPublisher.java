package com.lawassistant.lawservice.embedding;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class EmbeddingEventPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final EmbeddingRabbitProperties properties;

    public EmbeddingEventPublisher(RabbitTemplate rabbitTemplate, EmbeddingRabbitProperties properties) {
        this.rabbitTemplate = rabbitTemplate;
        this.properties = properties;
    }

    public void publishDocumentUpdated(Long documentId) {
        rabbitTemplate.convertAndSend(properties.getExchange(), properties.getRoutingKey(), EmbeddingUpdateEvent.documentUpdated(documentId));
    }
}
