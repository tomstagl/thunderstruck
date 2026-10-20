def record_payment(session, order_id, amount):
    payment = Payment(order_id=order_id, amount=amount)
    session.add(payment)
    session.commit()
