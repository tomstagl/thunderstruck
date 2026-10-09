def ask(client, prompt):
    return client.messages.create(model="m", max_tokens=100, messages=[{"role": "user", "content": prompt}])  # boundary: LLM
