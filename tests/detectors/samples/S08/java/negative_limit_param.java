package com.example.orders;

import java.util.List;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByStatus(String status, Limit limit);
    Window<Order> findByCustomer(String customer, ScrollPosition position);
}

class Order { }
