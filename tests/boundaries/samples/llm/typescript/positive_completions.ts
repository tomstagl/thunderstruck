export async function ask(client: OpenAI, prompt: string) {
  return client.chat.completions.create({ model: "m", messages: [{ role: "user", content: prompt }] });  // boundary: LLM
}
