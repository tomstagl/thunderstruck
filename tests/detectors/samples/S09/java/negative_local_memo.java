package com.example.reports;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class OrderReport {
    private final CustomerRepository customers;

    public OrderReport(CustomerRepository customers) {
        this.customers = customers;
    }

    public List<String> build(List<Order> orders) {
        Map<Long, String> customerCache = new HashMap<>();
        List<String> rows = new ArrayList<>();
        for (Order order : orders) {
            String customer = customerCache.get(order.customerId());
            if (customer == null) {
                customer = customers.findName(order.customerId());
                customerCache.put(order.customerId(), customer);
            }
            rows.add(order.id() + "," + customer);
        }
        return rows;
    }

    public interface CustomerRepository { String findName(long id); }

    public record Order(long id, long customerId) { }
}
