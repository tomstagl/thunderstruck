package com.example.orders;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.transaction.annotation.Transactional;

public class OrderExportService {
    private final OrderRepository orderRepository;

    public OrderExportService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public void export(List<String> codes) {
        for (Order order : orderRepository.findAll()) {
            String name = order.getName().trim();
            String email = order.getEmail().toLowerCase();
            String nickname = order.getNickname().orElse("none");
            boolean open = order.getStatus().equals("OPEN");
            String state = order.getState().name();
            int sign = order.getTotal().compareTo(BigDecimal.ZERO);
            int year = order.getCreatedAt().getYear();
            String created = order.getCreatedAt().toString();
            String kind = order.getClass().getSimpleName();
            Long customerId = order.getCustomer().getId();
            System.out.println(name + email + nickname + open + state + sign + year + created + kind + customerId);
        }
        for (String code : codes) {
            System.out.println(code.getBytes().length);
        }
    }
}
