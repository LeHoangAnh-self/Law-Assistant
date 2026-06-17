package com.lawassistant.lawservice.embedding;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(EmbeddingRabbitProperties.class)
public class RabbitMqConfig {

    @Bean
    DirectExchange embeddingExchange(EmbeddingRabbitProperties properties) {
        return new DirectExchange(properties.getExchange(), true, false);
    }

    @Bean
    Queue embeddingQueue(EmbeddingRabbitProperties properties) {
        return new Queue(properties.getQueue(), true);
    }

    @Bean
    Binding embeddingBinding(Queue embeddingQueue, DirectExchange embeddingExchange, EmbeddingRabbitProperties properties) {
        return BindingBuilder.bind(embeddingQueue).to(embeddingExchange).with(properties.getRoutingKey());
    }

    @Bean
    Jackson2JsonMessageConverter jackson2JsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    RabbitTemplate rabbitTemplate(
            org.springframework.amqp.rabbit.connection.ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter converter) {
        RabbitTemplate rabbitTemplate = new RabbitTemplate(connectionFactory);
        rabbitTemplate.setMessageConverter(converter);
        return rabbitTemplate;
    }
}
