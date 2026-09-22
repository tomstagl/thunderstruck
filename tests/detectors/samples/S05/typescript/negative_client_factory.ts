import axios from "axios";
import axiosRetry from "axios-retry";

export const client = axios.create({ baseURL: BASE, timeout: 5_000 });
axiosRetry(client, { retries: 3, retryDelay: axiosRetry.exponentialDelay });
