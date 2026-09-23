package com.example.orders;

import java.util.List;
import org.springframework.transaction.annotation.Transactional;

public class OrderSummaryService {
    private final OrderRepository orderRepository;

    public OrderSummaryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public int countLines(List<OrderDto> orders) {
        int total = 0;
        for (OrderDto dto : orders) {
            total += dto.getLines().size();
        }
        return total;
    }

    public String firstNames(List<OrderView> views) {
        StringBuilder names = new StringBuilder();
        for (OrderView view : views) {
            names.append(view.getCustomer().getName());
        }
        return names.toString();
    }

    @Transactional(readOnly = true)
    public int mappedLines() {
        int total = 0;
        for (var summary : orderRepository.findAll().stream().map(OrderSummary::from).toList()) {
            total += summary.getLines().size();
        }
        return total;
    }
}
