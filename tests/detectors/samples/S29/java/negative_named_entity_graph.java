package com.example.orders;

import java.util.List;
import java.util.Map;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

public class OrderReportService {
    private final EntityManager entityManager;

    public OrderReportService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional(readOnly = true)
    public int countLineItems() {
        List<Order> orders = entityManager.createQuery("select o from Order o", Order.class)
                .setHint("jakarta.persistence.fetchgraph", entityManager.getEntityGraph("Order.lineItems"))
                .getResultList();
        int total = 0;
        for (Order order : orders) {
            total += order.getLineItems().size();
        }
        return total;
    }
}
