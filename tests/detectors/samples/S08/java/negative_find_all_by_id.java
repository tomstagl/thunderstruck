package com.example.orders;

import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findAllById(Iterable<Long> ids);
    List<Order> findByIdIn(Collection<Long> ids);
}

class Order { }
