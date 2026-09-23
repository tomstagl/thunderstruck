package com.example.orders;

import java.util.List;
import org.springframework.data.jpa.repository.Query;
import org.springframework.transaction.annotation.Transactional;

public class OrderReportService {
    private final OrderRepository orderRepository;

    public OrderReportService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public int countLineItems() {
        int total = 0;
        for (Order order : orderRepository.findAllWithLineItems()) {
            total += order.getLineItems().size();
        }
        return total;
    }
}

interface OrderRepository extends org.springframework.data.jpa.repository.JpaRepository<Order, Long> {
    @Query("select distinct o from Order o join fetch o.lineItems")
    List<Order> findAllWithLineItems();
}
