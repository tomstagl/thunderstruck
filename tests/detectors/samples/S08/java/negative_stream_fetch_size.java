package com.example.orders;

import java.util.stream.Stream;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.QueryHints;

public interface OrderRepository extends JpaRepository<Order, Long> {
    @QueryHints(@QueryHint(name = org.hibernate.jpa.HibernateHints.HINT_FETCH_SIZE, value = "500"))
    Stream<Order> streamAllByStatus(String status);
}

class Order { }
