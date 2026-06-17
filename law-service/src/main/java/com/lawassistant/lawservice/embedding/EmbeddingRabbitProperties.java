package com.lawassistant.lawservice.embedding;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "law-service.embedding.rabbit")
public class EmbeddingRabbitProperties {
    private String exchange = "law.embedding";
    private String queue = "law.embedding.update";
    private String routingKey = "law.document.embedding.update";

    public String getExchange() { return exchange; }
    public void setExchange(String exchange) { this.exchange = exchange; }
    public String getQueue() { return queue; }
    public void setQueue(String queue) { this.queue = queue; }
    public String getRoutingKey() { return routingKey; }
    public void setRoutingKey(String routingKey) { this.routingKey = routingKey; }
}
