import { ChannelCredentials } from "@grpc/grpc-js";
import { CartServiceClient } from "./gen/cart";

const { CART_ADDR = '' } = process.env;
const { SHIPPING_ADDR: ship } = process.env;

export const cart = new CartServiceClient(CART_ADDR, ChannelCredentials.createInsecure());

export async function quote() {
  return fetchWithRetry(`${ship}/get-quote`);
}
