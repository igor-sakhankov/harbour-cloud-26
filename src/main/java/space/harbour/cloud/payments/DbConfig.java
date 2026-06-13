package space.harbour.cloud.payments;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;

@ConfigurationProperties(prefix = "app.db")
public record DbConfig(int shardCount, List<ShardConfig> shards) {

    public record ShardConfig(String url, String username, String password) {}
}
