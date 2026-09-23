package com.example.orders;

import java.util.List;
import org.springframework.transaction.annotation.Transactional;

public class OrderReportService {
    private final OrderRepository orderRepository;

    public OrderReportService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public int countLineItems() {
        int total = 0;
        for (Order order : orderRepository.findAll()) {
            total += order.getLineItems().size();
        }
        return total;
    }
}
