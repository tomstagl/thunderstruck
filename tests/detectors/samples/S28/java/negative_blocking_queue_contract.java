package com.example.queue;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class BoundedDeque<E> implements java.util.concurrent.BlockingDeque<E> {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition notEmpty = lock.newCondition();
    private final Condition notFull = lock.newCondition();

    @Override
    public void putLast(final E e) throws InterruptedException {
        lock.lock();
        try {
            while (!linkLast(e)) {
                notFull.await();
            }
        } finally {
            lock.unlock();
        }
    }

    @Override
    public E takeFirst() throws InterruptedException {
        lock.lock();
        try {
            E x;
            while ((x = unlinkFirst()) == null) {
                notEmpty.await();
            }
            return x;
        } finally {
            lock.unlock();
        }
    }

    @Override
    public E pollFirst(long timeout, TimeUnit unit) throws InterruptedException {
        long nanos = unit.toNanos(timeout);
        lock.lock();
        try {
            E x;
            while ((x = unlinkFirst()) == null) {
                if (nanos <= 0) {
                    return null;
                }
                nanos = notEmpty.awaitNanos(nanos);
            }
            return x;
        } finally {
            lock.unlock();
        }
    }

    private boolean linkLast(E e) { return false; }
    private E unlinkFirst() { return null; }
}
