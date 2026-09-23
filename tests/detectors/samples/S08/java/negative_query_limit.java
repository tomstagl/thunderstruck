package com.example.orders;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface OrderRepository extends JpaRepository<Order, Long> {
    @Query(value = "select * from orders order by created_at desc limit 20", nativeQuery = true)
    List<Order> findRecent();

    @Query(value = "select * from orders where status = :status fetch first 50 rows only", nativeQuery = true)
    List<Order> findOldestByStatus(String status);
}

class Order { }
