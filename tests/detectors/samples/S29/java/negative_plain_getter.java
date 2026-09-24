package com.example.orders;

import java.util.ArrayList;
import java.util.List;
import org.springframework.transaction.annotation.Transactional;

public class OrderIdService {
    private final OrderRepository orderRepository;

    public OrderIdService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public List<Long> ids() {
        List<Long> ids = new ArrayList<>();
        for (Order order : orderRepository.findAll()) {
            ids.add(order.getId());
        }
        return ids;
    }
}
