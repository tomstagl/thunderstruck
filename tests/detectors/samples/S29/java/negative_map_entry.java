package com.example.orders;

import java.util.List;
import java.util.Map;
import org.springframework.transaction.annotation.Transactional;

public class OrderGroupingService {
    private final OrderRepository orderRepository;

    public OrderGroupingService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public int largestGroup(Map<String, List<Long>> grouped, Map<String, Order> byRef) {
        int max = 0;
        for (Map.Entry<String, List<Long>> e : grouped.entrySet()) {
            max = Math.max(max, e.getValue().size());
        }
        for (java.util.Map.Entry<String, Order> entry : byRef.entrySet()) {
            System.out.println(entry.getKey().length() + entry.getValue().getReference());
        }
        return max;
    }
}
