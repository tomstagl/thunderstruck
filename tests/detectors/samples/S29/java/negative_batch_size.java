package com.example.orders;

import java.util.List;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import org.hibernate.annotations.BatchSize;
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

@Entity
class Order {
    @Id
    Long id;

    @OneToMany(mappedBy = "order")
    @BatchSize(size = 50)
    List<LineItem> lineItems;

    List<LineItem> getLineItems() {
        return lineItems;
    }
}
