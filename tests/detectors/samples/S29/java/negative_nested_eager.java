package com.example.catalog;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.transaction.annotation.Transactional;

public class AuthorCatalogService {
    private final AuthorRepository authorRepository;

    public AuthorCatalogService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @Transactional(readOnly = true)
    public List<String> titles() {
        List<String> titles = new ArrayList<>();
        for (Author author : authorRepository.findAllWithBooks()) {
            for (Book book : author.getBooks()) {
                titles.add(book.getTitle());
            }
        }
        return titles;
    }
}

interface AuthorRepository extends JpaRepository<Author, Long> {
    @Query("select distinct a from Author a join fetch a.books")
    List<Author> findAllWithBooks();
}
