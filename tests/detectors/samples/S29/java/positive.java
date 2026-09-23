package com.example.orders;

import java.util.List;
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

class AuthorCatalogService {
    private final AuthorRepository authorRepository;

    AuthorCatalogService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @org.springframework.transaction.annotation.Transactional(readOnly = true)
    java.util.List<String> titles() {
        java.util.List<String> titles = new java.util.ArrayList<>();
        for (Author author : authorRepository.findAll()) {
            for (Book book : author.getBooks()) {
                titles.add(book.getTitle());
            }
        }
        return titles;
    }
}
