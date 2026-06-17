package com.lawassistant.lawservice.cache;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lawassistant.lawservice.document.LegalDocumentDetail;
import java.time.Duration;
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext.SerializationPair;

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    RedisCacheManagerBuilderCustomizer redisCacheManagerBuilderCustomizer(ObjectMapper objectMapper) {
        Jackson2JsonRedisSerializer<LegalDocumentDetail> serializer =
                new Jackson2JsonRedisSerializer<>(objectMapper, LegalDocumentDetail.class);
        RedisCacheConfiguration detailCache = RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofHours(6))
                .serializeValuesWith(SerializationPair.fromSerializer(serializer));
        return builder -> builder.withCacheConfiguration("legal-document-detail", detailCache);
    }
}
