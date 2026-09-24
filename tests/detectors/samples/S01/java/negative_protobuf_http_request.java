package com.example.tasks;

import com.google.cloud.tasks.v2.CloudTasksClient;
import com.google.cloud.tasks.v2.HttpMethod;
import com.google.cloud.tasks.v2.HttpRequest;
import com.google.cloud.tasks.v2.OidcToken;
import com.google.cloud.tasks.v2.QueueName;
import com.google.cloud.tasks.v2.Task;
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.service.auth.v3.AttributeContext;

// Protobuf messages named HttpRequest are data, not java.net.http requests.
// Nothing here is sent by an HttpClient, so there is no request timeout to set.
public class TaskEnqueuer {
    private final CloudTasksClient tasks;
    private final QueueName queue;

    public TaskEnqueuer(CloudTasksClient tasks, QueueName queue) {
        this.tasks = tasks;
        this.queue = queue;
    }

    public Task enqueue(String url, String payload, String serviceAccount) {
        Task task = Task.newBuilder()
                .setHttpRequest(HttpRequest.newBuilder()
                        .setUrl(url)
                        .setHttpMethod(HttpMethod.POST)
                        .putHeaders("Content-Type", "application/json")
                        .setBody(ByteString.copyFromUtf8(payload))
                        .setOidcToken(OidcToken.newBuilder().setServiceAccountEmail(serviceAccount))
                        .build())
                .build();
        return tasks.createTask(queue, task);
    }

    public AttributeContext.Request describe(String path) {
        AttributeContext.HttpRequest.Builder http = AttributeContext.HttpRequest.newBuilder();
        http.setPath(path);
        http.setMethod("POST");
        http.setProtocol("HTTP/2");
        return AttributeContext.Request.newBuilder().setHttp(http).build();
    }
}
